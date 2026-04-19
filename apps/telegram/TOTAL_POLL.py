import os
import httpx
import time
from dotenv import load_dotenv

load_dotenv()

def poll():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    base = f"https://api.telegram.org/bot{token}"
    
    print(f"🕵️  MONITORING TOKEN: {token[:10]}...")
    print("🧹 CLEARING WEBHOOK...")
    httpx.post(f"{base}/deleteWebhook?drop_pending_updates=True")
    
    offset = 0
    print("📡  LISTENING FOR MESSAGES (60s loop)...")
    print("👉  SEND 'PING' TO THE BOT NOW.")
    
    start = time.time()
    while time.time() - start < 60:
        r = httpx.get(f"{base}/getUpdates?offset={offset}&timeout=5")
        res = r.json()
        
        if res.get("ok") and res.get("result"):
            for upd in res["result"]:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text")
                
                print(f"📥 RECEIVED: '{text}' from {chat_id}")
                
                # REPLY IMMEDIATELY
                httpx.post(f"{base}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "🚨 *ENGINE BYPASS SUCCESS*\nI have received your message directly at the OS level.\n\nNow I know the connection is 100% fine. Fixing the bot now.",
                    "parse_mode": "Markdown"
                })
                print("📤 REPLIED.")
        else:
            print(".", end="", flush=True)
            time.sleep(1)

if __name__ == "__main__":
    poll()
