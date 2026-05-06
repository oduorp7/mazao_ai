"""
handlers.py — All Telegram command and message handlers.

Each handler is a standalone async function registered in bot.py.
Pattern: receive Update → check tenant state → act → reply.

Conversation states (stored in DB):
  idle              — normal, commands work
  awaiting_name     — /start flow, waiting for business name
  awaiting_till     — waiting for M-Pesa till number
  awaiting_settings_name  — editing business name
  awaiting_settings_phone — editing phone number
  awaiting_settings_till  — editing till number
"""

from __future__ import annotations

import structlog
import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from apps.agent import estimator
from apps.agent import obligations

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import apps.tg_bot.db as db
import apps.tg_bot.messages as M
from apps.tg_bot import router
from apps.tg_bot import mpesa_parser
from apps.tg_bot.menu import update_user_menu
from apps.tg_bot.trial import is_feature_allowed, start_trial, get_trial_status
from apps.payments.stk import initiate_stk_push
from apps.agent.utils.logging import get_logger
from apps.agent.utils.ocr_service import ocr_engine
from apps.agent.state import RawTransaction, TransactionType

log = get_logger(__name__)

# ── Global State for Rate Limiting (P8-T4) ──────────────────────────────────
# Maps tenant_id -> list of timestamps of recent /upgrade attempts
upgrade_rate_limit = {}

# P20-FIX_06: In-memory pipeline mutex to prevent race conditions during report generation
# Maps tenant_id (str) -> bool
_pipeline_locks: dict[str, bool] = {}

# ── Constants ─────────────────────────────────────────────────────────────

HOUSEHOLD_TYPE_LABELS = {
    "basic": "Basic (No fridge)",
    "standard": "Standard (Fridge + TV)",
    "comfort": "Comfort (Fridge + TV + Heater)",
    "business": "Business Premises"
}

# P16-FIX-FINAL: KPLC Tariff Tiers — update ONLY this dict when EPRA revises rates.
# Source: EPRA / KPLC Schedule of Tariffs 2025
# D1 Lifeline: KES 12.23/unit, D2 Ordinary: KES 16.45/unit, D3 High: KES 19.08/unit base rates.
# Thresholds apply to TknAmt/Units (electricity-only rate from token SMS).
KPLC_TARIFF_TIERS = {
    "D1": {"max_rate": 13.50, "label": "Lifeline (D1)",         "description": "Low consumption < 30 units/month"},
    "D2": {"max_rate": 17.50, "label": "Ordinary (D2)",          "description": "Medium consumption 30–100 units/month"},
    "D3": {"max_rate": 99.99, "label": "High Consumption (D3)",  "description": "Heavy usage > 100 units/month"},
}

# ── Plan Normalization (P17-T4I) ─────────────────────────────────────────────
NORM_PLAN_MAP = {
    'biashara': 'pro',
    'mtu_wenyewe': 'core',
    'hustler': 'free',
    'pro': 'pro',
    'core': 'core',
    'free': 'free',
    'trial': 'trial'
}
# ── T43: Admin & Control Constants ─────────────────────────────────────────────
ADMIN_TELEGRAM_ID = 5833240219
# ─────────────────────────────────────────────────────────────────────────────

# ── Helpers ───────────────────────────────────────────────────────────────────

# ── T6F: Centralized DB fail-safe wrapper ────────────────────────────────────
async def _safe_db_call(fn, *, default=None):
    """Run a synchronous DB function in the executor with a safe fallback.

    Usage:
        tenant = await _safe_db_call(lambda: db.get_tenant(tid))

    - Runs fn() off the event loop (non-blocking).
    - On ANY exception, logs a warning and returns `default` (None by default).
    - Keeps handlers crash-proof regardless of Supabase state.
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(None, fn)
    except Exception as exc:
        log.warning("safe_db_call_failed", error=str(exc), fn=getattr(fn, "__name__", repr(fn)))
        return default


# ── T6F-EMPTY-STATE: Statement empty-state renderer ─────────────────────────
async def _render_statement_empty_state(update: Update) -> None:
    """Render the FAANG-grade empty-state for /statement and /report.

    Shows a guided message with two CTA buttons:
      📤 Upload Statement  → triggers awaiting_statement_upload session
      ❓ How to Export     → shows step-by-step guide inline

    Never leaks internal state. No dead ends.
    """
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Statement", callback_data="statement_upload")],
        [InlineKeyboardButton("❓ How to Export", callback_data="statement_guide")],
    ])
    await _reply(update, M.STATEMENT_REQUIRED, reply_markup=keyboard)


# ── T6F-EMPTY-STATE: Report empty-state renderer ────────────────────────────
async def _render_report_empty_state(update: Update) -> None:
    """Render the UX-separated empty-state for /report.
    
    Explains the dependency on M-Pesa data before a report can be generated.
    """
    await _reply(update, M.REPORT_STATEMENT_REQUIRED)


# ── KPLC SMS helpers (P16-FIX-FINAL) ─────────────────────────────────────────

_KPLC_SMS_RE = re.compile(
    r"Mtr[:\s]*([A-Za-z0-9]+)\s+"
    r"Token[:\s]*([\d\-]+)\s+"
    r"Date[:\s]*(\d{8})\s+(\d{2}:\d{2})\s+"
    r"Units[:\s]*([\d.]+)\s+"
    r"Amt[:\s]*([\d.]+)\s+"
    r"TknAmt[:\s]*([\d.]+)\s+"
    r"OtherCharges[:\s]*([\d.]+)",
    re.IGNORECASE,
)


def _parse_kplc_sms(text: str) -> Optional[Dict]:
    """Pure function. Attempts to parse a full KPLC token SMS.

    Returns a structured dict on success, None on failure.
    No side effects. Fully unit-testable.

    Expected SMS format::
        Mtr:0277100839863 Token:0967-8847-2772-1258-0314 Date:20260422 12:47
        Units:28.3 Amt:1000.00 TknAmt:525.26 OtherCharges:474.74
    """
    import structlog as _structlog
    _log = _structlog.get_logger(__name__)

    m = _KPLC_SMS_RE.search(text)
    if not m:
        _log.debug("kplc_sms_parse_failed_using_short_form", input_length=len(text))
        return None

    try:
        date_str, time_str = m.group(3).strip(), m.group(4).strip()
        purchase_date = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H:%M").date()
    except ValueError:
        try:
            purchase_date = datetime.strptime(m.group(3).strip()[:8], "%Y%m%d").date()
        except ValueError:
            _log.warning("kplc_sms_date_parse_failed", date_raw=m.group(3))
            return None

    units = float(m.group(5))
    amount_paid = float(m.group(6))
    token_amount = float(m.group(7))
    other_charges = float(m.group(8))

    if units <= 0 or amount_paid <= 0 or token_amount < 0 or other_charges < 0:
        _log.warning("kplc_sms_invalid_values", units=units, amount_paid=amount_paid)
        return None

    return {
        "meter_number":  m.group(1).strip(),
        "token_number":  m.group(2).strip(),
        "purchase_date": purchase_date,
        "units":         units,
        "amount_paid":   amount_paid,
        "token_amount":  token_amount,
        "other_charges": other_charges,
        "is_full_sms":   True,
    }


def _detect_tariff_tier(rate_per_unit: float) -> Dict:
    """Pure function. Derives tariff tier dict from TknAmt/Units rate.

    Iterates KPLC_TARIFF_TIERS in defined order (D1 → D2 → D3).
    Returns the first tier where rate_per_unit <= max_rate.
    Uses KPLC_TARIFF_TIERS constant — no inline thresholds.
    """
    for tier_key, tier in KPLC_TARIFF_TIERS.items():
        if rate_per_unit <= tier["max_rate"]:
            return {"key": tier_key, **tier}
    # Fallback: return D3 for any rate above all thresholds
    d3 = KPLC_TARIFF_TIERS["D3"]
    return {"key": "D3", **d3}


async def _check_subscription_guard(update: Update, feature: str = "utility_tracking") -> bool:
    """Centralized subscription guard for user-initiated utility entry."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return False
        
    if not await is_feature_allowed(str(tenant["id"]), feature):
        await _reply(update, M.UPGRADE_REQUIRED.format(
            feature_name="Utility Tracking",
            upgrade_link=f"{os.getenv('FLY_APP_URL', 'https://mazao-ai.fly.dev')}/upgrade"
        ))
        return False
    return True


def _tg_id(update: Update) -> int:
    return update.effective_user.id


def _username(update: Update) -> str:
    return update.effective_user.username or ""


def _full_name(update: Update) -> str:
    u = update.effective_user
    return f"{u.first_name or ''} {u.last_name or ''}".strip()


# P19-T9G1: Referral & Control Flags
REFERRAL_REWARDS_ENABLED = False

