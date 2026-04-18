import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler

# Fix Windows encoding
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

# Path setup for handlers
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

load_dotenv()

from handlers import cmd_start

async def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    print(f"DEBUG: Starting with token ending in ...{token[-5:]}")
    
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    
    print("✅  Minimal bot is polling. Press Ctrl+C to stop.")
    await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
