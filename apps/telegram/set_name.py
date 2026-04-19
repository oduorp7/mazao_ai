import os
import httpx
from dotenv import load_dotenv

load_dotenv()

def rename():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    base = f"https://api.telegram.org/bot{token}"
    
    print(f"📡  UPDATING IDENTITY...")
    r = httpx.post(f"{base}/setMyName", json={"name": "Mazao [LIVE]"})
    print(f"RESULT: {r.json()}")

if __name__ == "__main__":
    rename()