async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays bot information (P19-T9G1)."""
    await _reply(update, M.ABOUT_MESSAGE)

async def _reply(update: Update, text: str, **kwargs) -> None:
    # CF-1: Final safety net redaction of any KRA PIN patterns (A0xxxxxxxB)
    import re
    text = re.sub(r'\b[A-P]\d{9}[A-Z]\b', '[REDACTED]', text)
    
    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        **kwargs,
    )

async def _maybe_send_nudge(update: Update, context: ContextTypes.DEFAULT_TYPE, nudge_text: str, condition: bool = True) -> None:
    """Sends a conversion nudge if conditions are met and none has been sent in this session (P17-T4J)."""
    # T43: Upsell targeting enforcement
    # Admin, Trial, and Paid users never see unsolicited upgrade prompts.
    tid = update.effective_user.id
    if tid == ADMIN_TELEGRAM_ID:
        return

    if not condition:
        return
    
    # Session gating (one nudge per interaction session)
    if context.user_data.get("nudge_sent_this_session"):
        return
    
    try:
        await _reply(update, nudge_text)
        context.user_data["nudge_sent_this_session"] = True
        log.info("conversion_nudge_sent", telegram_id=update.effective_user.id)
    except Exception as e:
        log.error("conversion_nudge_failed", error=str(e))


def _fmt_kes(amount: float) -> str:
    return f"{amount:,.0f}"


def _get_htype_keyboard(current_htype: Optional[str] = None) -> InlineKeyboardMarkup:
    """Generates inline keyboard for household type with active selection indicator."""
    keyboard = []
    # FAANG Grade: Progressive Disclosure UI (1 per row for mobile legibility)
    for code, label in HOUSEHOLD_TYPE_LABELS.items():
        prefix = "✅ " if current_htype == code else ""
        btn = InlineKeyboardButton(f"{prefix}{label}", callback_data=f"htype_{code}")
        keyboard.append([btn])
    
    # Navigation: Return to settings
    keyboard.append([InlineKeyboardButton("⬅️ Back to Settings", callback_data="back_to_settings")])
    
    return InlineKeyboardMarkup(keyboard)


# ── /start — onboarding entry point ──────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    log.info("cmd_start", telegram_id=tid)
    
    # P18-T8E: Clear state on start
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))

    # P10-T4: Handle Referral deep link (start=REF_CODE)
    args = context.args
    referred_by_id = None
    try:
        if args and args[0].startswith("REF_"):
            ref_code = args[0]
            log.info("referral_link_detected", telegram_id=tid, ref_code=ref_code)
            # Find referrer
            referrer_resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: db.get_client().table("tenants").select("id").eq("referral_code", ref_code).execute()
            )
            if referrer_resp and referrer_resp.data:
                potential_referrer = referrer_resp.data[0]
                # P19-T9G: Self-referral protection (if they somehow found their own link)
                # Note: tid is int, but we check if potential_referrer id exists and isn't them
                # For a new user, they won't have a record yet, so this is safe.
                referred_by_id = potential_referrer["id"]
                log.info("referrer_found", referrer_id=referred_by_id)
    except Exception as e:
        log.error("referral_parsing_failed", error=str(e), telegram_id=tid)
        # Continue onboarding regardless of referral failure

    tenant = await _safe_db_call(lambda: db.get_tenant(tid))

    # P18-T8G: Idempotent Routing & Onboarding Escape
    if tenant:
        has_name = bool(tenant.get("business_name") or tenant.get("full_name"))
        has_lang = bool(tenant.get("preferred_language"))
        
        if has_name and has_lang:
            # ACTIVE_USER: Skip onboarding entirely
            await update_user_menu(context.bot, tid, tenant)
            name = tenant.get("business_name") or tenant.get("full_name") or "there"
            await _reply(update, M.WELCOME_BACK_MENU.format(name=name))
            log.info("start_bypass_onboarding", telegram_id=tid)
            return

        # PARTIAL_ONBOARDING: Resume from missing step
        u_type = tenant.get("user_type")
        if not u_type:
            keyboard = [
                [
                    InlineKeyboardButton("🏢 Business Owner", callback_data="type_business"),
                    InlineKeyboardButton("👤 Individual", callback_data="type_individual"),
                ]
            ]
            await _reply(update, M.USER_TYPE_SELECT, reply_markup=InlineKeyboardMarkup(keyboard))
        elif not has_name:
            if u_type == "business":
                await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_name"))
                await _reply(update, M.WELCOME)
            else:
                await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_individual_name"))
                await _reply(update, M.INDIVIDUAL_ASK_NAME)
        elif not has_lang:
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_language"))
            keyboard = [
                [
                    InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
                    InlineKeyboardButton("🇰🇪 Swahili", callback_data="lang_sw"),
                ]
            ]
            await _reply(update, M.ASK_LANGUAGE, reply_markup=InlineKeyboardMarkup(keyboard))
        
        log.info("start_resume_onboarding", telegram_id=tid, u_type=u_type)
        return

    # NEW_USER: Fresh Start
    keyboard = [
        [
            InlineKeyboardButton("🏢 Business Owner", callback_data="type_business"),
            InlineKeyboardButton("👤 Individual", callback_data="type_individual"),
        ]
    ]
    await _reply(update, M.USER_TYPE_SELECT, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Create tenant record
    await asyncio.get_event_loop().run_in_executor(
        None, 
        lambda: db.create_tenant(
            telegram_id=tid,
            telegram_username=_username(update),
            full_name=_full_name(update),
            referred_by=referred_by_id
        )
    )
    log.info("start_new_user", telegram_id=tid)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Settings menu (HF-T3)."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    # FAANG Grade: Surface current state in the menu labels
    ht_code = tenant.get("household_type", "basic")
    ht_label = HOUSEHOLD_TYPE_LABELS.get(ht_code, "Set Type")
    
    lang_code = tenant.get("preferred_language", "en")
    lang_label = "English" if lang_code == "en" else "Swahili"

    keyboard = [
        [
            InlineKeyboardButton("✏️ Business Name", callback_data="set_name"),
            InlineKeyboardButton(f"🌍 Lang: {lang_label}", callback_data="set_lang"),
        ],
        [
            InlineKeyboardButton(f"🏠 Home: {ht_label}", callback_data="set_htype"),
            InlineKeyboardButton("📱 Phone Number", callback_data="set_phone"),
        ],
        [
            InlineKeyboardButton("🧾 Till Number", callback_data="set_till"),
            InlineKeyboardButton("👥 Employees", callback_data="set_emp"),
        ],
        [
            InlineKeyboardButton("💰 VAT Status", callback_data="set_vat"),
        ]
    ]
    await _reply(update, M.SETTINGS_MENU, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries from inline keyboards."""
    query = update.callback_query
    await query.answer()
    
    tid = query.from_user.id
    data = query.data
    
    log.info("callback_received", telegram_id=tid, data=data)

    if data == "tokens_add_new":
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_tokens"))
        await query.edit_message_text(M.TOKEN_ENTRY_PROMPT)
        return

    # T6F-EMPTY-STATE: Statement CTA callbacks
    elif data == "statement_upload":
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_statement_upload"))
        await query.edit_message_text(M.STATEMENT_UPLOAD_PROMPT)
        log.info("statement_upload_session_started", telegram_id=tid)
        return

    elif data == "statement_guide":
        await query.answer()  # acknowledge before sending new message
        await query.edit_message_text(M.STATEMENT_GUIDE_TEXT)
        log.info("statement_guide_shown", telegram_id=tid)
        return

    elif data == "tokens_change_htype":
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        current_htype = tenant.get("household_type")
        keyboard = []
        for code, label in HOUSEHOLD_TYPE_LABELS.items():
            prefix = "✅ " if current_htype == code else ""
            btn = InlineKeyboardButton(f"{prefix}{label}", callback_data=f"t_htype_{code}")
            keyboard.append([btn])
        keyboard.append([InlineKeyboardButton("⬅️ Back to Status", callback_data="tokens_back_to_status")])
        
        await query.edit_message_text(
            "🏠 *Select your Home Type:*\n\nThis updates your electricity prediction baselines.", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data.startswith("t_htype_"):
        new_htype = data.replace("t_htype_", "")
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"household_type": new_htype}))
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        await _render_tokens_status(query, tid, tenant)
        return

    elif data == "tokens_back_to_status":
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        await _render_tokens_status(query, tid, tenant)
        return

    # P17-T6E: Gas Dashboard Parity Callbacks
    elif data == "gas_add_new":
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_gas"))
        await query.edit_message_text(M.GAS_SMS_PROMPT)
        return

    elif data == "gas_change_htype":
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        current_htype = tenant.get("household_type")
        keyboard = []
        for code, label in HOUSEHOLD_TYPE_LABELS.items():
            prefix = "✅ " if current_htype == code else ""
            btn = InlineKeyboardButton(f"{prefix}{label}", callback_data=f"g_htype_{code}")
            keyboard.append([btn])
        keyboard.append([InlineKeyboardButton("⬅️ Back to Status", callback_data="gas_back_to_status")])
        
        await query.edit_message_text(
            "🏠 *Select your Home Type:*\n\nThis updates your gas prediction baselines.", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data.startswith("g_htype_"):
        new_htype = data.replace("g_htype_", "")
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"household_type": new_htype}))
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        await _render_gas_status(query, tid, tenant)
        return

    elif data == "gas_back_to_status":
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        await _render_gas_status(query, tid, tenant)
        return

    if data == "set_htype":
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        current_htype = tenant.get("household_type")
        reply_markup = _get_htype_keyboard(current_htype)
        await query.edit_message_text(
            "🏠 *Select your Home Type:*\n\nThis updates your electricity prediction baselines.", 
            reply_markup=reply_markup
        )

    elif data == "back_to_settings":
        # Re-use cmd_settings logic for a seamless experience
        await cmd_settings(update, context)
        return

    elif data == "set_name":
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_settings_name"))
        await query.edit_message_text(M.SETTINGS_EDIT_NAME_PROMPT)
    
    elif data == "set_lang":
        keyboard = [
            [
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
                InlineKeyboardButton("🇰🇪 Swahili", callback_data="lang_sw"),
            ]
        ]
        await query.edit_message_text(M.ASK_LANGUAGE, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "set_phone":
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_settings_phone"))
        await query.edit_message_text(M.SETTINGS_EDIT_PHONE_PROMPT)

    elif data == "set_till":
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_settings_till"))
        await query.edit_message_text(M.SETTINGS_EDIT_TILL_PROMPT)

    elif data == "set_emp":
        keyboard = [
            [
                InlineKeyboardButton("Yes", callback_data="set_emp_yes"),
                InlineKeyboardButton("No", callback_data="set_emp_no"),
            ]
        ]
        await query.edit_message_text(M.SETTINGS_EDIT_EMPLOYEES_PROMPT, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "set_vat":
        keyboard = [
            [
                InlineKeyboardButton("Yes", callback_data="set_vat_yes"),
                InlineKeyboardButton("No", callback_data="set_vat_no"),
            ]
        ]
        await query.edit_message_text(M.SETTINGS_EDIT_VAT_PROMPT, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("set_emp_"):
        val = data.replace("set_emp_", "")
        # Robust handling for potential DB schema lag
        try:
            # Map yes/no to a status if we want to store it in employment_status, 
            # or just skip if the column doesn't exist.
            # In settings, we likely want to know if they have employees for PAYE/NSSF
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"employment_status": "has_employees" if val == "yes" else "sole_proprietor"}))
        except Exception as e:
            log.warning("schema_inconsistency", error=str(e), column="employment_status")
        
        await query.edit_message_text(M.SETTINGS_UPDATED.format(field="Employees", new_value=val.upper()))

    elif data.startswith("set_vat_"):
        val = data.replace("set_vat_", "")
        # Fallback: if is_vat_registered is missing from schema, skip DB update but proceed with UI
        try:
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"is_vat_registered": val == "yes"}))
        except Exception as e:
            log.warning("schema_inconsistency", error=str(e), column="is_vat_registered")
            
        await query.edit_message_text(M.SETTINGS_UPDATED.format(field="VAT Status", new_value=val.upper()))
        return

    elif data == "type_business":
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_name", data={"user_type": "business"}))
        # Create tenant row if not exists
        if not await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid)):
            await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: db.create_tenant(
                    telegram_id=tid,
                    telegram_username=query.from_user.username,
                    full_name=query.from_user.full_name,
                )
            )
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"user_type": "business"}))
        await query.edit_message_text(M.WELCOME)
        
    elif data == "type_individual":
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_individual_name"))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"user_type": "individual"}))
        await query.edit_message_text(M.INDIVIDUAL_ASK_NAME)

    elif data.startswith("emp_"):
        status = data.replace("emp_", "")
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"employment_status": status}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_language"))
        
        keyboard = [
            [
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
                InlineKeyboardButton("🇰🇪 Swahili", callback_data="lang_sw"),
            ]
        ]
        await query.edit_message_text(M.ASK_LANGUAGE, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("upgrade_"):
        plan = data.replace("upgrade_", "")
        log.info("upgrade_selection", telegram_id=tid, plan=plan)
        
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        # Store plan in conv state to know what we are paying for after phone is given
        await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: db.set_conv_state(tid, "awaiting_upgrade_phone", data={"pending_plan": plan})
        )
        
        prompt = "📱 *M-Pesa Number*\n\nPlease enter the phone number you'll use for payment (e.g., `0712345678`)."
        if tenant.get("phone_number"):
            prompt += f"\n\nPress enter (or reply with a new number) to use *{tenant['phone_number']}*."
            
        await query.edit_message_text(prompt)

    elif data.startswith("htype_"):
        new_htype = data.replace("htype_", "")
        try:
            tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
            old_htype = tenant.get("household_type")
            
            # WWFD: Instant non-disruptive feedback for redundant clicks
            if str(old_htype) == str(new_htype):
                label = HOUSEHOLD_TYPE_LABELS.get(new_htype, new_htype.capitalize())
                await query.answer(f"Already set to {label}", show_alert=False)
                return

            # Atomically update DB
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"household_type": new_htype}))

            # P16-FIX-02-FINAL: WWFD — no fabricated projection. Show baseline only.
            new_baseline = estimator.get_population_baseline(new_htype)
            display_label = HOUSEHOLD_TYPE_LABELS.get(new_htype, new_htype.capitalize())

            await query.edit_message_text(
                f"☁️ Home type updated to *{display_label}*\n\n"
                f"📊 New baseline: *{new_baseline} units/day*\n"
                f"_Baseline updated. Your projection will be recalculated next time you record tokens via /tokens._",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚙️ Back to Settings", callback_data="back_to_settings")
                ]]),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Post-update synchronization
            tenant["household_type"] = new_htype
            await update_user_menu(context.bot, tid, tenant)
            log.info("htype_updated_verified", tenant_id=tid, new_htype=new_htype)
            
        except Exception as e:
            log.error("htype_callback_failed", telegram_id=tid, error=str(e))
            await query.answer("Something went wrong updating your settings.", show_alert=True)
        return

    elif data.startswith("lang_"):
        try:
            lang = data.replace("lang_", "")
            log.info("language_selection", telegram_id=tid, lang=lang)
            
            # FAANG Grade: Robustly handle potential DB schema lag
            try:
                await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"preferred_language": lang}))
            except Exception as e:
                log.warning("preferred_language_update_failed", error=str(e))
                if "preferred_language" in str(e).lower():
                    await query.answer("⚠️ Database Migration Missing", show_alert=True)
                else:
                    raise e

            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            
            tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
            
            # ── Onboarding Completion (P10-T2) ───────────────────────────
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: db.update_tenant(tid, {"onboarding_completed": True})
                )
                tenant["onboarding_completed"] = True
            except Exception as e:
                log.warning("onboarding_completed_update_failed", error=str(e))
            
            # ── Progressive Command Menu Update (P13) ──────────────────────
            await update_user_menu(context.bot, tid, tenant)
            # ─────────────────────────────────────────────────────────────

            # ── Founding Member Auto-Tag (P9-T2) ──────────────────────────
            # Set founding_member=true if total tenants <= 50
            try:
                total_tenants = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: db.get_client().table("tenants").select("id", count="exact").execute()
                )
                if total_tenants.count and total_tenants.count <= 50:
                    log.info("founding_member_tagged", telegram_id=tid)
                    await asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: db.update_tenant(tid, {"founding_member": True})
                    )
                    tenant["founding_member"] = True # Update local dict for immediate use
            except Exception as e:
                log.warning("founding_member_tag_failed", error=str(e))
            # ─────────────────────────────────────────────────────────────

            name = (tenant.get("full_name") or tenant.get("business_name") or "User") if tenant else "User"
            
            msg = M.LANGUAGE_SET_EN if lang == "en" else M.LANGUAGE_SET_SW
            
            # ── Warm Onboarding Finish (P9-T5) ───────────────────────────
            trial_ends = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%d %b %Y")
            badge = M.FOUNDING_BADGE if tenant.get("founding_member") else ""
            
            if tenant.get("user_type") == "individual":
                if lang == "sw":
                    final_msg = M.ONBOARDING_SUCCESS_INDIVIDUAL_SW.format(
                        name=name, 
                        founding_badge=badge,
                        trial_ends_at=trial_ends
                    )
                else:
                    final_msg = M.ONBOARDING_SUCCESS_INDIVIDUAL.format(
                        name=name, 
                        founding_badge=badge,
                        trial_ends_at=trial_ends
                    )
            else:
                if lang == "sw":
                    final_msg = M.ONBOARDING_SUCCESS_BUSINESS_SW.format(
                        name=name, 
                        founding_badge=badge,
                        trial_ends_at=trial_ends
                    )
                else:
                    final_msg = M.ONBOARDING_SUCCESS_BUSINESS.format(
                        name=name, 
                        founding_badge=badge,
                        trial_ends_at=trial_ends
                    )
            
            await query.edit_message_text(f"{msg}\n\n{final_msg}")
            await query.answer(f"Language set to {lang.upper()}")

            # ── Start Trial (P7-T2) ──────────────────────────────────────────
            if tenant:
                try:
                    await start_trial(str(tenant["id"]))
                except Exception as e:
                    log.warning("start_trial_failed", error=str(e))
        except Exception as exc:
            log.exception("handle_callback_critical_failure", error=str(exc))
            await query.answer("⚠️ Mazao AI Logic Error")
            await query.edit_message_text("⚠️ *Mazao AI Logic Error*\nFailed to save settings.")


# ── /language ─────────────────────────────────────────────────────────────────

async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the language selection menu."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    keyboard = [
        [
            InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
            InlineKeyboardButton("🇰🇪 Swahili", callback_data="lang_sw"),
        ]
    ]
    await _reply(update, M.ASK_LANGUAGE, reply_markup=InlineKeyboardMarkup(keyboard))


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)
    # P18-T8E: Clear state on help
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
    
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    # P7-T6: Append Trial Reminder to Help
    status = await get_trial_status(str(tenant["id"]))
    help_text = M.HELP
    if status["active"] and not status["plan"] != "free": # On trial
        help_text += "\n" + M.TRIAL_REMINDER.format(days_remaining=status["days_remaining"])
    
    await _reply(update, help_text)


# ── /privacy ──────────────────────────────────────────────────────────────────

