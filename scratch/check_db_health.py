import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv("apps/tg_bot/.env")

def check_health():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    client = create_client(url, key)

    print("--- Mazao AI DB Health Check ---")
    
    # 1. Check Tables
    tables = ["tenants", "reports", "statements", "token_entries", "fuliza_entries"]
    for table in tables:
        try:
            client.table(table).select("id").limit(1).execute()
            print(f"[OK] Table '{table}' exists.")
        except Exception as e:
            msg = str(e).lower()
            if "pgrst204" in msg or "not find" in msg or "does not exist" in msg:
                print(f"[MISSING] Table '{table}' MISSING.")
            else:
                print(f"[ERROR] Table '{table}' Error: {e}")

    # 2. Check Columns in Tenants
    print("\n--- Column Probe ---")
    required_cols = ["preferred_language", "household_size", "user_type", "employment_status"]
    for col in required_cols:
        try:
            client.table("tenants").select(col).limit(1).execute()
            print(f"[OK] Column 'tenants.{col}' exists.")
        except Exception as e:
            msg = str(e).lower()
            if col in msg and ("not find" in msg or "does not exist" in msg or "pgrst204" in msg):
                print(f"[MISSING] Column 'tenants.{col}' MISSING.")
            else:
                print(f"[ERROR] Column 'tenants.{col}' Error: {e}")

if __name__ == "__main__":
    check_health()
