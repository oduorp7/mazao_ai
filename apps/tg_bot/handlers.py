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

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import apps.tg_bot.db as db
import apps.tg_bot.messages as M
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

# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _tg_id(update: Update) -> int:
    return update.effective_user.id


def _username(update: Update) -> str:
    return update.effective_user.username or ""


def _full_name(update: Update) -> str:
    u = update.effective_user
    return f"{u.first_name or ''} {u.last_name or ''}".strip()


async def _reply(update: Update, text: str, **kwargs) -> None:
    # CF-1: Final safety net redaction of any KRA PIN patterns (A0xxxxxxxB)
    import re
    text = re.sub(r'\b[A-P]\d{9}[A-Z]\b', '[REDACTED]', text)
    
    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        **kwargs,
    )


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

    # P10-T4: Handle Referral deep link (start=REF_CODE)
    args = context.args
    referred_by_id = None
    if args and args[0].startswith("REF_"):
        ref_code = args[0]
        log.info("referral_link_detected", telegram_id=tid, ref_code=ref_code)
        # Find referrer
        referrer_resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda: db.get_client().table("tenants").select("id").eq("referral_code", ref_code).execute()
        )
        if referrer_resp.data:
            referred_by_id = referrer_resp.data[0]["id"]
            log.info("referrer_found", referrer_id=referred_by_id)

    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

    if tenant and tenant["status"] in ("active", "trial"):
        # P13: Refresh menu for existing users
        await update_user_menu(context.bot, tid, tenant)
        # Already registered — show help instead
        await _reply(update, M.HELP)
        return

    conv = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_conv_state(tid))
    state = conv["state"] if conv else "idle"

    if state == "idle":
        # First time start: present user type selection
        keyboard = [
            [
                InlineKeyboardButton("🏢 Business Owner", callback_data="type_business"),
                InlineKeyboardButton("👤 Individual", callback_data="type_individual"),
            ]
        ]
        await _reply(update, M.USER_TYPE_SELECT, reply_markup=InlineKeyboardMarkup(keyboard))
        # Create tenant row if not exists
        if not await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid)):
            await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: db.create_tenant(
                    telegram_id=tid,
                    telegram_username=_username(update),
                    full_name=_full_name(update),
                    referred_by=referred_by_id # P10-T4
                )
            )
        elif referred_by_id:
            # Update existing but un-onboarded tenant
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.update_tenant(tid, {"referred_by": referred_by_id})
            )
        return


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
            trial_ends = (datetime.utcnow() + timedelta(days=14)).strftime("%d %b %Y")
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
    tenant = db.get_tenant(_tg_id(update))
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
    
    keyboard = [
        [
            InlineKeyboardButton("🔹 Mtu Wenyewe (KES 300/mo)" if is_founding else "🔹 Mtu Wenyewe (KES 500/mo)", callback_data="upgrade_mtu"),
        ],
        [
            InlineKeyboardButton("🔸 Biashara (KES 1,500/mo)" if is_founding else "🔸 Biashara (KES 2,500/mo)", callback_data="upgrade_biashara"),
        ]
    ]
    
    msg = M.UPGRADE_PROMPT.format(mtu_price=300 if is_founding else 500, biashara_price=1500 if is_founding else 2500)
    if is_founding:
        msg = f"{M.FOUNDING_BADGE}\n\n{msg}"
        
    await _reply(
        update, 
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ── /mystatus ─────────────────────────────────────────────────────────────────

async def cmd_mystatus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the upcoming obligations for an individual user."""
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)
    
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
    
    today = datetime.utcnow()
    
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
    
    await _reply(update, text)


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
            await _reply(update, M.STATEMENT_REQUIRED)
            return

        # P3-T5: Summary format with null-safety (FAANG grade robustness)
        text = (
            "📂 *M-Pesa Statement Summary*\n"
            f"Period: {statement.get('period', 'N/A')}\n"
            f"Parsed: {str(statement.get('parsed_at', '')).split('T')[0]}\n\n"
            f"💰 Total Inflows:  KES {(statement.get('total_inflows') or 0):,.2f}\n"
            f"💸 Total Outflows: KES {(statement.get('total_outflows') or 0):,.2f}\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Net Amount:    KES {(statement.get('net') or 0):,.2f}*\n"
        )
        
        vat_est = statement.get("vat_estimate") or 0
        if vat_est > 0:
            text += f"\n📋 *Est. VAT Liability: KES {vat_est:,.2f}*"
            text += "\n_(Label: Clearly an Estimate)_"

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
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    # P3-T2: Check if a statement has been uploaded
    statement = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_statement(str(tenant["id"])))
    if not statement:
        await _reply(update, M.STATEMENT_REQUIRED)
        return

    # P7-T6: Feature Gating
    if not await is_feature_allowed(str(tenant["id"]), "report"):
        await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Business Report", upgrade_link="/upgrade"))
        return

    # FAANG-grade immediate feedback
    msg = await update.message.reply_text("🔄 *Mazao AI is analyzing your transactions...*\nPlease wait a moment.")
    
    if not tenant.get("mpesa_till"):
        await _reply(
            update,
            "⚙️ Your M-Pesa Till isn't set up yet.\n\nType /start to complete setup."
        )
        return

    await _reply(update, M.REPORT_GENERATING)

    log.info("report_requested", telegram_id=tid, tenant_id=tenant["id"])

    # Run pipeline in background
    context.application.create_task(
        _run_pipeline_and_reply(update, context, tenant)
    )


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
    ext = Path(doc.file_name).suffix.lower()
    
    fmt = None
    if mime == "text/csv" or ext == ".csv":
        fmt = "csv"
    elif mime == "application/pdf" or ext == ".pdf":
        fmt = "pdf_text"
    elif mime == "text/plain" or ext == ".txt":
        fmt = "sms"
    
    if not fmt:
        await _reply(update, M.UNSUPPORTED_FILE_FORMAT)
        return

    await _reply(update, M.STATEMENT_RECEIVED_PARSING)

    try:
        file = await context.bot.get_file(doc.file_id)
        file_bytes = await file.download_as_bytearray()
        
        from apps.agent.mpesa_parser import parse
        txs = parse(bytes(file_bytes), fmt)
        
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
            
        period = datetime.utcnow().strftime("%Y-%m")
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

        await _reply(update, M.STATEMENT_PARSE_SUCCESS.format(count=len(txs)))
        
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

    try:
        from pipeline import run_pipeline
        from state import RawTransaction, TransactionType

        # Use passed transactions or fall back to live transactions (P6-T6)
        txs = custom_transactions
        if not txs:
            from datetime import datetime
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            
            live_resp = db.get_client().table("live_transactions").select("*").eq("tenant_id", str(tenant["id"])).gte("trans_time", month_start).execute()
            if live_resp and live_resp.data:
                from apps.agent.state import RawTransaction, TransactionType
                txs = []
                for lt in live_resp.data:
                    tx_time = datetime.fromisoformat(lt["trans_time"].replace("Z", "+00:00"))
                    txs.append(RawTransaction(
                        mpesa_ref=lt["trans_id"],
                        amount=float(lt["amount"]),
                        phone=lt["msisdn"] or "",
                        name=lt["first_name"] or "Guest",
                        shortcode=lt["bill_ref"] or "",
                        transaction_type=TransactionType.PAYMENT_RECEIVED,
                        timestamp=tx_time
                    ))
                trigger_source = "live_feed"
            else:
                await context.bot.send_message(
                    chat_id=tid,
                    text=M.STATEMENT_REQUIRED,
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_pipeline(
                tenant_id=str(tenant["id"]),
                raw_transactions=txs,
                triggered_by=trigger_source,
            ),
        )

        # Language selection logic (P2-T4)
        lang = tenant.get("preferred_language", "en")
        report_text = result.report_text_sw if lang == "sw" else result.report_text_en

        if report_text:
            await context.bot.send_message(
                chat_id=tid,
                text=report_text,
                parse_mode=ParseMode.MARKDOWN,
            )

            # Persist report
            if result.reconciliation:
                r = result.reconciliation
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: db.save_report(
                        tenant_id=str(tenant["id"]),
                        period=datetime.now(timezone.utc).strftime("%Y-%m"),
                        summary={
                            "income": r.total_income,
                            "expenses": r.total_expenses,
                            "profit": r.net_profit,
                            "flagged": r.flagged_count,
                        },
                    )
                )
        else:
            await context.bot.send_message(
                chat_id=tid,
                text=M.PIPELINE_ERROR,
                parse_mode=ParseMode.MARKDOWN,
            )

    except Exception as exc:
        log.exception("pipeline_failed", telegram_id=tid, error=str(exc))
        await context.bot.send_message(
            chat_id=tid,
            text=M.PIPELINE_ERROR,
            parse_mode=ParseMode.MARKDOWN,
        )


# ── /vat ──────────────────────────────────────────────────────────────────────

async def cmd_vat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    # Try to get latest cached report
    report = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_report(str(tenant["id"])))

    if not report:
        await _reply(
            update,
            "📊 No report data yet.\n\nRun /report first to generate your numbers."
        )
        return

    summary = report.get("summary", {})
    income = summary.get("income", 0)
    expenses = summary.get("expenses", 0)

    output_vat = round(income * 0.16, 0)
    input_vat = round(expenses * 0.16, 0)
    net_vat = max(output_vat - input_vat, 0)
    refund = max(input_vat - output_vat, 0)

    # VAT Hygiene (P15-H2)
    today = datetime.now(timezone.utc)
    next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    due_date = next_month.replace(day=20)
    days_left = (due_date.date() - today.date()).days

    if refund > 0:
        await _reply(
            update,
            M.VAT_REFUND.format(
                period=today.strftime("%B %Y"),
                refund=_fmt_kes(refund),
                due_date=due_date.strftime("%d %b %Y"),
            ),
        )
    else:
        await _reply(
            update,
            M.VAT_SUMMARY.format(
                period=today.strftime("%B %Y"),
                taxable_sales=_fmt_kes(income),
                supplier_spend=_fmt_kes(expenses),
                output_vat=_fmt_kes(output_vat),
                input_vat=_fmt_kes(input_vat),
                net_vat=_fmt_kes(net_vat),
                due_date=due_date.strftime("%d %b %Y"),
                days_left=days_left,
            ),
        )


# ── /kra ──────────────────────────────────────────────────────────────────────

async def cmd_kra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    today = datetime.utcnow()
    next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)

    obligations = [
        {"type": "VAT", "due_day": 20, "icon": "📋"},
        {"type": "PAYE", "due_day": 9, "icon": "👥"},
        {"type": "NSSF", "due_day": 15, "icon": "🏥"},
        {"type": "NHIF/SHA", "due_day": 9, "icon": "💊"},
    ]

    text = M.KRA_OBLIGATIONS_HEADER
    for ob in obligations:
        due_date = next_month.replace(day=ob["due_day"])
        days_left = (due_date.date() - today.date()).days
        overdue = days_left < 0
        overdue_flag = "\n   ❗ *OVERDUE*" if overdue else ""

        text += M.KRA_OBLIGATION_ROW.format(
            icon=ob["icon"],
            obligation_type=ob["type"],
            due_date=due_date.strftime("%d %b %Y"),
            amount=0,               # will come from pipeline result in production
            days_left=abs(days_left) if not overdue else f"{abs(days_left)} days ago",
            overdue_flag=overdue_flag,
        )

    await _reply(update, text)

# ── /tokens (P4-T1) ─────────────────────────────────────────────────────────

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
    # Check if household_type is already set in the database
    h_type = tenant.get("household_type")
    if not h_type:
        reply_markup = _get_htype_keyboard()
        await _reply(
            update, 
            "🏠 *Before we record your tokens, what best describes your home?*\n\nThis helps us provide accurate predictions from day one.", 
            reply_markup=reply_markup
        )
        return
        
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_tokens"))
    await _reply(update, M.TOKEN_ENTRY_PROMPT)


# ── /gas (P17-T1) ────────────────────────────────────────────────────────────

async def cmd_gas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    # P7-T6: Feature Gating
    if not await is_feature_allowed(str(tenant["id"]), "utility_tracking"):
        await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Gas Tracking", upgrade_link="/upgrade"))
        return
        
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
        
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_fuliza"))
    await _reply(update, M.FULIZA_SMS_PROMPT)


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
        
        if not subs.data:
            await _reply(update, M.SUBSCRIPTIONS_EMPTY)
            return
        
        text = M.SUBSCRIPTIONS_LIST_HEADER
        today = datetime.utcnow()
        
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
    """P6-T5: Register M-Pesa Till for live alerts."""
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


# ── /status ───────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unified Business Dashboard (HF-T2). Redirects individuals to /mystatus."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    # P7-T6: Feature Gating
    if not await is_feature_allowed(str(tenant["id"]), "report"):
        await _reply(update, M.UPGRADE_REQUIRED.format(feature_name="Business Dashboard", upgrade_link="/upgrade"))
        return
    
    # P5-T3: Redirect Individual users
    if tenant.get("user_type") == "individual":
        await cmd_mystatus(update, context)
        return

    # ── 1. Header ──────────────────────────────────────────────────────────
    biz_name = tenant.get("business_name") or "Your Business"
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
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    is_superadmin = admin_id and str(tid) == str(admin_id)
    
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
    all_tenants = tenants_resp.data or []
    
    # P15-T1: SUPERADMIN_EXCLUDED — Exclude Chief Engineer from metrics
    tenants = [t for t in all_tenants if str(t.get("telegram_id")) != str(admin_id)]
    admin_tenant = next((t for t in all_tenants if str(t.get("telegram_id")) == str(admin_id)), None)
    admin_uuid = admin_tenant["id"] if admin_tenant else None
    
    total = len(tenants)
    onboarded_count = sum(1 for t in tenants if t.get("onboarding_completed"))
    completion_rate = (onboarded_count / total * 100) if total > 0 else 0
    
    # 2. Plan Breakdown
    plans = {"free": 0, "mtu_wenyewe": 0, "biashara": 0, "trial": 0}
    for t in tenants:
        p = t.get("plan", "free")
        plans[p] = plans.get(p, 0) + 1
        
    # 3. Active Trials
    trials_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("tenants").select("trial_days_left").eq("plan", "trial").execute()
    )
    trial_data = trials_resp.data or []
    avg_trial = sum(t["trial_days_left"] for t in trial_data) / len(trial_data) if trial_data else 0
    
    # 4. Monthly Revenue
    this_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    rev_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("payment_requests").select("amount, tenant_id").eq("status", "confirmed").gte("confirmed_at", this_month).execute()
    )
    all_rev_data = rev_resp.data or []
    
    # P15-T1: SUPERADMIN_EXCLUDED — Exclude test payments from Chief Engineer
    rev_data = [r for r in all_rev_data if str(r.get("tenant_id")) != str(admin_uuid)]
    
    revenue = sum(float(r["amount"]) for r in rev_data)
    payments_count = len(rev_data)
    
    # 5. Conversion Targets (Expired trials not upgraded)
    expired_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("tenants").select("id").eq("status", "lapsed").execute()
    )
    expired_count = len(expired_resp.data or [])

    report = (
        "👑 *Chief Engineer Dashboard*\n\n"
        f"� *Onboarding (Funnel):*\n"
        f"├─ Started: {total}\n"
        f"├─ Completed: {onboarded_count}\n"
        f"└─ Rate: {completion_rate:.1f}%\n\n"
        f"👥 *Tenants by Plan:*\n"
        f"├─ Biashara: {plans['biashara']}\n"
        f"├─ Mtu Wenyewe: {plans['mtu_wenyewe']}\n"
        f"└─ Free/Trial: {plans['trial'] + plans['free']}\n\n"
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
        log.info("auto_detect_token_sms", user_id=update.message.from_user.id)
        return await awaiting_tokens(update, context)

    # P10-T1: Command interruption check
    if text.startswith("/"):
        if state != "idle":
            log.info("state_cleared_by_command", telegram_id=tid, state=state, command=text)
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
        return

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
                if any(col in exc_str for col in ["meter_number", "token_number", "token_amount", "other_charges", "tariff_tier"]):
                    log.warning("new_columns_missing_fallback", error=str(insert_exc))
                    # Retry with basic fields only
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: db.get_client().table("token_entries").insert({
                            "tenant_id": str(tenant["id"]),
                            "units": units,
                            "purchase_date": p_date.isoformat(),
                            "amount_paid": amount_paid,
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
            h_type = tenant.get("household_type", "standard")
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
            import math as _math
            days_remaining = int(_math.ceil(total_units_for_projection / daily_rate))
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
            # WWFD: Only show breakdown when we have REAL TknAmt from KPLC SMS.
            # Never estimate or approximate — if we don't know, say so.
            breakdown_text = ""
            if is_full_sms and token_amount and other_charges is not None and amount_paid > 0:
                elec_pct = round((token_amount / amount_paid) * 100, 1)
                tax_pct  = round((other_charges / amount_paid) * 100, 1)
                rate_display = round(token_amount / units, 2) if units > 0 else 0
                tier_label = tier["label"] if tier else "Unknown"

                breakdown_text = (
                    f"\n\n💡 *Cost Breakdown (from your token):*\n"
                    f"Actual electricity: KES {token_amount:,.2f} ({elec_pct}%)\n"
                    f"Taxes & levies:     KES {other_charges:,.2f} ({tax_pct}%)\n"
                    f"Your rate: KES {rate_display}/unit — {tier_label}\n"
                    f"_Levy charges vary monthly per EPRA gazette._\n\n"
                    f"Only {elec_pct}% of your KES {amount_paid:,.0f} was electricity."
                )
            elif amount_paid and not is_full_sms:
                # WWFD: honest prompt, no fabricated numbers
                breakdown_text = "\n\n💡 _Paste the full KPLC token SMS next time for an accurate cost breakdown._"

            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))

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
        return


    if state == "awaiting_gas":
        parts = text.split()
        if len(parts) < 2:
            await _reply(update, M.GAS_SMS_PROMPT)
            return
            
        try:
            amount_kg = float(parts[0].replace(",", ""))
            d_str = parts[1]
            
            from dateutil import parser as date_parser
            p_date = date_parser.parse(d_str, dayfirst=True).date()
            
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
            
            # ── Gas Estimation Logic (P17-T1B) ───────────────────────────────
            gas_resp = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("gas_entries")
                .select("amount_kg, purchase_date")
                .eq("tenant_id", str(tenant["id"]))
                .order("purchase_date", desc=True)
                .execute()
            )
            
            # Map amount_kg -> units for estimator compatibility
            history = [{"units": r["amount_kg"], "purchase_date": r["purchase_date"]} for r in gas_resp.data]
            n = len(history)
            
            # Reuse core math: Weighted personal rate + population blend (0.2kg/day)
            pop_rate = estimator.GAS_DAILY_BASELINE
            pers_rate, n_valid = estimator.calculate_weighted_personal_rate(history)
            daily_rate = estimator.blend_rates(pers_rate, pop_rate, n, n_valid)
            
            if daily_rate <= 0:
                daily_rate = pop_rate
                
            # Depletion Math (Simpler for gas: Current KG / Daily Rate)
            import math as _math
            days_remaining = int(_math.ceil(amount_kg / daily_rate))
            depletion_date = (datetime.now(timezone.utc) + timedelta(days=days_remaining)).strftime("%d %b %Y")
            
            # Confidence Label
            conf = estimator.get_confidence_info(n)
            conf_text = f"Confidence: {conf['bar']} {conf['label']}"
            if n <= 1:
                conf_text += "\n_Recording more refills will improve accuracy._"

            await _reply(update, M.GAS_RECORDED_SUCCESS.format(
                amount_kg=amount_kg,
                daily_rate=daily_rate,
                days_remaining=days_remaining,
                depletion_date=depletion_date,
                confidence_info=conf_text
            ))
        except Exception as e:
            log.error("gas_entry_failed", error=str(e))
            await _reply(update, "❌ *Invalid Input*\nPlease use format: `6 22/04/2026`")
        return


    if state == "awaiting_fuliza":
        # P10-T1: Regex parse failure check
        bal_match = re.search(r"KES\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})|(\d{4}-\d{1,2}-\d{1,2})", text)
        
        if not bal_match or not date_match:
            await _reply(update, M.FULIZA_PARSE_FAILED)
            return
            
        try:
            balance = float(bal_match.group(1).replace(",", ""))
            d_str = date_match.group(0)
            fmt = "%d/%m/%Y" if "/" in d_str else "%Y-%m-%d"
            due_date = datetime.strptime(d_str, fmt).date()
            tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("fuliza_entries").insert({
                    "tenant_id": str(tenant["id"]),
                    "balance": balance,
                    "due_date": due_date.isoformat()
                }).execute()
            )
            days_left = (due_date - datetime.utcnow().date()).days
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            await _reply(update, M.FULIZA_PARSED_CONFIRMATION.format(
                balance=balance,
                due_date=due_date.strftime("%d %b %Y"),
                days_until_due=days_left
            ))
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
            
            today = datetime.utcnow()
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
        now = datetime.utcnow()
        tenant_attempts = upgrade_rate_limit.get(tid, [])
        tenant_attempts = [ts for ts in tenant_attempts if (now - ts).total_seconds() < 600]
        if len(tenant_attempts) >= 3:
            await _reply(update, "⚠️ *Too many attempts.*\nPlease wait 10 minutes.")
            return
        tenant_attempts.append(now)
        upgrade_rate_limit[tid] = tenant_attempts

        pending_plan = conv.get("data", {}).get("pending_plan", "mtu_wenyewe")
        is_founding = tenant.get("founding_member", False)
        has_referral_discount = tenant.get("referral_discount", False)
        
        if is_founding:
            amount = 1500 if pending_plan == "biashara" else 300
        else:
            amount = 2500 if pending_plan == "biashara" else 500
            
        if has_referral_discount:
            amount = amount * 0.8
            
        plan_name = "Mtu Wenyewe" if amount in (240, 300, 400, 500) else "Biashara"
        
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"phone_number": clean_phone}))
        account_ref = f"MAZAO-{str(tenant['id'])[:8]}"
        res = await initiate_stk_push(phone_number=clean_phone, amount=amount, account_ref=account_ref, narrative=f"Mazao AI {plan_name}")
        
        if "error" in res:
            await _reply(update, M.PAYMENT_FAILED.format(upgrade_link="/upgrade"))
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            return
            
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

    # ── Idle state fallback ───────────────────────────────────────────────
    tenant = db.get_tenant(tid)
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    text_lower = text.lower()
    if any(k in text_lower for k in ["report", "summary", "mapato"]):
        await cmd_report(update, context)
    elif any(k in text_lower for k in ["vat", "tax", "kodi"]):
        await cmd_vat(update, context)
    elif any(k in text_lower for k in ["help", "commands"]):
        await cmd_help(update, context)
    else:
        await _reply(update, M.UNKNOWN_MESSAGE)


# ── Bot commands menu (shown in Telegram's / menu) ────────────────────────────

BOT_COMMANDS = [
    # (1) Core
    BotCommand("start",         "Start Mazao AI & Onboarding"),
    BotCommand("help",          "Show all commands"),
    
    # (2) Dashboard
    BotCommand("status",        "Business Dashboard"),
    BotCommand("mystatus",      "Personal status (KRA/SHA)"),
    BotCommand("report",        "Generate profit report"),
    BotCommand("statement",     "Show parsing summary"),
    BotCommand("vat",           "Show VAT estimate"),
    BotCommand("kra",           "Show next deadlines"),
    
    # (3) Utilities
    BotCommand("tokens",        "Log electricity units"),
    BotCommand("fuliza",        "Log Fuliza loan balance"),
    BotCommand("till",          "Register M-Pesa Till"),
    
    # (4) Bills
    BotCommand("subscribe",     "Add monthly bill reminder"),
    BotCommand("subscriptions", "List all active bills"),
    
    # (5) Account
    BotCommand("upgrade",       "🚀 Upgrade to paid plan"),
    BotCommand("language",      "Change language"),
    BotCommand("settings",      "⚙️ Edit your profile"),
    BotCommand("privacy",       "Read Privacy Policy"),
    BotCommand("refer",         "Refer a friend & get discount"),
    BotCommand("feedback",      "Send feedback/report issue"),
    
    # (6) Controls
    BotCommand("stop",          "Pause daily bot alerts"),
    BotCommand("resume",        "Resume daily bot alerts"),
]