async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the privacy policy."""
    await _reply(update, M.PRIVACY_POLICY_TEXT)


# ── /feedback (P10-T3) ────────────────────────────────────────────────────────

async def cmd_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point for feedback collection."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_feedback"))
    await _reply(update, M.FEEDBACK_PROMPT)


# ── /refer (P10-T4) ───────────────────────────────────────────────────────────

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays unique referral link."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
        
    code = tenant.get("referral_code")
    if not code:
        code = f"MAZAO-{str(tenant['id'])[:6].upper()}"
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: db.update_tenant(tid, {"referral_code": code})
        )
        
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=REF_{code}"
    
    await _reply(update, M.REFERRAL_INFO.format(referral_link=link, code=code))


# ── /upgrade (P7-T4) ─────────────────────────────────────────────────────────

async def cmd_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point for plan selection."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    is_founding = tenant.get("founding_member", False)
    
    msg = M.UPGRADE_PROMPT.format(core_price=149, pro_price=399)
    if is_founding:
        msg = f"{M.FOUNDING_BADGE}\n\n{msg}"
    
    keyboard = [
        [InlineKeyboardButton("🔹 Upgrade to Core (KES 149)", callback_data="upgrade_core")],
        [InlineKeyboardButton("🔸 Upgrade to Pro (KES 399)", callback_data="upgrade_pro")],
    ]
    if is_founding:
        msg = f"{M.FOUNDING_BADGE}\n\n{msg}"
        
    await _reply(
        update, 
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ── /mystatus ─────────────────────────────────────────────────────────────────

async def cmd_mystatus(update: Update, context: ContextTypes.DEFAULT_TYPE, notice: str = "") -> None:
    """Displays the upcoming obligations for an individual user."""
    try:
        tid = _tg_id(update)
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        
        if not tenant:
            await _reply(update, M.NOT_REGISTERED)
            return

        # P7-T6: Feature Gating
        if not await is_feature_allowed(str(tenant["id"]), "compliance_alerts"):
            await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Individual Status", upgrade_link="/upgrade"))
            return
            
        if tenant.get("user_type") != "individual":
            await _reply(update, M.MYSTATUS_BUSINESS_REDIRECT)
            return

        obligations = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_individual_obligations(tid))
        
        status_label = tenant.get("employment_status", "unknown").title().replace("_", " ")
        text = M.MYSTATUS_HEADER.format(
            name=tenant.get("full_name", _username(update)),
            status=status_label
        )
        
        if notice:
            text = notice + "\n\n" + text
        
        today = datetime.now(timezone.utc)
        
        for ob in obligations:
            days_left = (ob["due_date"].date() - today.date()).days
            icon = "📋" if "Return" in ob["name"] else "🏥"
            
            text += M.MYSTATUS_OBLIGATION_ROW.format(
                icon=icon,
                name=ob["name"],
                due_date=ob["due_date"].strftime("%d %b %Y"),
                description=ob["description"],
                days_left=f"{days_left} days" if days_left >= 0 else "OVERDUE"
            )
            
        # CF-1: Proactive redaction of KRA PIN patterns (A0xxxxxxxB)
        import re
        text = re.sub(r'\b[A-P]\d{9}[A-Z]\b', '[REDACTED]', text)
        
        # P18-T4: Electricity summary
        try:
            tenant_data = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
            proj = await _get_electricity_projection(tid, tenant_data)
            
            text += "\n"
            if proj["n"] > 0:
                text += M.MYSTATUS_ELECTRICITY_ROW.format(
                    daily_rate=proj["daily_rate"],
                    depletion_date=proj["depletion_date"],
                    days_left=proj["days_remaining"]
                )
            else:
                text += M.MYSTATUS_ELECTRICITY_EMPTY
        except Exception as e:
            log.warning("mystatus_electricity_failed", error=str(e))

        await _reply(update, text)
    except Exception as exc:
        log.exception("cmd_mystatus_failed", telegram_id=_tg_id(update), error=str(exc))
        await _reply(update, "⚠️ *Mazao AI Logic Error*\nI encountered an internal error loading your personal status. Please try again.")


# ── /statement (P3-T5) ────────────────────────────────────────────────────────

async def cmd_statement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the most recent parsed statement summary."""
    try:
        tid = _tg_id(update)
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        
        if not tenant:
            await _reply(update, M.NOT_REGISTERED)
            return
            
        statement = await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: db.get_latest_statement(str(tenant["id"]))
        )
        
        if not statement:
            await _render_statement_empty_state(update)
            return

        # P3-T5: Summary format with null-safety (FAANG grade robustness)
        text = (
            "📑 *Raw Statement Totals*\n"
            f"Period: {statement.get('period', 'N/A')}\n"
            f"Parsed: {str(statement.get('parsed_at', '')).split('T')[0]}\n\n"
            f"📥 Total Inflows:  KES {float(statement.get('total_inflows') or 0):,.2f}\n"
            f"📤 Total Outflows: KES {float(statement.get('total_outflows') or 0):,.2f}\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Net Amount:    KES {float(statement.get('net') or 0):,.2f}*\n"
        )
        
        vat_est = float(statement.get("vat_estimate") or 0)
        if vat_est > 0:
            text += f"\n📋 *Est. VAT Liability: KES {vat_est:,.2f}*\n"
            text += "_(Note: This is a raw estimate. Use /report for AI-categorized business performance.)_"

        await _reply(update, text)
    except Exception as exc:
        log.exception("cmd_statement_failed", telegram_id=_tg_id(update), error=str(exc))
        # Check for missing table (Supabase/PostgREST PGRST204 or standard Postgres error)
        exc_str = str(exc).lower()
        if "statements" in exc_str and ("not find" in exc_str or "does not exist" in exc_str or "pgrst204" in exc_str):
            await _reply(update, "⚠️ *Database Migration Missing*\nPlease ask your engineer to run the Sprint 3 / Phase 3 migrations (specifically the `statements` table).")
        else:
            await _reply(update, "⚠️ *Mazao AI Logic Error*\nI encountered an internal error processing your statement.")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        tid = _tg_id(update)
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

        if not tenant:
            await _reply(update, M.NOT_REGISTERED)
            return

        # P7-T6: Feature Gating
        if not await is_feature_allowed(str(tenant["id"]), "report"):
            await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Business Report", upgrade_link="/upgrade"))
            return

        log.info("report_requested", telegram_id=tid, tenant_id=tenant["id"])

        # CQRS READ-HEAL PATH (P20-FIX_05)
        report = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_report(str(tenant["id"])))
        
        # Determine Narrative Presence
        has_narrative = bool(report and report.get("summary", {}).get("ai_narrative"))
        
        if report and has_narrative:
            # STATE 3: CACHE HIT (Full AI Narrative)
            summary = report.get("summary", {})
            narrative = summary.get("ai_narrative")
            created_at = report.get("created_at", datetime.now(timezone.utc).isoformat())
            # Normalize ISO string for strftime compatibility
            report_date = datetime.fromisoformat(created_at.replace("Z", "+00:00")).strftime("%d %b %Y")
            footer = f"\n\n_Analysis from {report_date}. Upload /statement for new month analysis._"
            await _reply(update, narrative + footer)
            return

        # STATE 2: AUTO-HEAL (Parsed data exists but no narrative)
        latest_stmt = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_statement(str(tenant["id"])))
        if latest_stmt or (report and not has_narrative):
            # T36: Mutex Check — prevent parallel analysis if one is already running
            if _pipeline_locks.get(str(tenant["id"])):
                await _reply(update, "🔄 *Analysis in Progress*\nI'm already working on your report. It will be ready in a few moments.")
                return

            await _reply(update, "🔄 *Generating your business report...*\nI found your parsed statement data. Please wait while I analyze it.")
            context.application.create_task(_run_pipeline_and_reply(update, context, tenant))
            return

        # STATE 1: MISSING DATA
        await _reply(update, "📭 *No Statement Yet*\nUpload your M-Pesa CSV via /statement to get started.")

    except Exception as exc:
        log.exception("cmd_report_failed", telegram_id=_tg_id(update), error=str(exc))
        await _reply(update, "⚠️ *Mazao AI Logic Error*\nI encountered an internal error preparing your report. Please try again.")
    except Exception as exc:
        log.exception("cmd_report_failed", telegram_id=_tg_id(update), error=str(exc))
        await _reply(update, "⚠️ *Mazao AI Logic Error*\nI encountered an internal error preparing your report. Please try again.")


