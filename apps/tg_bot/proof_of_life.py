import os
import sys
import httpx
import time
from dotenv import load_dotenv

load_dotenv()

def reset_and_ping():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    base_url = f"https://api.telegram.org/bot{token}"
    
    print(f"🚀  Starting connectivity reset for token {token[:10]}...")
    
    # 1. Clear Webhook (CRITICAL)
    print("🧹  Clearing any existing webhooks...")
    r = httpx.post(f"{base_url}/deleteWebhook?drop_pending_updates=False")
    print(f"    Result: {r.json()}")
    
    # 2. Check for pending updates (this will catch your recent messages)
    print("\n📡  Listening for incoming messages (Long Polling)...")
    print("👉  PLEASE SEND A MESSAGE TO THE BOT NOW (e.g. 'HELLO')")
    
    start_time = time.time()
    found_chat_id = None
    
    while time.time() - start_time < 60:  # Wait up to 60 seconds
        r = httpx.get(f"{base_url}/getUpdates?timeout=10&limit=1")
        res = r.json()
        
        if res.get("ok") and res.get("result"):
            upd = res["result"][0]
            msg = upd.get("message", {})
            text = msg.get("text")
            found_chat_id = msg.get("chat", {}).get("id")
            user = msg.get("from", {}).get("first_name", "Unknown")
            
            print(f"\n📢  MESSAGE RECEIVED!")
            print(f"    From: {user}")
            print(f"    Text: {text}")
            print(f"    Chat ID: {found_chat_id}")
            break
        else:
            print(".", end="", flush=True)
            time.sleep(1)
            
    if found_chat_id:
        # 3. Try to SEND a message back
        print(f"\n📤  Attempting direct Ping to {found_chat_id}...")
        payload = {
            "chat_id": found_chat_id,
            "text": "🎯 *PROOF OF LIFE: SUCCESS*\nThe Mazao AI Engine has established a direct link to your session.\n\nI am now restarting the full bot with this verified connection.",
            "parse_mode": "Markdown"
        }
        r = httpx.post(f"{base_url}/sendMessage", json=payload)
        if r.status_code == 200:
            print("✅  Ping delivered! Outgoing connectivity is alive.")
        else:
            print(f"❌  Ping failed: {r.status_code} - {r.text}")
    else:
        print("\n⌛  Timed out. No messages received from Telegram.")

if __name__ == "__main__":
    reset_and_ping()
