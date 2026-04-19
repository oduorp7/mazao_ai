"""
handlers.py — All Telegram command and message handlers.

Each handler is a standalone async function registered in bot.py.
Pattern: receive Update → check tenant state → act → reply.

Conversation states (stored in DB):
  idle              — normal, commands work
  awaiting_name     — /start flow, waiting for business name
  awaiting_till     — waiting for M-Pesa till number
  awaiting_kra_pin  — waiting for KRA PIN
"""

from __future__ import annotations

import sys
import os
import re
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

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

# Add agent pipeline to path
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

import db
import messages as M
from utils.logging import get_logger

log = get_logger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _tg_id(update: Update) -> int:
    return update.effective_user.id


def _username(update: Update) -> str:
    return update.effective_user.username or ""


def _full_name(update: Update) -> str:
    u = update.effective_user
    return f"{u.first_name or ''} {u.last_name or ''}".strip()


async def _reply(update: Update, text: str, **kwargs) -> None:
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        **kwargs,
    )


def _fmt_kes(amount: float) -> str:
    return f"{amount:,.0f}"


# ── /start — onboarding entry point ──────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    log.info("cmd_start", telegram_id=tid)

    tenant = db.get_tenant(tid)

    if tenant and tenant["status"] in ("active", "trial"):
        # Already registered — show help instead
        await _reply(update, M.HELP)
        return

    # Sprint 2: User Type selection
    keyboard = [
        [
            InlineKeyboardButton("🏪 Business Owner", callback_data="type_business"),
            InlineKeyboardButton("👤 Individual", callback_data="type_individual"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await _reply(update, M.USER_TYPE_SELECT, reply_markup=reply_markup)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the user type selection from the inline keyboard."""
    query = update.callback_query
    await query.answer()
    
    tid = query.from_user.id
    data = query.data
    
    log.info("callback_received", telegram_id=tid, data=data)
    
    if data == "type_business":
        db.set_conv_state(tid, "awaiting_name", data={"user_type": "business"})
        # Create tenant row if not exists
        if not db.get_tenant(tid):
            db.create_tenant(
                telegram_id=tid,
                telegram_username=query.from_user.username,
                full_name=query.from_user.full_name,
            )
        db.update_tenant(tid, {"user_type": "business"})
        await query.edit_message_text(M.WELCOME)
        
    elif data == "type_individual":
        db.set_conv_state(tid, "awaiting_individual_name", data={"user_type": "individual"})
        # Create tenant row if not exists
        if not db.get_tenant(tid):
            db.create_tenant(
                telegram_id=tid,
                telegram_username=query.from_user.username,
                full_name=query.from_user.full_name,
            )
        db.update_tenant(tid, {"user_type": "individual"})
        await query.edit_message_text(M.INDIVIDUAL_ASK_NAME)

    elif data.startswith("emp_"):
        emp_status = data.replace("emp_", "")
        db.update_tenant(tid, {"employment_status": emp_status})
        db.set_conv_state(tid, "awaiting_sha")
        
        status_readable = emp_status.replace("_", " ").title()
        await query.edit_message_text(
            f"✅ Status set to: *{status_readable}*\n\n{M.INDIVIDUAL_ASK_SHA}", 
            parse_mode=ParseMode.MARKDOWN
        )

# ── /skip ───────────────────────────────────────────────────────────────────

async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles skipping optional steps like SHA number."""
    tid = _tg_id(update)
    conv = db.get_conv_state(tid)
    state = conv["state"] if conv else "idle"
    
    if state == "awaiting_sha":
        db.update_tenant(tid, {"status": "active"})
        db.clear_conv_state(tid)
        tenant = db.get_tenant(tid)
        await _reply(update, M.INDIVIDUAL_SETUP_COMPLETE.format(name=tenant.get("full_name", "")))
        return

    await _reply(update, "Nothing to skip right now.")


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tenant = db.get_tenant(_tg_id(update))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    await _reply(update, M.HELP)


# ── /mystatus ─────────────────────────────────────────────────────────────────

async def cmd_mystatus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the upcoming obligations for an individual user."""
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)
    
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
        
    if tenant.get("user_type") != "individual":
        await _reply(update, "This command is only available for Individual accounts.")
        return

    obligations = db.get_individual_obligations(tid)
    
    text = M.MYSTATUS_HEADER.format(
        name=tenant.get("full_name", _username(update)),
        status=tenant.get("employment_status", "unknown").title().replace("_", " ")
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
        
    await _reply(update, text)


# ── /report — trigger pipeline now ───────────────────────────────────────────

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    # FAANG-grade immediate feedback
    msg = await update.message.reply_text("🔄 *Mazao AI is analyzing your transactions...*\nPlease wait a moment.")
    
    # Run the pipeline (this might take 5-10s)

    if not tenant.get("mpesa_till"):
        await _reply(
            update,
            "⚙️ Your M-Pesa Till isn't set up yet.\n\nType /start to complete setup."
        )
        return

    await _reply(update, M.REPORT_GENERATING)

    log.info("report_requested", telegram_id=tid, tenant_id=tenant["id"])

    # Run pipeline in background so Telegram doesn't time out
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
        
        from mpesa_parser import parse
        txs = parse(bytes(file_bytes), fmt)
        
        if not txs:
            await _reply(update, M.STATEMENT_PARSE_FAILED)
            return

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

        # Use passed transactions or fall back to sample/real fetch
        txs = custom_transactions if custom_transactions is not None else _get_sample_transactions(tenant)

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_pipeline(
                tenant_id=str(tenant["id"]),
                raw_transactions=txs,
                triggered_by=trigger_source,
            ),
        )

        if result.report_text_en:
            await context.bot.send_message(
                chat_id=tid,
                text=result.report_text_en,
                parse_mode=ParseMode.MARKDOWN,
            )

            # Persist report
            if result.reconciliation:
                r = result.reconciliation
                db.save_report(
                    tenant_id=str(tenant["id"]),
                    period=datetime.utcnow().strftime("%Y-%m"),
                    summary={
                        "income": r.total_income,
                        "expenses": r.total_expenses,
                        "profit": r.net_profit,
                        "flagged": r.flagged_count,
                    },
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


def _get_sample_transactions(tenant: dict):
    """
    Returns sample transactions for demo/dev mode.
    Replace this with real Daraja API calls in production.
    """
    from state import RawTransaction, TransactionType

    return [
        RawTransaction(
            mpesa_ref="QHF001",
            amount=3500.0,
            phone="0712000001",
            name="JANE WANJIKU",
            shortcode=tenant.get("mpesa_till", "123456"),
            transaction_type=TransactionType.C2B,
            timestamp=datetime.utcnow() - timedelta(days=1),
        ),
        RawTransaction(
            mpesa_ref="QHF002",
            amount=12000.0,
            phone="0723000002",
            name="KAMAU HARDWARE",
            shortcode=tenant.get("mpesa_till", "123456"),
            transaction_type=TransactionType.C2B,
            timestamp=datetime.utcnow() - timedelta(days=2),
        ),
        RawTransaction(
            mpesa_ref="QHF003",
            amount=8500.0,
            phone="0734000003",
            name="JOHN MWANGI",
            shortcode=tenant.get("mpesa_till", "123456"),
            transaction_type=TransactionType.B2C,
            timestamp=datetime.utcnow() - timedelta(days=3),
        ),
        RawTransaction(
            mpesa_ref="QHF004",
            amount=4800.0,
            phone="0745000004",
            name="NAIVAS SUPERMARKET",
            shortcode=tenant.get("mpesa_till", "123456"),
            transaction_type=TransactionType.B2B,
            timestamp=datetime.utcnow() - timedelta(days=4),
        ),
    ]


# ── /vat ──────────────────────────────────────────────────────────────────────

async def cmd_vat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    # Try to get latest cached report
    report = db.get_latest_report(str(tenant["id"]))

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

    # Due on 20th of next month
    today = datetime.utcnow()
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
    tenant = db.get_tenant(tid)

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

    text += M.KRA_OBLIGATIONS_FOOTER
    await _reply(update, text)


# ── /status ───────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    report = db.get_latest_report(str(tenant["id"]))
    last_report = (
        report["created_at"][:10] if report else "No reports yet"
    )

    plan_map = {
        "trial": f"🆓 Free Trial ({tenant.get('trial_days_left', 0)} days left)",
        "hustler": "🟢 Hustler (KES 1,500/mo)",
        "biashara": "🔵 Biashara (KES 3,500/mo)",
    }

    status_map = {
        "active": "✅ Active",
        "trial": "⏳ Trial",
        "pending": "⚙️ Setup incomplete",
        "paused": "⏸️ Paused",
        "lapsed": "❌ Lapsed",
    }

    trial_line = ""
    if tenant["plan"] == "trial":
        days = tenant.get("trial_days_left", 0)
        trial_line = f"\nTrial ends: {days} days remaining\n"

    await _reply(
        update,
        M.STATUS.format(
            business_name=tenant.get("business_name", "—"),
            till_number=tenant.get("mpesa_till", "Not set"),
            kra_pin=tenant.get("kra_pin", "Not set"),
            plan=plan_map.get(tenant.get("plan", "trial"), tenant.get("plan", "—")),
            status=status_map.get(tenant.get("status", ""), tenant.get("status", "—")),
            trial_line=trial_line,
            last_report=last_report,
        ),
    )


# ── /stop and /resume ─────────────────────────────────────────────────────────

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = db.get_tenant(tid)
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    db.update_tenant(tid, {"status": "paused"})
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
    db.update_tenant(tid, {"status": "active"})
    await _reply(
        update,
        "▶️ *Daily reports resumed!*\n\nYou'll receive your next report tomorrow at 7:00 AM.",
    )


# ── Message handler — onboarding flow + free-text ────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles all non-command text messages.
    Routes to the correct onboarding step based on conversation state,
    or falls back to a helpful unknown-message reply.
    """
    tid = _tg_id(update)
    text = (update.message.text or "").strip()

    conv = db.get_conv_state(tid)
    state = conv["state"] if conv else "idle"

    log.info("message_received", telegram_id=tid, state=state, length=len(text))

    # ── Onboarding state machine ──────────────────────────────────────────

    # ── Individual Onboarding ──────────────────────────────────────────

    if state == "awaiting_individual_name":
        if len(text) < 2:
            await _reply(update, "Please enter your full name (at least 2 characters).")
            return
        db.set_conv_state(tid, "awaiting_individual_kra", data={"full_name": text})
        db.update_tenant(tid, {"full_name": text})
        await _reply(update, M.INDIVIDUAL_ASK_KRA.format(name=text))
        return

    if state == "awaiting_individual_kra":
        # Validate KRA PIN format: A012345678B
        if not re.match(r"^[A-Za-z]\d{9}[A-Za-z]$", text):
            await _reply(
                update,
                "⚠️ That doesn't look like a valid KRA PIN.\n\nFormat: `A012345678B` (letter, 9 digits, letter)",
            )
            return
        db.set_conv_state(tid, "awaiting_employment")
        db.update_tenant(tid, {"kra_pin": text.upper()})
        
        keyboard = [
            [
                InlineKeyboardButton("🏢 Employed", callback_data="emp_employed"),
                InlineKeyboardButton("🛠️ Self-Employed", callback_data="emp_self_employed"),
            ],
            [InlineKeyboardButton("🎓 Unemployed / Student", callback_data="emp_unemployed")]
        ]
        await _reply(update, M.INDIVIDUAL_ASK_EMPLOYMENT, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if state == "awaiting_sha":
        # Validate SHA: digits only
        if not re.match(r"^\d+$", text):
            await _reply(update, "Please send a valid SHA number (digits only), or type /skip.")
            return

        db.update_tenant(tid, {"sha_number": text, "status": "active"})
        db.clear_conv_state(tid)
        tenant = db.get_tenant(tid)
        await _reply(update, M.INDIVIDUAL_SETUP_COMPLETE.format(name=tenant.get("full_name", "")))
        return

    # ── Business Onboarding ────────────────────────────────────────────

    if state == "awaiting_name":
        if len(text) < 2:
            await _reply(update, "Please enter your business name (at least 2 characters).")
            return

        db.set_conv_state(tid, "awaiting_till", data={"business_name": text})

        # Create tenant row if not exists
        if not db.get_tenant(tid):
            db.create_tenant(
                telegram_id=tid,
                telegram_username=_username(update),
                full_name=_full_name(update),
            )
        db.update_tenant(tid, {"business_name": text})

        await _reply(update, M.ASK_MPESA_TILL.format(business_name=text))
        return

    if state == "awaiting_till":
        # Validate: M-Pesa Till/Paybill is 5-7 digits
        if not re.match(r"^\d{5,7}$", text):
            await _reply(
                update,
                "⚠️ That doesn't look like a valid Till/Paybill number.\n\nPlease send only digits, e.g. `123456`",
            )
            return

        conv_data = conv.get("data", {})
        db.set_conv_state(
            tid, "awaiting_kra_pin", data={**conv_data, "mpesa_till": text}
        )
        db.update_tenant(tid, {"mpesa_till": text})

        await _reply(update, M.ASK_KRA_PIN.format(till_number=text))
        return

    if state == "awaiting_kra_pin":
        # Validate KRA PIN format: A012345678B
        if not re.match(r"^[A-Za-z]\d{9}[A-Za-z]$", text):
            await _reply(
                update,
                "⚠️ That doesn't look like a valid KRA PIN.\n\nFormat: `A012345678B` (letter, 9 digits, letter)",
            )
            return

        db.update_tenant(tid, {"kra_pin": text.upper(), "status": "trial"})
        db.clear_conv_state(tid)

        tenant = db.get_tenant(tid)
        name = tenant.get("business_name", _full_name(update))

        await _reply(update, M.SETUP_COMPLETE.format(name=name))

        log.info("onboarding_complete", telegram_id=tid, business_name=name)
        return

    # ── Idle state — not in onboarding ───────────────────────────────────

    tenant = db.get_tenant(tid)
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    # Check for common keywords and route helpfully
    text_lower = text.lower()

    if any(k in text_lower for k in ["report", "summary", "mapato", "pesa"]):
        await cmd_report(update, context)
        return

    if any(k in text_lower for k in ["vat", "tax", "kodi"]):
        await cmd_vat(update, context)
        return

    if any(k in text_lower for k in ["deadline", "kra", "due", "filing"]):
        await cmd_kra(update, context)
        return

    if any(k in text_lower for k in ["help", "commands", "what can"]):
        await cmd_help(update, context)
        return

    # True fallback
    await _reply(update, M.UNKNOWN_MESSAGE)


# ── Bot commands menu (shown in Telegram's / menu) ────────────────────────────

BOT_COMMANDS = [
    BotCommand("start",  "Set up your account"),
    BotCommand("report", "Generate today's business report"),
    BotCommand("vat",    "See your VAT estimate"),
    BotCommand("kra",    "View KRA deadlines"),
    BotCommand("status", "Account & subscription info"),
    BotCommand("stop",   "Pause daily reports"),
    BotCommand("resume", "Resume daily reports"),
    BotCommand("mystatus", "View your individual status"),
    BotCommand("skip",   "Skip the current optional step"),
    BotCommand("help",   "Show all commands"),
]