async def awaiting_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processes electricity token entry (Full SMS or Quick entry)."""
    tid = _tg_id(update)
    text = (update.message.text or "").strip()

    try:
        # ── P16-FIX-FINAL: KPLC Token SMS Parser ─────────────────────────
        # Mode A: full KPLC SMS paste — all 7 fields extracted via pure helper
        # Mode B: legacy short format — graceful degradation, no cost breakdown
        parsed = _parse_kplc_sms(text)

        # Fields populated by whichever mode succeeds
        meter_number = None
        token_number = None
        token_amount = None
        other_charges = None
        tier = None
        rate_per_unit_stored = None
        units = None
        p_date = None
        amount_paid = None
        is_full_sms = False

        if parsed:
            # ── Mode A: Full KPLC SMS ─────────────────────────────────
            is_full_sms = True
            meter_number  = parsed["meter_number"]
            token_number  = parsed["token_number"]
            units         = parsed["units"]
            amount_paid   = parsed["amount_paid"]
            token_amount  = parsed["token_amount"]
            other_charges = parsed["other_charges"]
            p_date        = parsed["purchase_date"]

            # Deduplication: block double-entry of same physical token
            try:
                dup_check = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: db.get_client().table("token_entries")
                    .select("id, purchase_date")
                    .eq("token_number", token_number)
                    .maybe_single()
                    .execute()
                )
                if dup_check.data:
                    existing_date = str(dup_check.data.get("purchase_date", "unknown"))[:10]
                    await _reply(
                        update,
                        f"⚡ *Token already recorded!*\n"
                        f"Token `{token_number}` was logged on {existing_date}.\n"
                        f"No duplicate entry created."
                    )
                    await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
                    return
            except Exception as dup_exc:
                # Pre-migration: token_number column may not exist yet — skip dedup safely
                log.warning("dedup_check_skipped", error=str(dup_exc))

            # Derive tariff tier using pure helper (uses KPLC_TARIFF_TIERS constant)
            rate_per_unit_stored = round(token_amount / units, 4) if units > 0 else 0
            tier = _detect_tariff_tier(rate_per_unit_stored)
            log.info(
                "kplc_sms_parsed",
                meter=meter_number, units=units, amount=amount_paid,
                token_amount=token_amount, tariff=tier["key"],
                rate=round(rate_per_unit_stored, 2),
            )
        else:
            # ── Mode B: Legacy short format — "units date [amount]" ───
            parts = text.split()
            if len(parts) < 2:
                await _reply(update, M.TOKEN_ENTRY_PROMPT)
                return

            units = float(parts[0].replace(",", ""))
            d_str = parts[1]

            try:
                from dateutil import parser as date_parser
                p_date = date_parser.parse(d_str, dayfirst=True).date()
                if p_date.year < 2000 or p_date.year > 2100:
                    raise ValueError("invalid_year")
            except Exception as e:
                log.error("token_date_parse_failed", input=d_str, error=str(e))
                await _reply(update, "❌ *Invalid Date*\nPlease use DD/MM/YYYY. Example: `22/04/2026` or `22/4/2026`")
                return

            if len(parts) >= 3:
                try:
                    amount_paid = float(parts[2].replace(",", ""))
                except ValueError:
                    pass

        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

        # ── Store in token_entries ─────────────────────────────────────
        insert_data = {
            "tenant_id":     str(tenant["id"]),
            "units":         units,
            "purchase_date": p_date.isoformat(),
            "amount_paid":   amount_paid,
        }
        # P16-FIX-FINAL: Add full SMS fields (nullable — backward compatible)
        if is_full_sms:
            insert_data["meter_number"]  = meter_number
            insert_data["token_number"]  = token_number
            insert_data["token_amount"]  = token_amount
            insert_data["other_charges"] = other_charges
            insert_data["tariff_tier"]   = tier["label"] if tier else None
            insert_data["rate_per_unit"] = rate_per_unit_stored

        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("token_entries").insert(insert_data).execute()
            )
        except Exception as insert_exc:
            # Handle missing columns gracefully (pre-migration)
            exc_str = str(insert_exc).lower()
            # P17-T2H: Harden guard to include all optional columns that might be missing in live DB
            if any(col in exc_str for col in ["meter_number", "token_number", "token_amount", "other_charges", "tariff_tier", "rate_per_unit", "amount_paid"]):
                log.warning("new_columns_missing_fallback", error=str(insert_exc))
                # Retry with basic fields only (guaranteed by schema.sql)
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: db.get_client().table("token_entries").insert({
                        "tenant_id": str(tenant["id"]),
                        "units": units,
                        "purchase_date": p_date.isoformat(),
                    }).execute()
                )
            else:
                raise insert_exc
        
        # ── Hybrid Projection Math ────────────────────────────────────
        token_resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db.get_client().table("token_entries")
            .select("units, purchase_date")
            .eq("tenant_id", str(tenant["id"]))
            .order("purchase_date", desc=True)
            .execute()
        )
        readings = token_resp.data or []
        n = len(readings)
        
        # Calculate rates — unpack tuple from updated estimator
        h_type = tenant.get("household_type") or "standard"
        pop_rate = estimator.get_population_baseline(h_type)
        pers_rate, n_valid = estimator.calculate_weighted_personal_rate(readings)

        # Daily Rate — pass n_valid_intervals explicitly (P16-FIX-01-FINAL)
        daily_rate = estimator.blend_rates(pers_rate, pop_rate, n, n_valid)
        if daily_rate <= 0:
            daily_rate = pop_rate

        # ── Carry-over Balance Logic (P16-FIX-FINAL) ──────────────────
        # Instead of assuming the user is at 0, we estimate remaining units.
        total_units_for_projection = units
        if len(readings) >= 2:
            prev = readings[1]
            p_date_raw = prev["purchase_date"]
            p_date = datetime.fromisoformat(p_date_raw.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            
            # How many days since the last purchase?
            # Safety: if token date is in future (test data), treat as 0.01 days
            elapsed_seconds = (now - p_date).total_seconds()
            elapsed_days = max(0.01, elapsed_seconds / 86400)
            
            # Estimate remaining units: (Prev Units - Consumed)
            prev_units = float(prev["units"])
            consumed = elapsed_days * daily_rate
            remaining = max(0, prev_units - consumed)
            
            total_units_for_projection += remaining
            log.info("carry_over_applied", new=units, remaining=round(remaining, 2), total=round(total_units_for_projection, 2))

        # P16-FIX-FINAL: Enterprise Rounding
        days_remaining = estimator.calculate_days_remaining(total_units_for_projection, daily_rate)
        if total_units_for_projection > 0 and days_remaining == 0:
            days_remaining = 1
        depletion_date = (datetime.now(timezone.utc) + timedelta(days=days_remaining)).strftime("%d %b %Y")
        
        # Confidence Info
        conf = estimator.get_confidence_info(n)
        src_label = estimator.get_source_label(n, h_type)
        
        # Anomaly Detection
        anomaly_warning = ""
        if n >= 3 and pers_rate:
            if n >= 2:
                d1 = datetime.fromisoformat(readings[0]["purchase_date"].replace("Z", "+00:00")).date()
                d2 = datetime.fromisoformat(readings[1]["purchase_date"].replace("Z", "+00:00")).date()
                gap_days = (d1 - d2).days
                if gap_days > 0:
                    this_rate = units / gap_days
                    if estimator.detect_anomaly(this_rate, readings[1:]):
                        anomaly_warning = "\n\n⚠️ *Anomaly Detected:* This reading seems unusual compared to your history."

        # Range/Confidence Interval
        range_text = ""
        interval = estimator.confidence_interval(readings, daily_rate)
        if interval:
            range_text = f"\nRange: {interval[0]} - {interval[1]} units/day"

        # Encouragement
        encouragement = ""
        if n == 1: encouragement = "\n_Recording more tokens will improve accuracy._"
        elif 2 <= n <= 4: encouragement = "\n_Learning your patterns..._"
        elif 5 <= n <= 9: encouragement = "\n_High accuracy achieved._"
        
        # ── Cost Breakdown (P16-FIX-FINAL) ───────────────────────────
        # P17-T1-FIX: Centralize cost breakdown in estimator with 52.5% D1 ratio.
        breakdown_text = ""
        if amount_paid and amount_paid > 0:
            t_key = tier["key"] if (is_full_sms and tier) else "D1"
            bd = estimator.get_cost_breakdown(amount_paid, tariff=t_key, actual_tkn=token_amount if is_full_sms else None)
            
            elec_pct = bd["percentage"]
            rate_display = round(bd["electricity"] / units, 2) if units > 0 else 0
            tier_label = tier["label"] if (is_full_sms and tier) else "D1 Lifeline (Estimated)"

            breakdown_text = (
                f"\n\n💡 *Cost Breakdown{' (from your token)' if is_full_sms else ''}:*\n"
                f"Actual electricity: KES {bd['electricity']:,.2f} ({elec_pct}%)\n"
                f"Taxes & levies:     KES {bd['taxes']:,.2f} ({round(100-elec_pct, 1)}%)\n"
                f"Your rate: KES {rate_display}/unit — {tier_label}\n"
                f"_Levy charges vary monthly per EPRA gazette._\n\n"
                f"Only {elec_pct}% of your KES {amount_paid:,.0f} was electricity."
            )
            if not is_full_sms:
                breakdown_text += "\n\n💡 _Paste the full KPLC token SMS next time for a more accurate breakdown._"

        await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))

        # P17-T4J: Post-usage nudge (Conversion Trigger 2)
        await _maybe_send_nudge(
            update, context, 
            M.NUDGE_POST_USAGE_VALUE, 
            condition=tenant.get("plan") in ("free", "trial")
        )

        # P16-T1: AI engagement tip (safe, optional, free-tier LLM)
        tip_text = ""
        try:
            from apps.agent import tips as tips_engine
            anomaly_flag = bool(anomaly_warning)
            if tips_engine.should_show_tip(n, anomaly_flag):
                tip = await tips_engine.generate_tip({
                    "units":           units,
                    "household_type":  h_type,
                    "daily_rate":      daily_rate,
                    "days_remaining":  days_remaining,
                    "entry_count":     n,
                    "amount_paid":     amount_paid,
                    "personal_rate":   pers_rate,
                    "population_rate": pop_rate,
                    "anomaly":         anomaly_flag,
                    # P16-FIX-FINAL: richer context when full SMS parsed
                    "token_amount":    token_amount if is_full_sms else None,
                    "other_charges":   other_charges if is_full_sms else None,
                    "tariff_tier":     tier["label"] if (is_full_sms and tier) else None,
                })
                if tip:
                    tip_text = f"\n\n💡 _{tip}_"
        except Exception as _tip_exc:
            log.warning("tip_pipeline_skipped", error=str(_tip_exc))

        response = (
            f"⚡ *Token Recorded!*\n\n"
            f"Units: {units}\n"
            f"Daily Rate: {daily_rate} units ({src_label})\n"
            f"Est. Depletion: {depletion_date}\n"
            f"Days Left: {days_remaining}\n"
            f"Confidence: {conf['bar']} {conf['label']}"
            f"{range_text}"
            f"{anomaly_warning}"
            f"{breakdown_text}"
            f"{tip_text}"
            f"{encouragement}"
        )
        
        await _reply(update, response)
    except ValueError:
        await _reply(update, M.TOKEN_INVALID_VALUE)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles uploaded statement files (CSV, PDF, TXT)."""
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)
    
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    doc = update.message.document
    if doc.file_size > 10 * 1024 * 1024:
        await _reply(update, "⚠️ File is too large. Max size is 10MB.")
        return

    mime = doc.mime_type
    from pathlib import Path
    ext = Path(doc.file_name).suffix.lower()
    
    fmt = None
    if mime == "text/csv" or ext == ".csv":
        fmt = "csv"
    elif mime == "application/pdf" or ext == ".pdf":
        await _reply(update, M.UNSUPPORTED_FILE_FORMAT)
        return
    elif mime == "text/plain" or ext == ".txt":
        fmt = "sms"
    
    if not fmt:
        await _reply(update, M.UNSUPPORTED_FILE_FORMAT)
        return

    await _reply(update, M.STATEMENT_RECEIVED_PARSING)

    try:
        file = await context.bot.get_file(doc.file_id)
        file_bytes = await file.download_as_bytearray()
        
        txs = mpesa_parser.parse(bytes(file_bytes), fmt)
        
        if not txs:
            await _reply(update, M.STATEMENT_PARSE_FAILED)
            return

        # P3-T1/T4: Calculate and store summary
        inflows = sum(t.amount for t in txs if t.transaction_type == TransactionType.C2B)
        outflows = sum(t.amount for t in txs if t.transaction_type == TransactionType.B2C)
        net = inflows - outflows
        
        # Simple VAT estimate: 16% of inflows for business tenants
        vat_estimate = 0
        if tenant.get("user_type") == "business":
            vat_estimate = inflows * 0.16
            
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        if txs:
            # Try to get period from transactions
            period = txs[0].timestamp.strftime("%Y-%m")

        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db.save_statement(
                tenant_id=str(tenant["id"]),
                period=period,
                total_inflows=inflows,
                total_outflows=outflows,
                net=net,
                vat_estimate=vat_estimate
            )
        )

        # P20-FIX_05: Persist parsed transactions to live_transactions for auto-healing support
        try:
            insert_batch = []
            for t in txs:
                insert_batch.append({
                    "tenant_id": str(tenant["id"]),
                    "trans_id": t.mpesa_ref,
                    "trans_time": t.timestamp.isoformat(),
                    "amount": float(t.amount),
                    "msisdn": t.phone or "",
                    "first_name": t.name or "Guest",
                    "bill_ref": t.shortcode or "",
                    "provider": "csv_upload"
                })
            
            # Use upsert with trans_id conflict resolution to prevent duplicate key errors on re-upload
            if insert_batch:
                await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: db.get_client().table("live_transactions").upsert(insert_batch, on_conflict="trans_id").execute()
                )
        except Exception as e:
            log.warning("csv_persistence_failed", tenant_id=tenant["id"], error=str(e))

        await _reply(update, M.STATEMENT_PARSE_SUCCESS.format(count=len(txs)))
        
        # CQRS WRITE GUARD: Check for existing report for this period (P20-FIX_03)
        existing = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_report_by_period(str(tenant["id"]), period))
        if existing and existing.get("summary", {}).get("ai_narrative"):
             await _reply(update, f"✅ *Report Already Exists*\nYou already have a {period} report. Use /report to view it or /refresh to regenerate.")
             return
        
        # Run pipeline with extracted transactions
        context.application.create_task(
            _run_pipeline_and_reply(
                update, 
                context, 
                tenant, 
                custom_transactions=txs,
                trigger_source="telegram_document"
            )
        )
        
    except Exception as exc:
        log.exception("document_parsing_failed", telegram_id=tid, error=str(exc))
        await _reply(update, M.STATEMENT_PARSE_FAILED)


