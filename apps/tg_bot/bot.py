"""
bot.py — Mazao AI Telegram Bot

THE entry point. Run this file and the bot is live.

  python bot.py

CORE ENVIRONMENT VARIABLES (Required):
  TELEGRAM_BOT_TOKEN
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
  ANTHROPIC_API_KEY
  FLY_APP_URL

PAYMENT BRIDGE VARIABLES (Optional - Intasend):
  INTASEND_PUBLISHABLE_KEY
  INTASEND_SECRET_KEY
  PAYMENT_PROVIDER (intasend | daraja)
  INTASEND_WEBHOOK_CHALLENGE

Nothing else lives here. All logic is in handlers.py, scheduler.py,
pipeline.py (agent), and db.py.
"""

import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import Bot, Update, BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    TypeHandler, # P10-T5
)
from telegram.request import HTTPXRequest # P10-T5
from telegram.constants import ParseMode

from apps.tg_bot.menu import update_user_menu
from apps.tg_bot.handlers import (
    cmd_start,
    cmd_help,
    cmd_report,
    cmd_vat,
    cmd_kra,
    cmd_status,
    cmd_mystatus,
    cmd_settings, # HF-T3
    cmd_language,
    cmd_privacy,
    cmd_feedback,
    cmd_refer,
    cmd_upgrade,
    cmd_admin,
    cmd_till,
    cmd_statement,
    cmd_tokens,
    cmd_gas,
    cmd_fuliza,
    cmd_subscribe,
    cmd_subscriptions,
    cmd_stop,
    cmd_resume,
    handle_message,
    handle_callback,
    handle_document,
    handle_photo,
    BOT_COMMANDS,
)
from apps.tg_bot.scheduler import (
    job_daily_reports,
    job_deadline_alerts,
    job_trial_alerts,
    job_subscription_renewal_alerts,
    job_admin_daily_digest, # P10-T5
)
from apps.agent.utils.logging import get_logger, setup_logging
from datetime import time # P10-T5

load_dotenv()

setup_logging()
log = get_logger(__name__)

# ── Environment & Application Setup ────────────────────────────────────────────

def _check_env() -> None:
    """Verify all required environment variables are set."""
    required = [
        "TELEGRAM_BOT_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "ANTHROPIC_API_KEY",
    ]
    missing = [env for env in required if not os.getenv(env)]
    if missing:
        log.critical("missing_environment_variables", missing=missing)
        sys.exit(1)


async def post_init(application: Application) -> None:
    """Called once after the bot starts — set global command menu and register webhooks."""
    try:
        # P13: Register DEFAULT scope for all users (initial view)
        from apps.tg_bot.menu import CMD_COMMON_START
        await application.bot.set_my_commands(CMD_COMMON_START, scope=BotCommandScopeDefault())
        log.info("default_bot_commands_registered", count=len(CMD_COMMON_START))

        # P6-T3: Register Payment Provider Callback
        app_url = os.getenv("FLY_APP_URL")
        if app_url:
            from apps.payments import get_provider
            provider = get_provider()
            webhook_url = f"{app_url.rstrip('/')}/payments/webhook"
            success = await provider.register_callback_url(webhook_url)
            if success:
                log.info("payment_callback_registered", url=webhook_url)
            else:
                log.warn("payment_callback_registration_failed")

    except Exception as e:
        log.error("post_init_failed", error=str(e))


