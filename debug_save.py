
import os
import asyncio
from dotenv import load_dotenv
from apps.tg_bot import db

load_dotenv('apps/tg_bot/.env')

async def test_save():
    client = db.get_client()
    tenant_id = "aea13d22-93c5-4942-b1f6-5febfead3a0c"
    summary = {"income": 100, "expenses": 50, "profit": 50, "statement_id": "test-stmt"}
    narrative = "THIS IS A TEST NARRATIVE"
    period = "2026-05-DEBUG"
    
    print(f"Saving report for {period}...")
    db.save_report(tenant_id, period, summary, report_text=narrative)
    
    print("Fetching back...")
    resp = client.table('reports').select('*').eq('period', period).execute()
    if resp.data:
        r = resp.data[0]
        print(f"ID: {r['id']}")
        print(f"Text in DB: '{r.get('report_text')}'")
        print(f"Len: {len(r.get('report_text')) if r.get('report_text') else 0}")
    else:
        print("Not found!")

if __name__ == "__main__":
    asyncio.run(test_save())