async def cmd_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """CQRS CACHE CLEAR: Deletes the latest report to allow regeneration (P20-FIX_03)."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    # Delete latest report row
    latest = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_report(str(tenant["id"])))
    if latest:
        await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: db.get_client().table("reports").delete().eq("id", latest["id"]).execute()
        )
    
    await _reply(update, "♻️ *Cache Cleared*\nRegenerating your report. Please upload your /statement to proceed.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles uploaded photos/screenshots for OCR processing."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    photo = update.message.photo[-1] # Best resolution
    mime = "image/jpeg"
    
    await _reply(update, "📸 *Image received. Scanning for M-Pesa details...*")

    try:
        file = await context.bot.get_file(photo.file_id)
        file_bytes = await file.download_as_bytearray()
        
        # Dispatch to our Document Intelligence engine (non-blocking if we scale it out later)
        extracted = await asyncio.get_event_loop().run_in_executor(None, lambda: ocr_engine.process_image(bytes(file_bytes)))
        
        if not extracted:
            await _reply(update, "❌ *Failed to extract transaction fields from this image. Please ensure it's a clear M-Pesa screenshot.*")
            return

        # Map to State schema
        try:
            ts = datetime.strptime(extracted["timestamp"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            ts = datetime.now(timezone.utc)
            
        t_type = getattr(TransactionType, extracted.get("transaction_type", "UNKNOWN"), TransactionType.UNKNOWN)

        tx = RawTransaction(
            mpesa_ref=extracted["mpesa_ref"],
            amount=extracted["amount"],
            phone="",
            name=extracted["sender_name"],
            shortcode="",
            transaction_type=t_type,
            timestamp=ts
        )
        
        await _reply(update, f"✅ *Successfully read transaction {tx.mpesa_ref} for KES {tx.amount:,.2f}.*\n\nReconciling...")
        
        # Run pipeline with extracted transactions
        context.application.create_task(
            _run_pipeline_and_reply(
                update, 
                context, 
                tenant, 
                custom_transactions=[tx],
                trigger_source="telegram_photo"
            )
        )
        
    except Exception as exc:
        log.exception("photo_ocr_failed", telegram_id=tid, error=str(exc))
        await _reply(update, "❌ *OCR Engine encountered an error. Please try a different screenshot or upload a CSV document.*")


async def _run_pipeline_and_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tenant: dict,
    custom_transactions: Optional[list] = None,
    trigger_source: str = "telegram_command",
) -> None:
    """
    Runs the agent pipeline and sends the report back.
    Executes in background — never blocks the handler.
    """
    tid = tenant["telegram_id"]
    tenant_uuid = str(tenant["id"])

    # P20-FIX_06: Mutex Lock Entrance
    if _pipeline_locks.get(tenant_uuid):
        log.info("pipeline_lock_active_ignoring", tenant_id=tenant_uuid)
        return
    
    _pipeline_locks[tenant_uuid] = True

    try:
        from apps.agent.pipeline import run_pipeline

        # P19-T24: Freshness-Aware Data Routing & Dynamic Period Targeting
        # Fetch status markers first to determine precedence and target period
        latest_report = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_report(str(tenant["id"])))
        latest_stmt = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_statement(str(tenant["id"])))

        # T34: Normalize timestamps to timezone-aware datetime objects for deterministic comparison.
        # Raw Supabase ISO strings may use 'Z' or '+00:00' — either could break string comparison.
        def _parse_ts(raw: str | None) -> datetime | None:
            if not raw:
                return None
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
            except (ValueError, TypeError):
                return None

        report_time: datetime | None = _parse_ts(latest_report.get("created_at") if latest_report else None)
        stmt_time: datetime | None = _parse_ts(latest_stmt.get("parsed_at") if latest_stmt else None)

        # Determine target period (P19-T27: Moved to function scope for universal access)
        now = datetime.now(timezone.utc)
        target_period = now.strftime("%Y-%m")
        
        # T32 Fix: target_period follows the most recently generated data artifact
        if stmt_time and report_time:
            if stmt_time > report_time:
                target_period = latest_stmt.get("period", target_period)
            else:
                target_period = latest_report.get("period", target_period)
        elif stmt_time:
            target_period = latest_stmt.get("period", target_period)
        elif report_time:
            target_period = latest_report.get("period", target_period)

        # T32: Fetch the specific report for the target period
        period_report = await asyncio.get_event_loop().run_in_executor(
            None, lambda: db.get_report_by_period(str(tenant["id"]), target_period)
        )


        # Use passed transactions (from current upload) or fetch from DB
        txs = custom_transactions
        if not txs:
            try:
                # Convert "YYYY-MM" to ISO start of month
                dt = datetime.strptime(target_period, "%Y-%m")
                month_start = dt.replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            
            try:
                # Query live transactions for the target period
                live_resp = db.get_client().table("live_transactions").select("*").eq("tenant_id", str(tenant["id"])).gte("trans_time", month_start).execute()
                if live_resp and live_resp.data:
                    txs = []
                    for lt in live_resp.data:
                        tx_time = datetime.fromisoformat(lt["trans_time"].replace("Z", "+00:00"))
                        name = lt["first_name"] or "Guest"
                        tx_type = TransactionType.C2B
                        
                        # T38: Audit Fix — apply T37 classification to live_feed path
                        tx_type = mpesa_parser.detect_internal_transfer(name, tx_type)
                        
                        txs.append(RawTransaction(
                            mpesa_ref=lt["trans_id"],
                            amount=float(lt["amount"]),
                            phone=lt["msisdn"] or "",
                            name=name,
                            shortcode=lt["bill_ref"] or "",
                            transaction_type=tx_type,
                            timestamp=tx_time
                        ))
                    trigger_source = "live_feed"
            except Exception as e:
                # P19-T17/T18: SCHEMA DRIFT CONTRACT — DEGRADED MODE
                log.warning("live_transactions_query_failed", error=str(e), tenant_id=tenant["id"])
                txs = []

        # P19-T21: Tiered Data Source Routing
        # 1. If we have transactions (custom or live), run the pipeline
        if txs:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: run_pipeline(
                    tenant_id=str(tenant["id"]),
                    raw_transactions=txs,
                    triggered_by=trigger_source,
                ),
            )
            # T36: Enforce pipeline execution authority — check explicit failure status.
            if result.pipeline_failed:
                failure_detail = "; ".join(result.errors) if result.errors else "Unknown pipeline failure"
                log.error("pipeline_execution_failed", tenant_id=tenant["id"], errors=result.errors)
                await context.bot.send_message(
                    chat_id=tid,
                    text=f"⚠️ *Report Generation Failed*\n\n_{failure_detail}_\n\nPlease re-upload your /statement to retry.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

            # Language selection logic (P2-T4)
            lang = tenant.get("preferred_language", "en")
            report_text = result.report_text_sw if lang == "sw" else result.report_text_en
            
            if report_text:
                # 1. Persist report (T31/T35/T36: Authority First — Save before delivery)
                r = result.reconciliation
                stmt_id = latest_stmt.get("id") if latest_stmt else None
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: db.save_report(
                        tenant_id=str(tenant["id"]),
                        period=target_period,
                        summary={
                            "income": r.total_income if r else 0.0,
                            "expenses": r.total_expenses if r else 0.0,
                            "profit": r.net_profit if r else 0.0,
                            "flagged": r.flagged_count if r else 0,
                            "degraded": result.ai_degraded,
                            "statement_id": stmt_id,
                        },
                    )
                )

                # 2. Attempt delivery with formatting (P19-T21-FIX: Robust Retry on Markdown Error)
                try:
                    await context.bot.send_message(
                        chat_id=tid,
                        text=report_text,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception as send_err:
                    log.warning("telegram_markdown_failed", error=str(send_err), tenant_id=tenant["id"])
                    # Fallback to plain text delivery (Option A: Reliable Delivery Gate)
                    await context.bot.send_message(
                        chat_id=tid,
                        text=report_text,
                        parse_mode=None,
                    )
                
                # P17-T4J: Report value anchor nudge (Conversion Trigger 4)
                # T43: Only nudge free-tier users who have not upgraded.
                await _maybe_send_nudge(
                    update, context, 
                    M.NUDGE_REPORT_VALUE_ANCHOR, 
                    condition=tenant.get("plan") == "free"
                )
                return

            else:
                await context.bot.send_message(
                    chat_id=tid,
                    text=M.PIPELINE_ERROR,
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

        # 2. Tiered Fallback: Statement Summary vs AI Report
        # T32: Strict Period-Scoped Selection
        
        # Scenario A: Valid computed report exists for the target period
        if period_report:
            summary = period_report.get("summary", {})
            period = period_report.get("period", "Current")
            is_degraded = summary.get("degraded", False)

            # T35: Lineage-based freshness authority.
            # A report is FRESH iff its summary.statement_id matches the current latest statement.
            # Eliminates all timestamp comparison; ID equality is deterministic and timezone-safe.
            current_stmt_id = latest_stmt.get("id") if latest_stmt else None
            report_stmt_id = summary.get("statement_id")
            is_fresh: bool = bool(report_stmt_id and report_stmt_id == current_stmt_id)
            # Legacy fallback: if report predates T35 (no statement_id), fall back to _parse_ts comparison.
            if not report_stmt_id and not is_degraded:
                report_created_at: datetime | None = _parse_ts(period_report.get("created_at"))
                if report_created_at and stmt_time:
                    is_fresh = report_created_at >= stmt_time
                elif report_created_at and not stmt_time:
                    is_fresh = True

            if is_degraded:
                header = f"⚠️ *Degraded AI Report ({period})*"
                footer = "_Report generation partially failed. Upload a new /statement to retry._"
            elif is_fresh:
                header = f"📊 *Business Report ({period})*"
                footer = "_Analysis is current for your latest uploaded statement._"
            else:
                header = f"📊 *Latest AI Report ({period})*"
                footer = "_Showing last generated AI insights. For a fresh analysis, upload a new /statement._"

            text = (
                f"{header}\n\n"
                f"💰 Total Income:  KES {summary.get('income', 0):,.2f}\n"
                f"💸 Total Expenses: KES {summary.get('expenses', 0):,.2f}\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"📈 *Net Profit:    KES {summary.get('profit', 0):,.2f}*\n\n"
                f"{footer}"
            )
            await context.bot.send_message(chat_id=tid, text=text, parse_mode=ParseMode.MARKDOWN)
            return

        # Scenario B: No report exists for target period, but a statement summary does
        if latest_stmt and latest_stmt.get("period") == target_period:
            text = (
                f"📊 *Statement Summary ({latest_stmt.get('period', 'Latest')})*\n\n"
                f"💰 Total Inflows:  KES {float(latest_stmt.get('total_inflows') or 0):,.2f}\n"
                f"💸 Total Outflows: KES {float(latest_stmt.get('total_outflows') or 0):,.2f}\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"📈 *Net Amount:    KES {float(latest_stmt.get('net') or 0):,.2f}*\n\n"
                "_M-Pesa live feed unavailable for this period. Upload /statement again to refresh AI insights._"
            )
            await context.bot.send_message(chat_id=tid, text=text, parse_mode=ParseMode.MARKDOWN)
            return

        # 4. Ultimate Fallback: Empty State (No data sources found)
        if trigger_source == "telegram_command":
            await _render_report_empty_state(update)
        else:
            await context.bot.send_message(
                chat_id=tid,
                text=M.REPORT_STATEMENT_REQUIRED,
                parse_mode=ParseMode.MARKDOWN,
            )
        return

    except Exception as exc:
        log.exception("pipeline_failed", telegram_id=tid, error=str(exc))
        await context.bot.send_message(
            chat_id=tid,
            text=M.PIPELINE_ERROR,
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        # P20-FIX_06: Mutex Lock Release
        _pipeline_locks.pop(tenant_uuid, None)
        log.info("pipeline_lock_released", tenant_id=tenant_uuid)


# ── /vat ──────────────────────────────────────────────────────────────────────

async def cmd_vat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    # Phase 18 T8K: Trust Fix - Remove fabricated VAT outputs
    statement = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_statement(str(tenant["id"])))
    
    # We currently do not have granular invoice/receipt OCR to determine real taxable inputs/outputs.
    # Therefore, any calculation is fabricated. Return safe unavailable state.
    await _reply(update, M.VAT_UNAVAILABLE)


# ── /kra ──────────────────────────────────────────────────────────────────────

async def cmd_kra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    today = datetime.now(timezone.utc)
    next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)

    obligations_tax = [
        {"type": "VAT", "due_day": 20},
        {"type": "PAYE", "due_day": 9},
    ]
    obligations_social = [
        {"type": "NSSF", "due_day": obligations.NSSF_DUE_DAY},
        {"type": "NHIF/SHA", "due_day": 9},
    ]

    text = M.KRA_OBLIGATIONS_HEADER
    
    # 1. Tax (KRA) Group
    text += M.KRA_OBLIGATION_GROUP.format(icon="🧾", group_name="Tax (KRA)")
    for ob in obligations_tax:
        due_date = next_month.replace(day=ob["due_day"])
        days_left = (due_date.date() - today.date()).days
        overdue = days_left < 0
        overdue_flag = "\n   ❗ *OVERDUE*" if overdue else ""

        text += M.KRA_OBLIGATION_ROW.format(
            obligation_type=ob["type"],
            due_date=due_date.strftime("%d %b %Y"),
            days_left=abs(days_left) if not overdue else f"{abs(days_left)} days ago",
            overdue_flag=overdue_flag,
        )

    # 2. Payroll & Social Group
    text += M.KRA_OBLIGATION_GROUP.format(icon="👥", group_name="Payroll & Social")
    for ob in obligations_social:
        due_date = next_month.replace(day=ob["due_day"])
        days_left = (due_date.date() - today.date()).days
        overdue = days_left < 0
        overdue_flag = "\n   ❗ *OVERDUE*" if overdue else ""

        # P19-T9H: Robust NSSF detection and trust-safe penalty display
        if ob["type"] == "NSSF":
            text += (
                f"🛡️ NSSF\n"
                f"Due: {due_date.strftime('%d %b %Y')}\n"
                f"{obligations.NSSF_RULE}\n"
                f"{obligations.NSSF_PENALTY}\n"
                f"Days left: {abs(days_left) if not overdue else f'{abs(days_left)} days ago'}{overdue_flag}\n\n"
            )
        else:
            text += M.KRA_OBLIGATION_ROW.format(
                obligation_type=ob["type"],
                due_date=due_date.strftime("%d %b %Y"),
                days_left=abs(days_left) if not overdue else f"{abs(days_left)} days ago",
                overdue_flag=overdue_flag,
            )

    await _reply(update, text)

# ── /tokens (P4-T1) ─────────────────────────────────────────────────────────

async def _get_electricity_projection(tid: int, tenant: Dict) -> Dict:
    """P18-T1: Unified projection logic for electricity."""
    import math as _math
    
    resp = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: db.get_client().table("token_entries")
        .select("units, purchase_date")
        .eq("tenant_id", str(tenant["id"]))
        .order("purchase_date", desc=True)
        .execute()
    )
    
    history = resp.data or []
    n = len(history)
    
    h_type = tenant.get("household_type", "standard")
    pop_rate = estimator.get_population_baseline(h_type)
    pers_rate, n_valid = estimator.calculate_weighted_personal_rate(history)
    daily_rate = estimator.blend_rates(pers_rate, pop_rate, n, n_valid)
    if daily_rate <= 0: daily_rate = pop_rate
    
    now = datetime.now(timezone.utc)
    
    if n > 0:
        latest = history[0]
        l_date = datetime.fromisoformat(latest["purchase_date"].replace("Z", "+00:00"))
        if l_date.tzinfo is None: l_date = l_date.replace(tzinfo=timezone.utc)
        
        days_since = (now - l_date).days
        # Units remaining = units - (rate * days_since)
        units_remaining = max(0, latest["units"] - (daily_rate * days_since))
        days_rem = estimator.calculate_days_remaining(units_remaining, daily_rate)
        depletion_date = (now + timedelta(days=max(0, days_rem))).strftime("%d %b %Y")
        
        return {
            "n": n,
            "daily_rate": daily_rate,
            "units_remaining": units_remaining,
            "days_remaining": days_rem,
            "depletion_date": depletion_date,
            "n_valid": n_valid
        }
    else:
        return {"n": 0, "daily_rate": pop_rate, "units_remaining": 0, "days_remaining": 0, "depletion_date": "N/A", "n_valid": 0}


async def _render_tokens_status(query_or_update: Update | CallbackQuery, tid: int, tenant: Dict) -> None:
    """Renders the status card for electricity tokens."""
    proj = await _get_electricity_projection(tid, tenant)
    h_type = tenant.get("household_type", "standard")
    
    src_label = estimator.get_source_label(proj["n"], h_type)
    conf = estimator.get_confidence_info(proj["n"])
    
    # Encouragement
    encouragement = ""
    if proj["n"] == 1: encouragement = "Recording more tokens will improve accuracy."
    elif 2 <= proj["n"] <= 4: encouragement = "Learning your patterns..."
    elif proj["n"] >= 5: encouragement = "High accuracy achieved."

    keyboard = [
        [InlineKeyboardButton("➕ Log New Token", callback_data="tokens_add_new")],
        [InlineKeyboardButton("🏠 Change Home Type", callback_data="tokens_change_htype")]
    ]
    
    text = M.TOKENS_STATUS_CARD.format(
        units_remaining=proj["units_remaining"],
        daily_rate=proj["daily_rate"],
        source_label=src_label,
        depletion_date=proj["depletion_date"],
        days_left=proj["days_remaining"],
        bar=conf["bar"],
        label=conf["label"],
        encouragement=encouragement
    )

    if hasattr(query_or_update, "edit_message_text"):
        # Callback query
        await query_or_update.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        # Update (command)
        await _reply(query_or_update, text, reply_markup=InlineKeyboardMarkup(keyboard))


async def cmd_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    # P7-T6: Feature Gating
    if not await is_feature_allowed(str(tenant["id"]), "utility_tracking"):
        await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Token Tracking", upgrade_link="/upgrade"))
        return

    # P15-T1A: Household type capture (Once per user)
    h_type = tenant.get("household_type")
    if not h_type:
        reply_markup = _get_htype_keyboard()
        await _reply(
            update, 
            "🏠 *Before we record your tokens, what best describes your home?*\n\nThis helps us provide accurate predictions from day one.", 
            reply_markup=reply_markup
        )
        return
        
    # P18-T1: Show status card first if entries exist
    proj = await _get_electricity_projection(tid, tenant)
    
    if proj["n"] > 0:
        await _render_tokens_status(update, tid, tenant)
    else:
        # Zero entries: go straight to prompt as current
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_tokens"))
        await _reply(update, M.TOKEN_ENTRY_PROMPT)


# ── Gas Helpers (P17-T1D) ──────────────────────────────────────────────────

async def _get_gas_projection(tid: int, tenant: Dict, refill_kg: float = 0) -> Dict:
    """Calculates burn rate and depletion projection for gas.
    
    If refill_kg > 0, it assumes a refill was just performed today.
    Otherwise, it calculates remaining days based on the latest historical entry.
    """
    gas_resp = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: db.get_client().table("gas_entries")
        .select("amount_kg, purchase_date")
        .eq("tenant_id", str(tenant["id"]))
        .order("purchase_date", desc=True)
        .execute()
    )
    
    history = [{"units": r["amount_kg"], "purchase_date": r["purchase_date"]} for r in gas_resp.data]
    n = len(history)
    
    # Baseline & Personal Rate
    h_type = tenant.get("household_type")
    pop_rate = estimator.get_gas_population_baseline(h_type)
    pers_rate, n_valid = estimator.calculate_weighted_personal_rate(history)
    daily_rate = estimator.blend_rates(pers_rate, pop_rate, n, n_valid)
    if daily_rate <= 0: daily_rate = pop_rate
    
    # Calculate Days Remaining
    now = datetime.now(timezone.utc)
    
    if refill_kg > 0:
        # Scenario A: Just refilled today
        days_rem = estimator.calculate_days_remaining(refill_kg, daily_rate)
    elif n > 0:
        # Scenario B: Standing status from history
        latest = history[0]
        l_date = datetime.fromisoformat(latest["purchase_date"].replace("Z", "+00:00"))
        if l_date.tzinfo is None: l_date = l_date.replace(tzinfo=timezone.utc)
        
        days_since = (now - l_date).days
        days_rem = estimator.calculate_days_remaining(latest["units"] - (daily_rate * days_since), daily_rate)
    else:
        # Scenario C: No data
        return {"n": 0, "daily_rate": pop_rate, "days_remaining": 0, "depletion_date": "N/A", "history": []}

    depletion_date = (now + timedelta(days=max(0, days_rem))).strftime("%d %b %Y")
    
    return {
        "n": n,
        "daily_rate": daily_rate,
        "days_remaining": days_rem,
        "depletion_date": depletion_date,
        "history": gas_resp.data[:3] # Last 3 for the table
    }


# ── /gas (P17-T1) ────────────────────────────────────────────────────────────

async def _render_gas_status(query_or_update: Update | CallbackQuery, tid: int, tenant: Dict) -> None:
    """Renders the status card for gas."""
    proj = await _get_gas_projection(tid, tenant)
    
    keyboard = [
        [InlineKeyboardButton("➕ Log New Gas Reading", callback_data="gas_add_new")],
        [InlineKeyboardButton("🏠 Change Home Type", callback_data="gas_change_htype")]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    # Build history table
    rows = []
    for r in proj["history"]:
        d = datetime.fromisoformat(r["purchase_date"].replace("Z", "+00:00")).strftime("%d/%m")
        rows.append(f"├ {d}: {r['amount_kg']}kg")
    history_table = "\n".join(rows) if rows else "No entries yet."
    
    days_text = f"{proj['days_remaining']} days" if proj['days_remaining'] > 0 else "⚠️ Empty or Overdue"
    
    # P17-T1G: Source explanation
    h_type = tenant.get("household_type", "standard")
    src_label = estimator.get_gas_source_label(proj["n"], h_type)
    conf = estimator.get_confidence_info(proj["n"])
    conf_text = f"Confidence: {conf['bar']} {conf['label']}"

    text = M.GAS_DASHBOARD.format(
        depletion_date=proj["depletion_date"],
        days_remaining=days_text,
        daily_rate=proj["daily_rate"],
        source_explanation=src_label,
        history_table=history_table,
        confidence_info=conf_text
    )

    if hasattr(query_or_update, "edit_message_text"):
        await query_or_update.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await _reply(query_or_update, text, reply_markup=markup)

async def cmd_gas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    if not await is_feature_allowed(str(tenant["id"]), "utility_tracking"):
        await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Gas Tracking", upgrade_link="/upgrade"))
        return
        
    # P15-T1A: Household type capture (Once per user)
    h_type = tenant.get("household_type")
    if not h_type:
        reply_markup = _get_htype_keyboard()
        await _reply(
            update, 
            "🏠 *Before we track your gas, what best describes your home?*\n\nThis helps us provide accurate predictions from day one.", 
            reply_markup=reply_markup
        )
        return
        
    # P17-T1D: Render Dashboard if history exists
    proj = await _get_gas_projection(tid, tenant)
    
    if proj["n"] > 0:
        await _render_gas_status(update, tid, tenant)
    else:
        # Zero entries: go straight to prompt as current
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_gas"))
        await _reply(update, M.GAS_SMS_PROMPT)


# ── /fuliza (P4-T2) ──────────────────────────────────────────────────────────

async def cmd_fuliza(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    # P7-T6: Feature Gating
    if not await is_feature_allowed(str(tenant["id"]), "utility_tracking"):
        await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Loan Tracking", upgrade_link="/upgrade"))
        return

    # P17-T5H: Dashboard-first flow — show status before prompt
    try:
        tenant_id_str = str(tenant["id"])
        rows = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db.get_client().table("fuliza_entries")
                .select("balance,due_date,code,access_fee")
                .eq("tenant_id", tenant_id_str)
                .order("created_at", desc=True)
                .limit(3)
                .execute()
        )
        if rows and hasattr(rows, "data") and isinstance(rows.data, list) and rows.data:
            today = datetime.now(timezone.utc).date()
            # Latest entry
            latest = rows.data[0]
            if not latest.get("due_date") or not isinstance(latest["due_date"], str):
                raise ValueError("Invalid due_date")
            l_due = datetime.strptime(latest["due_date"], "%Y-%m-%d").date()
            l_days = (l_due - today).days
            l_risk = ("🔴 OVERDUE" if l_days <= 0 else "🟠 HIGH" if l_days < 7
                      else "🟡 MEDIUM" if l_days <= 14 else "🟢 LOW")
            latest_section = (
                f"💰 *Outstanding:* KES {float(latest['balance']):,.2f}\n"
                f"📅 *Due:* {l_due.strftime('%d %b %Y')}\n"
                f"⏳ *Days Left:* {l_days}\n"
                f"{l_risk}"
            )
            # History lines
            history_parts = []
            for r in rows.data:
                if not r.get("due_date") or not isinstance(r["due_date"], str):
                    continue
                r_due = datetime.strptime(r["due_date"], "%Y-%m-%d").date()
                r_days = (r_due - today).days
                r_risk = ("🔴" if r_days <= 0 else "🟠" if r_days < 7
                          else "🟡" if r_days <= 14 else "🟢")
                history_parts.append(
                    f"• KES {float(r['balance']):,.2f} → {r_due.strftime('%d %b')} {r_risk}"
                )

            # P17-T5I: Pro-tier Intelligence Engine
            intel_section = ""
            if await is_feature_allowed(tenant_id_str, "fuliza_intelligence"):
                try:
                    month_start = today.replace(day=1).strftime("%Y-%m-%d")
                    last_30d = (today - timedelta(days=30)).strftime("%Y-%m-%d")
                    
                    stats = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: db.get_client().table("fuliza_entries")
                            .select("access_fee,created_at")
                            .eq("tenant_id", tenant_id_str)
                            .gte("created_at", last_30d)
                            .execute()
                    )
                    if stats and hasattr(stats, "data") and isinstance(stats.data, list):
                        monthly_burden = sum(float(r["access_fee"] or 0) for r in stats.data if r["created_at"] >= month_start)
                        usage_count = len(stats.data)
                        
                        # Pattern Signal (P17-T5I)
                        nudge_text = ""
                        if usage_count > 5:
                            nudge_text = M.FULIZA_INSIGHT_FREQUENT_USE
                            
                        intel_section = M.FULIZA_PRO_INTEL_SECTION.format(
                            monthly_burden=f"{monthly_burden:,.2f}",
                            usage_count=usage_count,
                            nudge=nudge_text
                        )
                except Exception as ex_intel:
                    log.warning("fuliza_intel_failed", error=str(ex_intel))

            await _reply(update, M.FULIZA_DASHBOARD.format(
                latest_section=latest_section,
                intel_section=intel_section,
                history_lines="\n".join(history_parts)
            ))
    except Exception:
        pass  # Fail open: show prompt even if dashboard fails

    await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_fuliza"))
    await _reply(update, M.FULIZA_SMS_PROMPT)


async def cmd_fuliza_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exit multi-entry Fuliza session."""
    tid = _tg_id(update)
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
    await _reply(update, M.FULIZA_SESSION_DONE)


