import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv("apps/tg_bot/.env")

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")

client = create_client(url, key)

try:
    # Attempt to call a common helper RPC for executing SQL
    res = client.rpc("exec_sql", {"cmd": "SELECT 1"}).execute()
    print("Success: exec_sql RPC is available.")
    print(res.data)
except Exception as e:
    print(f"Error: exec_sql RPC is not available or failed. {e}")
