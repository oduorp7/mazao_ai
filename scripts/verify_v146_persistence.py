import os
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('apps/tg_bot/.env')

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")

if not url or not key:
    print("Error: Missing Supabase credentials")
    exit(1)

# Query for reports created after the v146 deploy (approx 02:04 AM)
# v146 deploy was 2026-05-03T23:04:07Z
query_url = f"{url}/rest/v1/reports?created_at=gt.2026-05-03T23:04:00Z&order=created_at.desc"

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

try:
    resp = httpx.get(query_url, headers=headers)
    resp.raise_for_status()
    reports = resp.json()
    print(f"Total reports generated since v146 deploy: {len(reports)}")
    if reports:
        latest = reports[0]
        print(f"Latest report created at: {latest['created_at']}")
        print(f"Tenant ID: {latest['tenant_id']}")
        print(f"Summary: {latest['summary']}")
except Exception as e:
    print(f"Error querying DB: {e}")