# ── /subscribe & /subscriptions (P5-T1) ─────────────────────────────────────

async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    # P7-T6: Feature Gating
    if not await is_feature_allowed(str(tenant["id"]), "utility_tracking"):
        await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Subscription Alerts", upgrade_link="/upgrade"))
        return
        
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_sub_name"))
    await _reply(update, M.SUBSCRIBE_NAME_PROMPT)


async def cmd_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    try:
        subs = await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: db.get_client().table("subscriptions").select("*").eq("tenant_id", str(tenant["id"])).execute()
        )
        
        if not subs or not subs.data:
            await _reply(update, M.SUBSCRIPTIONS_EMPTY)
            return
        
        text = M.SUBSCRIPTIONS_LIST_HEADER
        today = datetime.now(timezone.utc)
        
        for s in subs.data:
            # Calculate next renewal date
            day = s["renewal_day"]
            try:
                next_date = today.replace(day=day)
                if today.day >= day:
                    # Move to next month
                    next_date = (next_date + timedelta(days=32)).replace(day=day)
            except ValueError:
                # Handle Feb 29-31 if renewal_day is set high (schema restricts to 28 so should be safe)
                next_date = (today + timedelta(days=30)).replace(day=1)

            days_left = (next_date.date() - today.date()).days
            text += f"• *{s['name']}*: KES {s['amount_kes']:,.0f} (due {next_date.strftime('%d %b')}, *{days_left}d*)\n"
        
        await _reply(update, text)
    except Exception as exc:
        log.error("cmd_subscriptions_failed", error=str(exc))
        await _reply(update, "⚠️ *Error retrieving subscriptions.*\nPlease try again later.")


# ── /till (P6-T5) ─────────────────────────────────────────────────────────────

async def cmd_till(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        tid = _tg_id(update)
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        if not tenant:
            await _reply(update, M.NOT_REGISTERED)
            return

        if tenant.get("user_type") != "business":
            await _reply(update, M.TILL_BUSINESS_ONLY)
            return

        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_till"))
        await _reply(update, M.TILL_REGISTRATION_PROMPT)
    except Exception as exc:
        log.exception("cmd_till_failed", telegram_id=_tg_id(update), error=str(exc))
        await _reply(update, "⚠️ *Mazao AI Logic Error*\nI encountered an internal error processing your request. Please try again.")


# ── /status ───────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unified Business Dashboard (HF-T2). Redirects individuals to /mystatus."""
    try:
        tid = _tg_id(update)
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

        if not tenant:
            await _reply(update, M.NOT_REGISTERED)
            return

        # P7-T6: Feature Gating
        if not await is_feature_allowed(str(tenant["id"]), "report"):
            await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Business Dashboard", upgrade_link="/upgrade"))
            return

        # P19-T9AB: Admin Detection
        admin_id = os.getenv("ADMIN_TELEGRAM_ID")
        is_superadmin = admin_id and str(tid) == str(admin_id)

        # P5-T3: Redirect Individual users (Bypassed for Super Admin)
        if tenant.get("user_type") == "individual" and not is_superadmin:
            await cmd_mystatus(update, context, notice=M.PERSONAL_STATUS_NOTICE)
            return

        # ── 1. Header ──────────────────────────────────────────────────────────
        biz_name = tenant.get("business_name") or "Your Business"
        
        if is_superadmin:
            # P19-T9AD: Admin Business Overview
            # Fetch existing data markers (Read-only)
            statement = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_statement(str(tenant["id"])))
            latest_report = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_report(str(tenant["id"])))
            
            if not statement:
                report_status = M.STATE_REPORT_NOT_READY
                statement_status = M.STATE_STATEMENT_NOT_UPLOADED
                cashflow_status = M.STATE_CASHFLOW_LOCKED
            else:
                period = statement.get("period", "Uploaded")
                statement_status = f"{period} ✅"
                cashflow_status = M.STATE_CASHFLOW_AVAILABLE
                report_status = M.STATE_REPORT_READY if latest_report else M.STATE_REPORT_PENDING
            
            text = M.ADMIN_BUSINESS_STATUS.format(
                biz_name=biz_name,
                report_status=report_status,
                statement_status=statement_status,
                cashflow_status=cashflow_status
            )
            await _reply(update, text)
            return

        report = f"🏢 *{biz_name}*\n\n"

        # ── 2. Account Section ─────────────────────────────────────────────────
        user_type = tenant.get("user_type", "business").title()
        lang = tenant.get("preferred_language", "en").upper()
        report += (
            "👤 *Account*\n"
            f"├─ Name: {biz_name}\n"
            f"├─ Type: {user_type}\n"
            f"└─ Lang: {lang}\n\n"
        )

        # ── 3. Plan Section ────────────────────────────────────────────────────
        if is_superadmin:
            plan = "Super Admin"
            status = "Active"
        else:
            plan = tenant.get("plan", "trial").upper()
            status = tenant.get("status", "active").title()
        
        if plan == "TRIAL":
            days_left = tenant.get("trial_days_left", 0)
            # Fallback for trial_ends_at schema inconsistency
            expiry = tenant.get("trial_ends_at")
            if expiry:
                if isinstance(expiry, str):
                    expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                else:
                    expiry_dt = expiry
                expiry_str = expiry_dt.strftime("%d %b %Y")
            else:
                # Calculate from days_left
                expiry_dt = datetime.now(timezone.utc) + timedelta(days=days_left)
                expiry_str = expiry_dt.strftime("%d %b %Y")
                
            report += (
                "🚀 *Plan*\n"
                f"├─ Tier: {plan}\n"
                f"├─ Status: {status}\n"
                f"└─ Ends: {expiry_str} ({days_left}d left)\n\n"
            )
        else:
            # Check both potential column names for subscription expiry
            expiry = tenant.get("subscription_expires_at") or tenant.get("subscription_ends_at")
            if expiry:
                if isinstance(expiry, str):
                    expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                else:
                    expiry_dt = expiry
                expiry_str = expiry_dt.strftime("%d %b %Y")
            else:
                expiry_str = "N/A"
                
            report += (
                "🚀 *Plan*\n"
                f"├─ Tier: {plan}\n"
                f"├─ Status: {status}\n"
                f"└─ Expiry: {expiry_str}\n\n"
            )

        # ── 4. M-Pesa Section ──────────────────────────────────────────────────
        till = tenant.get("mpesa_till")
        if till:
            report += f"📡 *M-Pesa*\n└─ Till: {till} ✅\n\n"
        else:
            report += "📡 *M-Pesa*\n└─ Not connected — /till to add\n\n"

        # ── 5. Last Activity ──────────────────────────────────────────────────
        latest_report = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_report(str(tenant["id"])))
        if latest_report:
            # Use created_at or updated_at from report
            created_at = latest_report.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    activity_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                else:
                    activity_dt = created_at
                activity_str = activity_dt.strftime("%d %b %Y")
            else:
                activity_str = "Recent"
            report += f"⏱️ *Last Activity*\n└─ Report: {activity_str}\n\n"
        else:
            report += "⏱️ *Last Activity*\n└─ No reports yet\n\n"

        # ── 6. Edit Prompt ─────────────────────────────────────────────────────
        report += "⚙️ Edit your details: /settings"

        # CF-1: Proactive redaction of KRA PIN patterns
        import re
        report = re.sub(r'\b[A-P]\d{9}[A-Z]\b', '[REDACTED]', report)

        await _reply(update, report)
    except Exception as exc:
        log.exception("cmd_status_failed", telegram_id=_tg_id(update), error=str(exc))
        await _reply(update, "⚠️ *Mazao AI Logic Error*\nI encountered an internal error loading your dashboard. Please try again.")


# ── /stop and /resume ─────────────────────────────────────────────────────────

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"status": "paused"}))
    await _reply(
        update,
        "⏸️ *Daily reports paused.*\n\nType /resume to turn them back on anytime.\nYour data is safe.",
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"status": "active"}))
    await _reply(
        update,
        "▶️ *Daily reports resumed!*\n\nYou'll receive your next report tomorrow at 7:00 AM.",
    )


