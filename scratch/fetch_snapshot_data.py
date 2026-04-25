import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Load env from apps/tg_bot/.env
env_path = Path("apps/tg_bot/.env")
load_dotenv(dotenv_path=env_path)

def fetch_data():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    client = create_client(url, key)

    print("--- TOKEN ENTRIES ---")
    try:
        # User requested: units, purchase_date, amount_paid, created_at
        # We might not have amount_paid, so we'll fetch all and see
        resp = client.table("token_entries").select("*").order("purchase_date", desc=False).execute()
        print(json.dumps(resp.data, indent=2, default=str))
    except Exception as e:
        print(f"ERROR fetching token_entries: {e}")

    print("\n--- TENANT STATE ---")
    try:
        # User requested: telegram_id, user_type, tier, household_type, preferred_language, onboarding_complete
        # 'tier' might be 'plan' in our schema
        # 'onboarding_complete' might be 'onboarding_completed'
        resp = client.table("tenants").select("telegram_id, user_type, plan, household_type, preferred_language, onboarding_completed").execute()
        print(json.dumps(resp.data, indent=2, default=str))
    except Exception as e:
        # Try again with likely column names if first one fails
        try:
             resp = client.table("tenants").select("*").execute()
             print(json.dumps(resp.data, indent=2, default=str))
        except Exception as e2:
             print(f"ERROR fetching tenants: {e2}")

if __name__ == "__main__":
    fetch_data()
