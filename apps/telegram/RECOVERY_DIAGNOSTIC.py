import os
import sys
import httpx
from dotenv import load_dotenv
from anthropic import Anthropic
from supabase import create_client

load_dotenv()

def audit():
    print("═══ Mazao AI FAANG-Grade Healing Diagnostic ═══\n")
    
    # 1. Network / Internet
    print("🌐 Checking Internet Connectivity...")
    try:
        r = httpx.get("https://8.8.8.8", timeout=5)
        print("✅ Internet: REACHABLE")
    except Exception as e:
        print(f"❌ Internet: FAILED ({e})")

    # 2. Telegram API
    print("\n🤖 Checking Telegram Bot API...")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    try:
        r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        if r.status_code == 200:
            print(f"✅ Telegram: AUTH SUCCESS (@{r.json()['result']['username']})")
        else:
            print(f"❌ Telegram: AUTH FAILED ({r.status_code})")
    except Exception as e:
        print(f"❌ Telegram: CONNECTION FAILED ({e})")

    # 3. Supabase API
    print("\n📦 Checking Supabase Persistence...")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    try:
        supabase = create_client(url, key)
        r = supabase.table("tenants").select("count", count="exact").execute()
        print(f"✅ Supabase: CONNECTED (Tenants count: {r.count})")
    except Exception as e:
        print(f"❌ Supabase: CONNECTION FAILED ({e})")

    # 4. Anthropic API (Claude 3.5 Sonnet)
    print("\n🧠 Checking Anthropic AI Engine...")
    apiKey = os.environ.get("ANTHROPIC_API_KEY")
    try:
        client = Anthropic(api_key=apiKey)
        # Low cost check using Haiku
        resp = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}]
        )
        print(f"✅ Anthropic: OPERATIONAL (Claude said: {resp.content[0].text[:5]}...)")
    except Exception as e:
        print(f"❌ Anthropic: FAILED ({e})")

    print("\n═══ Audit Complete ═══")

if __name__ == "__main__":
    audit()
