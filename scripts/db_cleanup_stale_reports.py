import os
import httpx
from dotenv import load_dotenv

load_dotenv('apps/tg_bot/.env')

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")

if not url or not key:
    print("Error: Missing Supabase credentials")
    exit(1)

# PostgREST DELETE call
# created_at < '2026-05-03T22:00:00Z' -> created_at=lt.2026-05-03T22:00:00Z
delete_url = f"{url}/rest/v1/reports?created_at=lt.2026-05-03T22:00:00Z"

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

try:
    resp = httpx.delete(delete_url, headers=headers)
    resp.raise_for_status()
    deleted = resp.json()
    print(f"SQL Executed: DELETE FROM reports WHERE created_at < '2026-05-03T22:00:00Z'")
    print(f"Rows deleted: {len(deleted)}")
except Exception as e:
    print(f"Error executing SQL: {e}")
    if hasattr(e, 'response'):
        print(f"Response: {e.response.text}")
