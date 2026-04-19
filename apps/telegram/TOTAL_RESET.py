import os
import httpx
from dotenv import load_dotenv

load_dotenv()

def reset():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    base = f"https://api.telegram.org/bot{token}"
    
    print(f"Token: {token[:10]}...")
    
    # 1. getMe
    r = httpx.get(f"{base}/getMe")
    me = r.json()
    print(f"ME: {me['result']['username']} (ID: {me['result']['id']})")
    
    # 2. deleteWebhook
    print("🧹 CLEARING WEBHOOK...")
    r = httpx.post(f"{base}/deleteWebhook?drop_pending_updates=True")
    print(f"WEBHOOK RESULT: {r.json()}")
    
    # 3. getUpdates check
    r = httpx.get(f"{base}/getUpdates")
    print(f"UPDATES: {r.json()}")

if __name__ == "__main__":
    reset()
