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
            name = (tenant.get("full_name") or tenant.get("business_name") or "User") if tenant else "User"
            
            msg = M.LANGUAGE_SET_EN if lang == "en" else M.LANGUAGE_SET_SW
            await query.edit_message_text(f"{msg}\n\n{M.SETUP_COMPLETE.format(name=name)}")
            await query.answer(f"Language set to {lang.upper()}")
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

        # Use passed transactions or fall back to live transactions (P6-T6)
        txs = custom_transactions
        if not txs:
            from datetime import datetime
            now = datetime.utcnow()
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

# ── /tokens (P4-T1) ─────────────────────────────────────────────────────────

async def cmd_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_tokens"))
    await _reply(update, M.TOKEN_ENTRY_PROMPT)


# ── /fuliza (P4-T2) ──────────────────────────────────────────────────────────

async def cmd_fuliza(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
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
    
    await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state(tid, "awaiting_sub_name"))
    await _reply(update, M.SUBSCRIBE_NAME_PROMPT)


async def cmd_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
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
    """Unified Business Dashboard (P5-T3). Redirects individuals to /mystatus."""
    tid = _tg_id(update)
    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))

    if not tenant:
        await _reply(update, M.NOT_REGISTERED)
        return
    
    # P5-T3: Redirect Individual users
    if tenant.get("user_type") == "individual":
        await _reply(update, M.BUSINESS_STATUS_REDIRECT)
        return

    today = datetime.utcnow()
    
    # ── 1. Tax Calculation ────────────────────────────────────────────────
    # VAT (20th), PAYE (9th)
    next_month = today + timedelta(days=32)
    vat_due = today.replace(day=20) if today.day < 20 else next_month.replace(day=20)
    paye_due = today.replace(day=9) if today.day < 9 else next_month.replace(day=9)
    annual_due = datetime(today.year if today.month <= 6 else today.year + 1, 6, 30)
    
    # ── 2. Latest Statement / Live Transactions ──────────────────────────
    from datetime import datetime
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    live_resp = db.get_client().table("live_transactions").select("*").eq("tenant_id", str(tenant["id"])).gte("trans_time", month_start).execute()
    live_data = live_resp.data if live_resp else []
    
    if live_data:
        count = len(live_data)
        last_txn = max(tx["trans_time"] for tx in live_data)
        last_txn_dt = datetime.fromisoformat(last_txn.replace("Z", "+00:00"))
        s_summary = f"📡 Live Feed ({count} txns)\nLast: {last_txn_dt.strftime('%H:%M Today')}"
    else:
        statement = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_statement(str(tenant["id"])))
        if statement:
            s_summary = (
                f"Period: {statement.get('period', 'N/A')}\n"
                f"Net: KES {(statement.get('net') or 0):,.2f}"
            )
        else:
            s_summary = "_No statement uploaded yet. (Use /statement)_"

    # ── 3. Subscriptions ──────────────────────────────────────────────────
    subs = await asyncio.get_event_loop().run_in_executor(
        None, 
        lambda: db.get_client().table("subscriptions").select("*").eq("tenant_id", str(tenant["id"])).execute()
    )
    sub_count = len(subs.data) if subs.data else 0
    next_sub_date = "N/A"
    sub_days = 0
    
    if sub_count > 0:
        # Find the soonest renewal
        soonest = 99
        for s in subs.data:
            day = s["renewal_day"]
            days_left = day - today.day if day > today.day else (day + 30 - today.day)
            if days_left < soonest:
                soonest = days_left
                next_date = today.replace(day=day) if day > today.day else (today + timedelta(days=32)).replace(day=day)
                next_sub_date = next_date.strftime("%d %b")
                sub_days = soonest

    # ── 4. Platform Status ────────────────────────────────────────────────
    status_map = {"active": "✅ Active", "trial": "⏳ Trial", "paused": "⏸️ Paused"}
    platform_status = status_map.get(tenant.get("status", ""), "⚙️ Setup")
    if tenant.get("plan") == "trial":
        platform_status += f" ({tenant.get('trial_days_left', 0)}d left)"

    await _reply(
        update,
        M.BUSINESS_STATUS_DASHBOARD.format(
            business_name=tenant.get("business_name", "Your Business"),
            plan_tier=tenant.get("plan", "trial").upper(),
            vat_days=(vat_due.date() - today.date()).days,
            paye_days=(paye_due.date() - today.date()).days,
            annual_days=(annual_due.date() - today.date()).days,
            statement_summary=s_summary,
            sub_count=sub_count,
            next_sub_date=next_sub_date,
            sub_days=sub_days,
            platform_status=platform_status
        )
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

    if state == "awaiting_till":
        if re.match(r"^\d{5,7}$", text):
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"till_number": text}))
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            await _reply(update, M.TILL_CONFIRMED.format(till_number=text))
        else:
            await _reply(update, M.TILL_INVALID)
        return

    if state == "awaiting_tokens":
        try:
            # Format: "units date" (e.g. "25.5 20/04/2026")
            parts = text.split()
            if len(parts) < 2:
                await _reply(update, "Please enter both units and date. Example: `25.5 20/04/2026`")
                return
            
            units = float(parts[0])
            d_str = parts[1]
            p_date = datetime.strptime(d_str, "%d/%m/%Y").date()
            
            tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))
            
            # Store in token_entries
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("token_entries").insert({
                    "tenant_id": str(tenant["id"]),
                    "units": units,
                    "purchase_date": p_date.isoformat()
                }).execute()
            )
            
            # P4-T1: Projection math
            # Get history
            history = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("token_entries")
                .select("*")
                .eq("tenant_id", str(tenant["id"]))
                .order("purchase_date", desc=True)
                .limit(5)
                .execute()
            )
            
            daily_rate = 6.0 # Default for 3-5 persons
            h_size = tenant.get("household_size", 4)
            if h_size <= 2: daily_rate = 3.0
            elif h_size >= 6: daily_rate = 10.0
            
            entries = history.data if history.data else []
            if len(entries) >= 2:
                # Calculate rate: (Newest - Oldest units) / days
                # Simpler implementation: just use default as fallback as per P4-T1 logic
                pass 

            days_remaining = int(units / daily_rate)
            depletion_date = (datetime.utcnow() + timedelta(days=days_remaining)).strftime("%d %b %Y")
            
            await asyncio.get_event_loop().run_in_executor(None, lambda: db.clear_conv_state(tid))
            await _reply(update, f"⚡ *Token Recorded!*\n\nUnits: {units}\nEst. Daily Rate: {daily_rate} units\n\n🗓️ *Depletion Date:* {depletion_date}\n⏳ *Days left:* {days_remaining}")
            return
        except Exception as exc:
            log.warning("token_parse_failed", error=str(exc))
            await _reply(update, "❌ Invalid format. Please use: `units DD/MM/YYYY` (e.g., `30 20/04/2026`)")
            return

    if state == "awaiting_fuliza":
        # Regex parse: balance and date
        bal_match = re.search(r"KES\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})|(\d{4}-\d{1,2}-\d{1,2})", text)
        
        if not bal_match or not date_match:
            await _reply(update, "❌ Could not find balance or due date in that text. Please forward the full SMS.")
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
            return
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
            # Clean KES prefix or commas
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
            
            # Save to DB
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("subscriptions").insert({
                    "tenant_id": str(tenant["id"]),
                    "name": data["name"],
                    "amount_kes": data["amount"],
                    "renewal_day": day
                }).execute()
            )
            
            # Calculate next date
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
            await _reply(update, "❌ Error saving subscription. Please try again.")
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
    BotCommand("start",         "Set up your account"),
    BotCommand("help",          "Show all commands"),
    BotCommand("status",        "Business dashboard"),
    BotCommand("mystatus",      "Personal dashboard"),
    BotCommand("report",        "Generate profit report"),
    BotCommand("vat",           "Show VAT estimate"),
    BotCommand("kra",           "Show tax deadlines"),
    BotCommand("statement",     "Show parsing summary"),
    BotCommand("tokens",        "Log electricity units"),
    BotCommand("fuliza",        "Log Fuliza loan"),
    BotCommand("subscribe",     "Add monthly bill"),
    BotCommand("subscriptions", "List active bills"),
    BotCommand("till",          "Register M-Pesa Till"),
    BotCommand("language",      "Change language"),
    BotCommand("stop",          "Pause bot alerts"),
    BotCommand("resume",        "Resume bot alerts"),
]