# ── /admin (P9-T4) ──────────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Invisible dashboard for Chief Engineer."""
    tid = _tg_id(update)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    
    if not admin_id or str(tid) != str(admin_id):
        # Silent ignore for unauthorized users
        return

    client = db.get_client()
    
    # 1. Total Tenants & Onboarding Stats (P10-T2)
    tenants_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("tenants").select("*").execute()
    )
    all_tenants = tenants_resp.data if tenants_resp and tenants_resp.data else []
    
    # P15-T1: SUPERADMIN_EXCLUDED — Exclude Chief Engineer from metrics
    tenants = [t for t in all_tenants if str(t.get("telegram_id")) != str(admin_id)]
    admin_tenant = next((t for t in all_tenants if str(t.get("telegram_id")) == str(admin_id)), None)
    admin_uuid = admin_tenant["id"] if admin_tenant else None
    
    total = len(tenants)
    onboarded_count = sum(1 for t in tenants if t.get("onboarding_completed"))
    completion_rate = (onboarded_count / total * 100) if total > 0 else 0
    
    # 2. Plan Breakdown (P17-T4I: Normalize Free/Trial/Core/Pro)
    plans = {"free": 0, "core": 0, "pro": 0, "trial": 0}
    for t in tenants:
        p = t.get("plan", "free")
        # Map legacy names using robust map
        mapped_plan = NORM_PLAN_MAP.get(p, "free")
        plans[mapped_plan] = plans.get(mapped_plan, 0) + 1
        
    # 3. Active Trials
    trials_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("tenants").select("trial_days_left").eq("plan", "trial").execute()
    )
    trial_data = trials_resp.data if trials_resp and trials_resp.data else []
    avg_trial = sum(t["trial_days_left"] for t in trial_data) / len(trial_data) if trial_data else 0
    
    # 4. Monthly Revenue
    this_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    rev_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("payment_requests").select("amount, tenant_id").eq("status", "confirmed").gte("confirmed_at", this_month).execute()
    )
    all_rev_data = rev_resp.data if rev_resp and rev_resp.data else []
    
    # P15-T1: SUPERADMIN_EXCLUDED — Exclude test payments from Chief Engineer
    rev_data = [r for r in all_rev_data if str(r.get("tenant_id")) != str(admin_uuid)]
    
    revenue = sum(float(r["amount"]) for r in rev_data)
    payments_count = len(rev_data)
    
    # 5. Conversion Targets (Expired trials not upgraded)
    expired_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("tenants").select("id").eq("status", "lapsed").execute()
    )
    expired_count = len(expired_resp.data if expired_resp and expired_resp.data else [])

    report = (
        "👑 *Chief Engineer Dashboard*\n\n"
        f"🚀 *Onboarding (Funnel):*\n"
        f"├─ Started: {total}\n"
        f"├─ Completed: {onboarded_count}\n"
        f"└─ Rate: {completion_rate:.1f}%\n\n"
        f"👥 *Tenants by Plan:*\n"
        f"├─ Pro (KES 399): {plans.get('pro', 0)}\n"
        f"├─ Core (KES 149): {plans.get('core', 0)}\n"
        f"├─ Trial: {plans.get('trial', 0)}\n"
        f"└─ Free: {plans.get('free', 0)}\n\n"
        f"⏳ *Trials:* {len(trial_data)} active (Avg: {avg_trial:.1f} days)\n"
        f"💰 *Revenue (MTD):* KES {revenue:,.0f} ({payments_count} txns)\n"
        f"🎯 *Conversion Targets:* {expired_count} lapsed"
    )
    
    await _reply(update, report)