async def main() -> None:
    _check_env()

    token = os.environ["TELEGRAM_BOT_TOKEN"]

    log.info("bot_starting")

    # ── Initialize application ────────────────────────────────────────────
    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=20.0,
    )

    app = (
        Application.builder()
        .token(token)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # ── Job 0: Admin Daily Digest (P10-T5) ──────────────────────────────────
    # Runs at 08:00 AM EAT daily
    app.job_queue.run_daily(
        job_admin_daily_digest,
        time=time(hour=8, minute=0, second=0),
        name="admin_daily_digest"
    )

    # ── High-level monitor ────────────────────────────────────────────────
    async def monitor(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.info("raw_update_received", update_type=type(update).__name__)
        if isinstance(update, Update) and update.effective_message:
            log.info("raw_message_text", text=update.effective_message.text, chat_id=update.effective_chat.id)

    app.add_handler(TypeHandler(Update, monitor), group=-1) # Group -1 runs BEFORE other handlers

    # ── Register handlers ─────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("vat",    cmd_vat))
    app.add_handler(CommandHandler("kra",    cmd_kra))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("mystatus", cmd_mystatus))
    app.add_handler(CommandHandler("settings", cmd_settings)) # HF-T3
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CommandHandler("privacy",  cmd_privacy))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("refer",    cmd_refer))
    app.add_handler(CommandHandler("upgrade",  cmd_upgrade))
    app.add_handler(CommandHandler("admin",    cmd_admin))
    app.add_handler(CommandHandler("till",     cmd_till))
    app.add_handler(CommandHandler("statement", cmd_statement))
    app.add_handler(CommandHandler("tokens", cmd_tokens))
    app.add_handler(CommandHandler("gas", cmd_gas))
    app.add_handler(CommandHandler("fuliza", cmd_fuliza))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("subscriptions", cmd_subscriptions))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(CommandHandler("resume", cmd_resume))

    # All non-command text → conversation handler
    app.add_handler(
        MessageHandler(filters.TEXT, handle_message)
    )

    # Document upload handle
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Photo upload handle for M-Pesa Screenshots (OCR)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Inline button clicks
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Global error handler (P5-T5)
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        import traceback
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)
        
        log.error("unhandled_exception", error=str(context.error), traceback=tb_string)
        
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️  *Something went wrong*\nOur team has been notified. Please try again or type /help.",
                parse_mode=ParseMode.MARKDOWN
            )

    app.add_error_handler(error_handler)

    # ── Start scheduler (APScheduler version) ───────────────────────────
    from apps.tg_bot.scheduler import create_scheduler
    scheduler = create_scheduler(app.bot)
    scheduler.start()
    log.info("scheduler_started")

    # ── Start polling ─────────────────────────────────────────────────────
    log.info("bot_polling_start")
    print("\n✅  Mazao AI bot is running. Press Ctrl+C to stop.\n")

    await app.initialize()
    await post_init(app)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    # Run forever until interrupt
    stop_event = asyncio.Event()
    
    # ── Webhook Server (P5-T6 & P6-T2) ───────────────────────────────────────
    from aiohttp import web
    
    async def health_check(request):
        """P14-T2: Health Check for Fly.io Rollback Protection."""
        version = os.getenv("GIT_HASH", "unknown")
        return web.json_response({
            "status": "ok",
            "version": version
        }, status=200)

    async def payment_webhook(request):
        """P8-T2: Intasend webhooks are POST only. Challenge is in the body."""
        try:
            payload = await request.json()
            # Intasend specific challenge
            expected_challenge = os.getenv("INTASEND_WEBHOOK_CHALLENGE", "")
            incoming_challenge = payload.get("challenge", "")
            if expected_challenge and incoming_challenge == expected_challenge:
                log.info("intasend_webhook_challenge_validated")
                return web.Response(text="OK", status=200)

            from apps.payments import get_provider
            provider = get_provider()
            parsed = await provider.handle_webhook(payload)
            if parsed:
                asyncio.create_task(process_live_transaction(app.bot, parsed))
            return web.Response(text="OK", status=200)
        except Exception as e:
            log.error("webhook_handler_error", error=str(e))
            return web.Response(text="OK", status=200)

    async def daraja_validation(request):
        """P12-T3A: Daraja C2B Validation Endpoint."""
        try:
            payload = await request.json()
            log.info("daraja_validation_received", payload=payload)
            # ResultCode 0 means we accept the transaction
            return web.json_response({"ResultCode": 0, "ResultDesc": "Accepted"})
        except Exception as e:
            log.error("daraja_validation_error", error=str(e))
            return web.json_response({"ResultCode": 1, "ResultDesc": "Internal Error"})

    async def daraja_confirmation(request):
        """P12-T3B: Daraja C2B Confirmation Endpoint."""
        try:
            payload = await request.json()
            log.info("daraja_confirmation_received", payload=payload)
            
            # P0_HOTFIX_PAYLOAD_MAPPING: Explicitly map Safaricom payload to DB columns
            # P17-T7C: Map Safaricom payload to DB schema (amount, bill_ref)
            mapping = {
                "trans_id": payload.get("TransID"),
                "trans_time": payload.get("TransTime"),
                "amount": payload.get("TransAmount"),
                "bill_ref": payload.get("BillRefNumber"),
                "msisdn": payload.get("MSISDN"),
                "first_name": payload.get("FirstName")
            }
            
            from apps.payments.daraja import DarajaProvider
            provider = DarajaProvider()
            parsed = await provider.handle_webhook(payload)
            
            if parsed:
                # This task handles the DB write to live_transactions and tenant notification
                # We pass the raw mapping now to ensure full field population
                asyncio.create_task(process_live_transaction(app.bot, parsed, raw_mapping=mapping))
                log.info("daraja_confirmation_processed", trans_id=parsed.trans_id)
            
            return web.json_response({"ResultCode": 0, "ResultDesc": "Accepted"})
        except Exception as e:
            log.error("daraja_confirmation_error", error=str(e))
            # Even on error, we return 0 to Safaricom to prevent retries if we logged the failure
            return web.json_response({"ResultCode": 0, "ResultDesc": "Accepted"})

    health_app = web.Application()
    health_app.router.add_get("/health", health_check)
    health_app.router.add_post("/payments/webhook", payment_webhook)
    health_app.router.add_post("/mpesa/c2b/validation", daraja_validation)
    health_app.router.add_post("/mpesa/c2b/confirmation", daraja_confirmation)
    
    runner = web.AppRunner(health_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("webhook_server_live", port=port)

    # Heartbeat task
    async def heartbeat():
        while not stop_event.is_set():
            log.info("bot_heartbeat", alive=True)
            await asyncio.sleep(60)
            
    asyncio.create_task(heartbeat())

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    finally:
        log.info("bot_shutdown_start")
        await app.stop()
        await app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass


async def process_live_transaction(bot: Bot, parsed, raw_mapping: dict = None):
    """P6-T2 & P7-T5: Routes transaction to tenant or subscription processor."""
    try:
        from apps.tg_bot.db import get_client
        import apps.tg_bot.messages as M
        
        db = get_client()
        
        # ── 1. Check for Subscription Payment (MAZAO- prefix) ───────────────────
        if parsed.bill_ref and parsed.bill_ref.startswith("MAZAO-"):
            log.info("subscription_payment_detected", ref=parsed.bill_ref, amount=parsed.amount)
            
            # Match via Account Ref
            pr_resp = db.table("payment_requests").select("*").eq("account_ref", parsed.bill_ref).eq("status", "pending").maybe_single().execute()
            if pr_resp and pr_resp.data:
                request_data = pr_resp.data
                tenant_id = request_data["tenant_id"]
                amount = float(parsed.amount)
                
                # Update Payment Request
                db.table("payment_requests").update({
                    "status": "confirmed",
                    "confirmed_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", request_data["id"]).execute()
                
                # Determine Plan (P17-T4D Alignment)
                if amount >= 399:
                    new_plan = "pro"
                elif amount >= 149:
                    new_plan = "core"
                else:
                    new_plan = "free"
                
                # Update Tenant
                expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
                db.table("tenants").update({
                    "plan": new_plan,
                    "subscription_active": True,
                    "subscription_expires_at": expires_at,
                    "trial_started_at": None, 
                    "trial_ends_at": None,
                    "status": "active"
                }).eq("id", tenant_id).execute()
                
                # Notify User
                # Get tenant telegram_id
                t_resp = db.table("tenants").select("telegram_id, referred_by, full_name, business_name").eq("id", tenant_id).maybe_single().execute()
                if t_resp and t_resp.data:
                    tenant_data = t_resp.data
                    await bot.send_message(
                        chat_id=tenant_data["telegram_id"],
                        text=M.PAYMENT_CONFIRMED.format(
                            plan_name=new_plan.title().replace("_", " "),
                            amount=parsed.amount
                        ),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # P10-T4: Referral Reward
                    if tenant_data.get("referred_by"):
                        referrer_id = tenant_data["referred_by"]
                        # Tag referrer for discount
                        db.table("tenants").update({"referral_discount": True}).eq("id", referrer_id).execute()
                        
                        # Notify Referrer
                        ref_resp = db.table("tenants").select("telegram_id").eq("id", referrer_id).maybe_single().execute()
                        if ref_resp and ref_resp.data:
                            name = tenant_data.get("business_name") or tenant_data.get("full_name") or "A friend"
                            await bot.send_message(
                                chat_id=ref_resp.data["telegram_id"],
                                text=M.REFERRAL_SUCCESS_REFERRER.format(name=name),
                                parse_mode=ParseMode.MARKDOWN
                            )
                return
            else:
                log.warn("subscription_payment_unmatched", ref=parsed.bill_ref)

        # ── 2. Match Tenant for Live Feed (Regular Payment) ──────────────────
        tenant = None
        resp = db.table("tenants").select("*").eq("mpesa_till", parsed.bill_ref).maybe_single().execute()
        if resp and resp.data:
            tenant = resp.data
        else:
            # Fallback (sanitized)
            clean_phone = parsed.msisdn.lstrip("+")
            resp = db.table("tenants").select("*").ilike("telegram_username", f"%{clean_phone}%").maybe_single().execute()
            if resp and resp.data:
                tenant = resp.data

        tenant_id = tenant["id"] if tenant else None
        
        # 3. Insert into live_transactions
        try:
            # P0_HOTFIX_PAYLOAD_MAPPING: Use raw_mapping if available for full field coverage
            if raw_mapping:
                insert_data = {**raw_mapping, "tenant_id": tenant_id, "provider": parsed.provider}
                # Ensure amount is float (Safaricom sends as string)
                if insert_data.get("amount"):
                    insert_data["amount"] = float(insert_data["amount"])
            else:
                insert_data = {
                    "tenant_id": tenant_id,
                    "trans_id": parsed.trans_id,
                    "trans_time": parsed.timestamp.isoformat(),
                    "amount": parsed.amount,
                    "msisdn": parsed.msisdn,
                    "first_name": parsed.first_name,
                    "bill_ref": parsed.bill_ref,
                    "provider": parsed.provider
                }

            db.table("live_transactions").insert(insert_data).execute()
            log.info("c2b_confirmation_db_write_success", trans_id=parsed.trans_id)
        except Exception as e:
            if "duplicate key" in str(e).lower():
                log.info("duplicate_txn_ignored", trans_id=parsed.trans_id)
                return
            log.error("c2b_confirmation_db_write_failed", trans_id=parsed.trans_id, error=str(e))
            raise

        # 4. Notify Tenant
        if tenant:
            text = M.PAYMENT_RECEIVED.format(
                amount=parsed.amount,
                name=parsed.first_name,
                msisdn=parsed.msisdn,
                trans_id=parsed.trans_id
            )
            await bot.send_message(
                chat_id=tenant["telegram_id"],
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
            log.info("payment_notification_sent", tenant=tenant["telegram_id"])
        else:
            log.warn("payment_unmatched", trans_id=parsed.trans_id, msisdn=parsed.msisdn)

    except Exception as e:
        log.error("transaction_processing_failed", error=str(e))
