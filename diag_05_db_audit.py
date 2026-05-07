
import os
from dotenv import load_dotenv
from apps.tg_bot import db

load_dotenv('apps/tg_bot/.env')
client = db.get_client()
tenant_id = 'aea13d22-93c5-4942-b1f6-5febfead3a0c'

def run_diagnostic():
    print("--- STEP 1: Latest 5 Reports ---")
    q1 = client.table('reports').select('id, tenant_id, period, created_at, report_text, summary').eq('tenant_id', tenant_id).order('created_at', desc=True).limit(5).execute()
    for r in q1.data:
        preview = (r.get('report_text') or "")[:100]
        degraded = r.get('summary', {}).get('degraded', False)
        print(f"ID: {r['id']} | Period: {r['period']} | Created: {r['created_at']} | Degraded: {degraded} | Preview: {preview}")

    print("\n--- STEP 2: Reports with non-NULL report_text ---")
    q2 = client.table('reports').select('id, tenant_id, period, created_at, report_text').eq('tenant_id', tenant_id).not_.is_('report_text', 'null').order('created_at', desc=True).execute()
    for r in q2.data:
        preview = (r.get('report_text') or "")[:50]
        print(f"ID: {r['id']} | Period: {r['period']} | Created: {r['created_at']} | Preview: {preview}")

    try:
        print("\n--- STEP 3: Latest 5 Statements ---")
        q3 = client.table('statements').select('id, tenant_id, period, parsed_at').eq('tenant_id', tenant_id).order('parsed_at', desc=True).limit(5).execute()
        for s in q3.data:
            print(f"ID: {s['id']} | Period: {s['period']} | Parsed: {s['parsed_at']}")
    except Exception as e:
        print(f"STEP 3 FAILED: {e}")

if __name__ == "__main__":
    run_diagnostic()
