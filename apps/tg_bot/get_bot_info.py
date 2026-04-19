import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv
from pathlib import Path

# Load from the correct path
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ No TELEGRAM_BOT_TOKEN found in .env")
        return
        
    bot = Bot(token)
    me = await bot.get_me()
    print("\n[SUCCESS] Bot is Global!")
    print(f"Bot Username: @{me.username}")
    print(f"Bot Link: https://t.me/{me.username}")
    print(f"Bot ID: {me.id}")

if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
