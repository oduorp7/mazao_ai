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

import apps.tg_bot.db as db
import apps.tg_bot.messages as M
from apps.agent.utils.logging import get_logger
from apps.agent.utils.ocr_service import ocr_engine
from apps.agent.state import RawTransaction, TransactionType

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

    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

    if tenant and tenant["status"] in ("active", "trial"):
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
                )
            )
        return


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

    elif data.startswith("lang_"):
        lang = data.replace("lang_", "")
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"preferred_language": lang}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
        
        tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
        name = tenant.get("full_name") or tenant.get("business_name") or "User"
        
        msg = M.LANGUAGE_SET_EN if lang == "en" else M.LANGUAGE_SET_SW
        await query.edit_message_text(f"{msg}\n\n{M.SETUP_COMPLETE.format(name=name)}")


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
            ts = datetime.utcnow()
            
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

        # Use passed transactions or fail if none
        txs = custom_transactions
        if not txs:
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
                        period=datetime.utcnow().strftime("%Y-%m"),
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

    text += M.KRA_OBLIGATIONS_FOOTER
    await _reply(update, text)


# ── /status ───────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return

    report = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_report(str(tenant["id"])))
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
            language="🇺🇸 English" if tenant.get("preferred_language") == "en" else "🇰🇪 Kiswahili",
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


# ── Message handler — onboarding flow + free-text ────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    text = (update.message.text or "").strip()

    conv = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_conv_state(tid))
    state = conv["state"] if conv else "idle"

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
            [InlineKeyboardButton("🎓 Unemployed", callback_data="emp_unemployed")]
        ]
        await _reply(update, M.INDIVIDUAL_ASK_EMPLOYMENT, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if state == "awaiting_name":
        if len(text) < 2:
            await _reply(update, "Please enter your business name.")
            return
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"business_name": text}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_till"))
        await _reply(update, M.ASK_MPESA_TILL.format(business_name=text))
        return

    if state == "awaiting_till":
        if not re.match(r"^\d+$", text):
            await _reply(update, "Please enter a valid Till number (digits only).")
            return
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"mpesa_till": text, "status": "active"}))
        await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_language"))
        
        keyboard = [
            [
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
                InlineKeyboardButton("🇰🇪 Swahili", callback_data="lang_sw"),
            ]
        ]
        await _reply(update, M.ASK_LANGUAGE, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await _reply(update, M.UNKNOWN_MESSAGE)

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
    BotCommand("mystatus", "Individual KRA/SHA status"),
    BotCommand("language", "Change language / Badilisha lugha"),
    BotCommand("stop",   "Pause daily reports"),
    BotCommand("resume", "Resume daily reports"),
    BotCommand("help",   "Show all commands"),
]
