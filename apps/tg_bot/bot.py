"""
bot.py — Mazao AI Telegram Bot

THE entry point. Run this file and the bot is live.

  python bot.py

What this file does:
  1. Loads .env
  2. Sets up structured logging
  3. Registers all command handlers
  4. Starts the APScheduler (daily reports + KRA alerts)
  5. Starts polling Telegram for messages

Nothing else lives here. All logic is in handlers.py, scheduler.py,
pipeline.py (agent), and db.py.
"""

import os
import sys
import asyncio
from pathlib import Path

# ── Windows stability fixes (MUST happen before other imports) ──────────────
if sys.platform == "win32":
    # Ensure emojis don't crash the console
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    
    # SelectorEventLoop is mandatory for PTB + Windows stability
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass

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

load_dotenv()

from apps.tg_bot.handlers import (
    cmd_start,
    cmd_help,
    cmd_report,
    cmd_vat,
    cmd_kra,
    cmd_status,
    cmd_mystatus,
    cmd_language,
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

setup_logging()
log = get_logger(__name__)


def _check_env() -> None:
    """Fail fast if required environment variables are missing."""
    required = [
        "TELEGRAM_BOT_TOKEN",
        "ANTHROPIC_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        log.error("missing_env_vars", missing=missing)
        print(f"\n❌  Missing environment variables: {', '.join(missing)}")
        print("    Copy .env.example to .env and fill them in.\n")
        sys.exit(1)


async def post_init(application: Application) -> None:
    """Called once after the bot starts — set command menu."""
    await application.bot.set_my_commands(BOT_COMMANDS)
    log.info("bot_commands_registered", count=len(BOT_COMMANDS))


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

    # Global error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("unhandled_exception", error=str(context.error))
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️  *Mazao AI Logic Error*\nI encountered an internal error. My engineers have been notified.",
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
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    # Run forever until interrupt
    stop_event = asyncio.Event()
    
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
