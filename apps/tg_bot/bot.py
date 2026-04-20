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
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode

from apps.tg_bot.handlers import (
    cmd_start,
    cmd_help,
    cmd_report,
    cmd_vat,
    cmd_kra,
    cmd_status,
    cmd_mystatus,
    cmd_language,
    cmd_statement,
    cmd_tokens,
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
from apps.tg_bot.scheduler import create_scheduler
from apps.agent.utils.logging import get_logger, setup_logging

load_dotenv()

setup_logging()
log = get_logger(__name__)


def _check_env() -> None:
    """Assertion: Startup audit (P6-T8). Failure on core vars causes clean exit."""
    core = [
        "TELEGRAM_BOT_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "ANTHROPIC_API_KEY",
        "FLY_APP_URL",
    ]
    payment = ["INTASEND_PUBLISHABLE_KEY", "INTASEND_SECRET_KEY", "PAYMENT_PROVIDER"]
    
    missing_core = [k for k in core if not os.getenv(k)]
    if missing_core:
        log.error("critical_env_missing", vars=missing_core)
        print(f"\n❌  CRITICAL: Missing environment variables: {', '.join(missing_core)}")
        print("    Bot cannot start without these core configurations.\n")
        sys.exit(1)

    missing_payment = [k for k in payment if not os.getenv(k)]
    if missing_payment:
        log.warn("payment_env_missing", vars=missing_payment, mode="statement_only")
        print(f"\n⚠️   WARNING: Payment variables missing: {', '.join(missing_payment)}")
        print("    Bot will run in 'Statement Upload Only' mode.\n")


async def post_init(application: Application) -> None:
    """Called once after the bot starts — set command menu and register webhooks."""
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
        log.info("bot_commands_registered", count=len(BOT_COMMANDS))

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
    from telegram.request import HTTPXRequest

    # Use custom timeouts to overcome local network instability
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

    # ── High-level monitor ────────────────────────────────────────────────
    from telegram.ext import TypeHandler
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
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CommandHandler("statement", cmd_statement))
    app.add_handler(CommandHandler("tokens", cmd_tokens))
    app.add_handler(CommandHandler("fuliza", cmd_fuliza))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("subscriptions", cmd_subscriptions))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(CommandHandler("resume", cmd_resume))

    # All non-command text → conversation handler
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
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

    # ── Start scheduler ───────────────────────────────────────────────────
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
        return web.Response(text="OK", status=200)

    async def payment_webhook(request):
        """P8-T2: Intasend webhooks are POST only. Challenge is in the body."""
        try:
            payload = await request.json()

            # ── Webhook Challenge Validation (P6A2 Addendum) ─────────────
            expected_challenge = os.getenv("INTASEND_WEBHOOK_CHALLENGE", "")
            incoming_challenge = payload.get("challenge", "")

            if expected_challenge and incoming_challenge:
                if incoming_challenge != expected_challenge:
                    log.warn("webhook_challenge_mismatch",
                             expected=expected_challenge[:6] + "...",
                             received=incoming_challenge[:6] + "...")
                    return web.Response(text="Unauthorized", status=401)
                log.info("webhook_challenge_validated")
            
            from apps.payments import get_provider
            provider = get_provider()
            parsed = await provider.handle_webhook(payload)

            if parsed:
                # Fire-and-forget processing
                asyncio.create_task(process_live_transaction(app.bot, parsed))

            return web.Response(text="OK", status=200)
        except Exception as e:
            log.error("webhook_handler_error", error=str(e))
            return web.Response(text="OK", status=200)

    health_app = web.Application()
    health_app.router.add_get("/health", health_check)
    health_app.router.add_post("/payments/confirm", payment_webhook)
    health_app.router.add_post("/payments/webhook", payment_webhook)
    
    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    log.info("webhook_server_live", port=8080)

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


if __name__ == "__main__":
    asyncio.run(main())


async def process_live_transaction(bot, parsed):
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
                    "confirmed_at": datetime.utcnow().isoformat()
                }).eq("id", request_data["id"]).execute()
                
                # Determine Plan
                new_plan = "biashara" if amount >= 2500 else "mtu_wenyewe"
                
                # Update Tenant
                expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat()
                db.table("tenants").update({
                    "plan": new_plan,
                    "subscription_active": True,
                    "subscription_expires_at": expires_at,
                    "trial_started_at": None, # End trial logic upon payment
                    "trial_ends_at": None
                }).eq("id", tenant_id).execute()
                
                # Notify User
                # Get tenant telegram_id
                t_resp = db.table("tenants").select("telegram_id").eq("id", tenant_id).maybe_single().execute()
                if t_resp and t_resp.data:
                    await bot.send_message(
                        chat_id=t_resp.data["telegram_id"],
                        text=M.PAYMENT_CONFIRMED.format(
                            plan_name=new_plan.title().replace("_", " "),
                            amount=parsed.amount
                        ),
                        parse_mode=ParseMode.MARKDOWN
                    )
                return
            else:
                log.warn("subscription_payment_unmatched", ref=parsed.bill_ref)

        # ── 2. Match Tenant for Live Feed (Regular Payment) ──────────────────
        tenant = None
        resp = db.table("tenants").select("*").eq("till_number", parsed.bill_ref).maybe_single().execute()
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
            db.table("live_transactions").insert({
                "tenant_id": tenant_id,
                "trans_id": parsed.trans_id,
                "trans_time": parsed.timestamp.isoformat(),
                "amount": parsed.amount,
                "msisdn": parsed.msisdn,
                "first_name": parsed.first_name,
                "bill_ref": parsed.bill_ref,
                "provider": parsed.provider
            }).execute()
        except Exception as e:
            if "duplicate key" in str(e).lower():
                log.info("duplicate_txn_ignored", trans_id=parsed.trans_id)
                return
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