# ── Message handler — onboarding flow + free-text ────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    text = (update.message.text or "").strip()

    conv = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_conv_state(tid))
    state = conv["state"] if conv else "idle"

    # P16-FINAL: Auto-Detect KPLC SMS (Zero Friction + Typo Resistant)
    import re as _re
    if text and (_re.search(r'(mtr|mur|mrt|token|tknamt):', text.lower())):
        # P17-T4A: Guard auto-detect path
        if not await _check_subscription_guard(update):
            return
        log.info("auto_detect_token_sms", user_id=update.message.from_user.id)
        return await awaiting_tokens(update, context)

    # 1. Global Command Interrupt Layer (P18-T8E)
    if text.startswith("/"):
        if state != "idle":
            # P17-T5H: Fuliza session-closure commands must reach their handler for custom summary
            if state == "awaiting_fuliza" and text.lower() in ("/done", "/cancel", "/menu"):
                 pass 
            else:
                log.info("session_interrupted_by_command", telegram_id=tid, state=state, command=text)
                await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
                
                # Confirmation for explicit exit commands
                if text.lower() in ("/cancel", "/done", "/menu", "/stop_session"):
                    await _reply(update, "✅ *Action cancelled.* Session cleared.")
                    return
                
                # If we reached here via handle_message (unregistered command), stop processing
                return
        
        # If we are in 'idle' and hit a command in handle_message, it means it's an 
        # unregistered command. Let it fall through to the router or fallback.
        if state == "idle":
            pass 

    if state == "awaiting_settings_name":
        if len(text) < 2:
            await _reply(update, M.SETTINGS_INVALID_INPUT.format(field="Business Name"))
            return
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"business_name": text}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
        
        # P13: Refresh menu after settings change
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        await update_user_menu(context.bot, tid, tenant)
        
        await _reply(update, M.SETTINGS_UPDATED.format(field="Business Name", new_value=text))
        return

    if state == "awaiting_settings_phone":
        clean_phone = re.sub(r"[^0-9]", "", text)
        if not clean_phone or len(clean_phone) < 10:
            await _reply(update, M.SETTINGS_INVALID_INPUT.format(field="Phone Number"))
            return
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"phone_number": clean_phone}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
        
        # P13: Refresh menu after settings change
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        await update_user_menu(context.bot, tid, tenant)
        
        await _reply(update, M.SETTINGS_UPDATED.format(field="Phone Number", new_value=clean_phone))
        return

    if state == "awaiting_settings_till":
        clean_till = re.sub(r"[^0-9]", "", text)
        if not clean_till or len(clean_till) < 5:
            await _reply(update, M.SETTINGS_INVALID_INPUT.format(field="Till Number"))
            return
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"mpesa_till": clean_till}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
        
        # P13: Refresh menu after settings change
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        await update_user_menu(context.bot, tid, tenant)
        
        await _reply(update, M.SETTINGS_UPDATED.format(field="Till Number", new_value=clean_till))
        return

    if state == "awaiting_name":
        if len(text) < 2:
            await _reply(update, M.SETTINGS_INVALID_INPUT.format(field="Business Name"))
            return
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"business_name": text}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_till"))
        await _reply(update, M.ASK_MPESA_TILL)
        return

    if state == "awaiting_individual_name":
        if len(text) < 2:
            await _reply(update, "Please enter your full name.")
            return
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"full_name": text}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_employment_status"))
        
        keyboard = [
            [
                InlineKeyboardButton("🏢 Employed", callback_data="emp_employed"),
                InlineKeyboardButton("🛠️ Self-Employed", callback_data="emp_self_employed"),
            ],
            [InlineKeyboardButton("🚜 Farmer", callback_data="emp_farmer")],
            [InlineKeyboardButton("🎓 Student/Other", callback_data="emp_other")]
        ]
        await _reply(update, M.INDIVIDUAL_ASK_EMPLOYMENT, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if state == "awaiting_feedback":
        # P10-T3: Store and Forward Feedback
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db.get_client().table("feedback").insert({
                "tenant_id": str(tenant["id"]),
                "message": text
            }).execute()
        )
        
        # Forward to admin
        admin_id = os.getenv("ADMIN_TELEGRAM_ID")
        if admin_id:
            name = tenant.get("business_name") or tenant.get("full_name") or "User"
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=M.FEEDBACK_FORWARD.format(name=name, user_type=tenant.get("user_type"), message=text),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                log.error("feedback_forward_failed", error=str(e))
            
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
        await _reply(update, M.FEEDBACK_RECEIVED)
        return

    if state == "awaiting_till":
        # P10-T1: Validation (Digits only, 5-7 range)
        clean_till = re.sub(r"[^0-9]", "", text)
        if not clean_till or len(clean_till) < 5:
            await _reply(update, M.TILL_INVALID)
            return
            
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"mpesa_till": clean_till}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_language"))
        
        keyboard = [
            [
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
                InlineKeyboardButton("🇰🇪 Swahili", callback_data="lang_sw"),
            ]
        ]
        await _reply(update, M.ASK_LANGUAGE, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if state == "awaiting_tokens":
        # P17-T4A: Guard state-based token entry
        if not await _check_subscription_guard(update):
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            return
        return await awaiting_tokens(update, context)

    if state == "awaiting_gas":
        # P17-T4A: Guard state-based gas entry
        if not await _check_subscription_guard(update):
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            return
        # P17-T1B-FIX: Strict regex for <amount> <dd/mm/yyyy>
        m = re.match(r"^\s*(\d+)\s+(\d{1,2}/\d{1,2}/\d{4})\s*$", text)
        if not m:
            await _reply(update, "❌ *Invalid Format*\nPlease use: `amount date` (e.g., `13 22/04/2026`)")
            return
            
        try:
            amount_kg = float(m.group(1))
            d_str = m.group(2)
            
            if amount_kg <= 0:
                await _reply(update, "❌ *Invalid Amount*\nGas amount must be greater than zero.")
                return

            # Strict dd/mm/yyyy parsing
            p_date = datetime.strptime(d_str, "%d/%m/%Y").date()
            
            tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("gas_entries").insert({
                    "tenant_id": str(tenant["id"]),
                    "amount_kg": amount_kg,
                    "purchase_date": p_date.isoformat()
                }).execute()
            )
            
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            
            # ── Gas Estimation Logic (P17-T1D: Refactored) ───────────────────
            proj = await _get_gas_projection(tid, tenant, refill_kg=amount_kg)
            
            # Confidence Label
            conf = estimator.get_confidence_info(proj["n"])
            conf_text = f"Confidence: {conf['bar']} {conf['label']}"
            if proj["n"] <= 1:
                conf_text += "\n_Recording more refills will improve accuracy._"

            # P17-T1G: Source Explanation
            h_type = tenant.get("household_type", "standard")
            src_label = estimator.get_gas_source_label(proj["n"], h_type)

            await _reply(update, M.GAS_RECORDED_SUCCESS.format(
                amount_kg=amount_kg,
                daily_rate=proj["daily_rate"],
                days_remaining=proj["days_remaining"],
                depletion_date=proj["depletion_date"],
                confidence_info=conf_text,
                source_explanation=src_label
            ))

            # P17-T4J: Post-usage nudge (Conversion Trigger 2)
            await _maybe_send_nudge(
                update, context, 
                M.NUDGE_POST_USAGE_VALUE, 
                condition=tenant.get("plan") in ("free", "trial")
            )
        except Exception as e:
            log.error("gas_entry_failed", error=str(e))
            await _reply(update, "❌ *Invalid Input*\nPlease use format: `6 22/04/2026`")
        return


    if state == "awaiting_fuliza":
        # P17-T5H: /done exits Fuliza multi-entry session
        if text.lower() in ("/done", "/cancel", "/menu"):
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            await _reply(update, M.FULIZA_SESSION_DONE)
            return

        # P17-T5: Multi-strategy Fuliza Parsing
        balance, due_date, code, amount_borrowed, fee, total_deducted = None, None, None, None, None, None
        d_str = None
        
        # Strategy 1: Full SMS
        m_code = re.search(r"Code:\s*([A-Z0-9]+)", text, re.IGNORECASE)
        m_amt = re.search(r"Fuliza Amount:\s*([\d,\.]+)", text, re.IGNORECASE)
        m_fee = re.search(r"Fee:\s*([\d,\.]+)", text, re.IGNORECASE)
        m_total = re.search(r"Total:\s*([\d,\.]+)", text, re.IGNORECASE)
        m_out = re.search(r"Outstanding:\s*([\d,\.]+)", text, re.IGNORECASE)
        m_due = re.search(r"Due:\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
        
        # Strategy 2: Quick Entry (Amount Date Outstanding)
        m_quick = re.search(r"^\s*([\d,\.]+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,\.]+)\s*$", text)
        
        # Strategy 3: Legacy Fallback
        bal_match = re.search(r"KES\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})|(\d{4}-\d{1,2}-\d{1,2})", text)
        
        if m_out and m_due:
            balance = float(m_out.group(1).replace(",", ""))
            d_str = m_due.group(1)
            code = m_code.group(1) if m_code else None
            amount_borrowed = float(m_amt.group(1).replace(",", "")) if m_amt else None
            fee = float(m_fee.group(1).replace(",", "")) if m_fee else None
            total_deducted = float(m_total.group(1).replace(",", "")) if m_total else None
        elif m_quick:
            amount_borrowed = float(m_quick.group(1).replace(",", ""))
            d_str = m_quick.group(2)
            balance = float(m_quick.group(3).replace(",", ""))
        elif bal_match and date_match:
            balance = float(bal_match.group(1).replace(",", ""))
            d_str = date_match.group(0)
        else:
            await _reply(update, M.FULIZA_PARSE_FAILED)
            return
            
        try:
            fmt = "%d/%m/%Y" if "/" in d_str else "%Y-%m-%d"
            due_date = datetime.strptime(d_str, fmt).date()
            tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
            tenant_id_str = str(tenant["id"])

            # P17-T5H: Duplicate code guard
            if code:
                dup_resp = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: db.get_client().table("fuliza_entries")
                        .select("id,balance,due_date,amount_borrowed,access_fee,total_deducted,code")
                        .eq("tenant_id", tenant_id_str)
                        .eq("code", code)
                        .limit(1)
                        .execute()
                )
                if dup_resp and hasattr(dup_resp, "data") and isinstance(dup_resp.data, list) and dup_resp.data:
                    # Return existing entry in T5G format
                    ex = dup_resp.data[0]
                    if not ex.get("due_date") or not isinstance(ex["due_date"], str):
                        raise ValueError("Invalid due_date")
                    ex_due = datetime.strptime(ex["due_date"], "%Y-%m-%d").date()
                    ex_days = (ex_due - datetime.now(timezone.utc).date()).days
                    ex_bal = float(ex["balance"])
                    ex_fee = float(ex["access_fee"]) if ex.get("access_fee") else None
                    ex_amtb = float(ex["amount_borrowed"]) if ex.get("amount_borrowed") else None
                    ex_total = float(ex["total_deducted"]) if ex.get("total_deducted") else None
                    ex_full_lines = []
                    if ex.get("code"): ex_full_lines.append(f"🧾 *Code:* {ex['code']}")
                    if ex_amtb is not None: ex_full_lines.append(f"💸 *Borrowed:* KES {ex_amtb:,.2f}")
                    if ex_fee is not None: ex_full_lines.append(f"📈 *Access Fee:* KES {ex_fee:,.2f}")
                    if ex_total is not None: ex_full_lines.append(f"🧮 *Total Deducted:* KES {ex_total:,.2f}")
                    ex_full_lines.append(f"💰 *Outstanding:* KES {ex_bal:,.2f}")
                    ex_full_lines.append(f"📅 *Due Date:* {ex_due.strftime('%d %b %Y')}")
                    ex_full_lines.append(f"⏳ *Time Left:* {ex_days} day{'s' if ex_days != 1 else ''}")
                    ex_risk_icon = ("🔴" if ex_days <= 0 else "🟠" if ex_days < 7 else "🟡" if ex_days <= 14 else "🟢")
                    ex_risk_label = ("OVERDUE" if ex_days <= 0 else "HIGH" if ex_days < 7 else "MEDIUM" if ex_days <= 14 else "LOW")
                    ex_daily = f"💹 *Daily Cost:* KES {ex_fee/ex_days:,.2f}/day" if ex_fee and ex_days > 0 else ""
                    await _reply(update, M.FULIZA_DUPLICATE_BLOCKED.format(
                        code=code,
                        full_view="\n".join(ex_full_lines),
                        quick_view=f"KES {ex_bal:,.2f} due {ex_due.strftime('%d %b')} ({ex_days}d)",
                        risk_line=f"{ex_risk_icon} *Risk:* {ex_risk_label}",
                        daily_cost_line=ex_daily
                    ))
                    await _reply(update, M.FULIZA_MULTI_ENTRY_HINT)
                    return

            insert_data = {
                "tenant_id": tenant_id_str,
                "balance": balance,
                "due_date": due_date.isoformat(),
            }
            if code: insert_data["code"] = code
            if amount_borrowed is not None: insert_data["amount_borrowed"] = amount_borrowed
            if fee is not None: insert_data["access_fee"] = fee
            if total_deducted is not None: insert_data["total_deducted"] = total_deducted
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("fuliza_entries").insert(insert_data).execute()
            )
            
            days_left = (due_date - datetime.now(timezone.utc).date()).days
            # P17-T5H: DO NOT clear state — keep multi-entry session alive
            
            # ── Fuliza Intelligence Output (P17-T5G) ──
            # Full View
            full_lines = []
            if code: full_lines.append(f"🧾 *Code:* {code}")
            if amount_borrowed is not None: full_lines.append(f"💸 *Borrowed:* KES {amount_borrowed:,.2f}")
            if fee is not None: full_lines.append(f"📈 *Access Fee:* KES {fee:,.2f}")
            if total_deducted is not None: full_lines.append(f"🧮 *Total Deducted:* KES {total_deducted:,.2f}")
            full_lines.append(f"💰 *Outstanding:* KES {balance:,.2f}")
            full_lines.append(f"📅 *Due Date:* {due_date.strftime('%d %b %Y')}")
            full_lines.append(f"⏳ *Time Left:* {days_left} day{'s' if days_left != 1 else ''}")
            full_view = "\n".join(full_lines)
            
            # Quick View
            quick_view = f"KES {balance:,.2f} due {due_date.strftime('%d %b')} ({days_left}d)"
            
            # Risk View
            if days_left <= 0:
                risk_label, risk_icon = "OVERDUE", "🔴"
            elif days_left < 7:
                risk_label, risk_icon = "HIGH", "🟠"
            elif days_left <= 14:
                risk_label, risk_icon = "MEDIUM", "🟡"
            else:
                risk_label, risk_icon = "LOW", "🟢"
            risk_line = f"{risk_icon} *Risk:* {risk_label}"
            
            # Daily Cost View
            daily_cost_line = ""
            if fee is not None and days_left > 0:
                daily_cost = fee / days_left
                daily_cost_line = f"💹 *Daily Cost:* KES {daily_cost:,.2f}/day"
                
            await _reply(update, M.FULIZA_PARSED_CONFIRMATION.format(
                full_view=full_view,
                quick_view=quick_view,
                risk_line=risk_line,
                daily_cost_line=daily_cost_line
            ))
            # P17-T5H: multi-entry hint
            await _reply(update, M.FULIZA_MULTI_ENTRY_HINT)
        except Exception as exc:
            log.error("fuliza_parse_error", error=str(exc))
            await _reply(update, "❌ Error saving Fuliza entry.")
        return

    if state == "awaiting_sub_name":
        if len(text) < 2:
            await _reply(update, "Please enter a valid service name.")
            return
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_sub_amount", data={"name": text}))
        await _reply(update, M.SUBSCRIBE_AMOUNT_PROMPT)
        return

    if state == "awaiting_sub_amount":
        try:
            clean_text = text.replace("KES", "").replace(",", "").strip()
            amount = float(clean_text)
            old_data = conv.get("data", {})
            old_data["amount"] = amount
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_sub_day", data=old_data))
            await _reply(update, M.SUBSCRIBE_DAY_PROMPT)
        except ValueError:
            await _reply(update, "❌ Invalid amount. Please enter a number (e.g., `1500`)")
        return

    if state == "awaiting_sub_day":
        try:
            day = int(text)
            if not (1 <= day <= 28):
                await _reply(update, "❌ Please enter a day between 1 and 28.")
                return
            
            data = conv.get("data", {})
            tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("subscriptions").insert({
                    "tenant_id": str(tenant["id"]),
                    "name": data["name"],
                    "amount_kes": data["amount"],
                    "renewal_day": day
                }).execute()
            )
            
            today = datetime.now(timezone.utc)
            next_date = today.replace(day=day)
            if today.day >= day:
                next_date = (next_date + timedelta(days=32)).replace(day=day)

            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            await _reply(update, M.SUBSCRIBE_CONFIRMED.format(
                name=data["name"],
                amount=data["amount"],
                next_date=next_date.strftime("%d %b %Y")
            ))
        except Exception as e:
            log.error("sub_save_failed", error=str(e))
            await _reply(update, "❌ Error saving subscription.")
        return

    if state == "awaiting_upgrade_phone":
        clean_phone = re.sub(r"[^0-9]", "", text)
        if not clean_phone or len(clean_phone) < 10:
            await _reply(update, "❌ Please enter a valid Kenyan phone number (e.g. 0712345678).")
            return
            
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        
        # ── Rate Limiting (P8-T4) ──
        now = datetime.now(timezone.utc)
        tenant_attempts = upgrade_rate_limit.get(tid, [])
        tenant_attempts = [ts for ts in tenant_attempts if (now - ts).total_seconds() < 600]
        if len(tenant_attempts) >= 3:
            await _reply(update, "⚠️ *Too many attempts.*\nPlease wait 10 minutes.")
            return
        tenant_attempts.append(now)
        upgrade_rate_limit[tid] = tenant_attempts

        pending_plan = conv.get("data", {}).get("pending_plan", "core")
        is_founding = tenant.get("founding_member", False)
        has_referral_discount = tenant.get("referral_discount", False)
        
        # P17-T4F: Align with new pricing
        if pending_plan == "pro":
            amount = 399
        else:
            amount = 149
            
        if has_referral_discount and REFERRAL_REWARDS_ENABLED:
            amount = amount * 0.8
            
        plan_name = "Core" if amount < 300 else "Pro"
        
        # P19-T9C: Pre-STK Guidance
        await _reply(update, M.PAYMENT_STK_GUIDE)
        
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"phone_number": clean_phone}))
        account_ref = f"MAZAO-{str(tenant['id'])[:8]}"
        res = await initiate_stk_push(phone_number=clean_phone, amount=amount, account_ref=account_ref, narrative=f"Mazao AI {plan_name}")
        
        if "error" in res:
            # P19-T9C: Standard failure message
            await _reply(update, M.PAYMENT_FAILED)
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            return
            
        # P19-T9C: Notify user about pending state
        await _reply(update, M.PAYMENT_PENDING)
        
        invoice_id = res.get("id") or res.get("invoice_id")
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db.get_client().table("payment_requests").insert({
                "tenant_id": str(tenant["id"]),
                "amount": amount,
                "phone_number": clean_phone,
                "account_ref": account_ref,
                "intasend_invoice_id": str(invoice_id),
                "status": "pending"
            }).execute()
        )
        
        await _reply(update, M.STK_PUSH_SENT.format(phone=clean_phone, amount=amount, plan_name=plan_name))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
        return

    # ── T6F-EMPTY-STATE: awaiting_statement_upload ───────────────────────
    if state == "awaiting_statement_upload":
        # /cancel exits the session cleanly
        if text.lower() in ("/cancel", "/done", "/menu"):
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            await _reply(update, "✅ *Upload cancelled.* Type /statement anytime to try again.")
            log.info("statement_upload_cancelled", telegram_id=tid)
            return

        # Document upload: validate, parse, and run pipeline
        if update.message and update.message.document:
            doc = update.message.document
            fname = (doc.file_name or "").lower()

            # Rule 1: Must be a CSV file
            if not fname.endswith(".csv"):
                await _reply(update, M.STATEMENT_UPLOAD_INVALID_FORMAT)
                log.info("statement_upload_invalid_format", telegram_id=tid, filename=doc.file_name)
                return

            # Rule 2: Basic size sanity (< 5MB for CSV)
            if doc.file_size and doc.file_size > 5 * 1024 * 1024:
                await _reply(update, "⚠️ *File too large.*\n\nPlease send a CSV under 5MB.")
                return

            # Download file bytes
            try:
                tg_file = await context.bot.get_file(doc.file_id)
                raw_bytes = await tg_file.download_as_bytearray()
            except Exception as exc:
                log.exception("statement_download_failed", telegram_id=tid, error=str(exc))
                await _reply(update, "❌ *Download failed.* Please try again.")
                return

            # Parse CSV statement using the centralized parser (P19-T12)
            try:
                parsed_txs = mpesa_parser.parse(raw_bytes, "csv")
            except Exception as exc:
                log.exception("statement_csv_parse_error", telegram_id=tid, error=str(exc))
                await _reply(update, M.STATEMENT_PARSE_FAILED)
                return

            if not parsed_txs:
                await _reply(update, M.STATEMENT_PARSE_FAILED)
                log.warning("statement_parse_empty", telegram_id=tid, filename=doc.file_name)
                return

            # Fetch tenant for statement save
            stmt_tenant = await _safe_db_call(lambda: db.get_tenant(tid))
            if not stmt_tenant:
                await _reply(update, M.NOT_REGISTERED)
                return

            # Save statement summary
            total_in  = sum(t.amount for t in parsed_txs if t.transaction_type == TransactionType.C2B)
            total_out = sum(t.amount for t in parsed_txs if t.transaction_type != TransactionType.C2B)
            period    = datetime.now(timezone.utc).strftime("%Y-%m")
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.save_statement(
                    tenant_id=str(stmt_tenant["id"]),
                    period=period,
                    total_inflows=total_in,
                    total_outflows=total_out,
                    net=round(total_in - total_out, 2),
                    vat_estimate=round(total_in * 0.16, 2),
                )
            )

            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            await _reply(update, M.STATEMENT_PARSE_SUCCESS.format(count=len(parsed_txs)))
            log.info("statement_parsed_and_saved", telegram_id=tid, tx_count=len(parsed_txs), filename=doc.file_name)

            # Launch pipeline with CSV transactions as custom data
            context.application.create_task(
                _run_pipeline_and_reply(
                    update, context, stmt_tenant,
                    custom_transactions=parsed_txs,
                    trigger_source="statement_upload",
                )
            )
            return


        # Text input while in upload mode: reject with guidance
        await _reply(update, M.STATEMENT_REJECT_TEXT)
        log.info("statement_upload_text_rejected", telegram_id=tid)
        return

    # ── Idle state fallback ───────────────────────────────────────────────
    tenant = db.get_tenant(tid)
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    # P18: Conversational Intent Router (Deterministic Only)
    intent = router.classify_intent(text)
    if intent:
        log.info("intent_detected", telegram_id=tid, intent=intent)
        if intent == router.INTENT_GREETING:
            return await cmd_start(update, context)
        if intent == router.INTENT_HELP:
            return await cmd_help(update, context)
        
        # Guide intents
        msg_key = router.get_guidance_message_key(intent)
        return await _reply(update, getattr(M, msg_key))

    # P18-T8H: Soft Recovery Layer (Deterministic)
    recovery_intent = router.classify_recovery_intent(text)
    msg_key = router.get_guidance_message_key(recovery_intent)
    log.info("fallback_recovery_triggered", telegram_id=tid, recovery_intent=recovery_intent)
    await _reply(update, getattr(M, msg_key))


# ── Bot commands menu (shown in Telegram's / menu) ────────────────────────────

BOT_COMMANDS = [
    # (1) Conversion Funnel (Top Menu)
    BotCommand("about",         "What Mazao AI does (Start here)"),
    BotCommand("start",         "Set up or open your account"),
    BotCommand("report",        "Today’s business summary"),
    BotCommand("tokens",        "Electricity usage"),
    BotCommand("gas",           "Gas tracking"),
    BotCommand("fuliza",        "Fuliza insights"),
    BotCommand("status",        "Account status"),
    BotCommand("settings",      "Update profile"),
    BotCommand("help",          "Show all commands"),
    
    # (2) Secondary / Deep links
    BotCommand("mystatus",      "Personal status (KRA/SHA)"),
    BotCommand("statement",     "Show parsing summary"),
    BotCommand("vat",           "Show VAT estimate"),
    BotCommand("kra",           "Show next deadlines"),
    BotCommand("till",          "Register M-Pesa Till"),
    BotCommand("subscribe",     "Add monthly bill reminder"),
    BotCommand("subscriptions", "List all active bills"),
    BotCommand("upgrade",       "🚀 Upgrade to paid plan"),
    BotCommand("language",      "Change language"),
    BotCommand("privacy",       "Read Privacy Policy"),
    BotCommand("refer",         "Refer a friend & get discount"),
    BotCommand("feedback",      "Send feedback/report issue"),
    BotCommand("stop",          "Pause daily bot alerts"),
    BotCommand("resume",        "Resume daily bot alerts"),
]

