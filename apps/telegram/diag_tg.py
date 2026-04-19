import os
import httpx
from dotenv import load_dotenv

load_dotenv()

def probe():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    print(f"Token: {token[:10]}...{token[-5:]}")
    
    # 1. getMe
    r = httpx.get(f"https://api.telegram.org/bot{token}/getMe")
    print(f"\ngetMe: {r.status_code}")
    print(r.json())
    
    # 2. getUpdates
    r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates?limit=5")
    print(f"\ngetUpdates: {r.status_code}")
    updates = r.json()
    print(updates)
    
    if updates.get("ok") and updates.get("result"):
        print("\n✅ Found pending updates! The bot SHOULD see these.")
    else:
        print("\n❌ No pending updates found. Either the bot already read them, or they weren't sent to this token.")

if __name__ == "__main__":
    probe()
