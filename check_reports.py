
import os
import asyncio
from dotenv import load_dotenv
from apps.tg_bot import db

load_dotenv('apps/tg_bot/.env')

def check_reports():
    client = db.get_client()
    resp = client.table('reports').select('id, period, created_at, report_text, summary').gte('created_at', '2026-05-07T00:00:00Z').order('created_at', desc=True).limit(10).execute()
    for r in resp.data:
        text = r.get('report_text')
        summary = r.get('summary', {})
        is_degraded = summary.get('degraded', False)
        stmt_id = summary.get('statement_id')
        print(f"ID: {r['id']}")
        print(f"  Period: {r['period']}")
        print(f"  Created: {r['created_at']}")
        print(f"  Statement ID: {stmt_id}")
        print(f"  Degraded: {is_degraded}")
        print(f"  Text Length: {len(text) if text else 0}")
        if text:
            print(f"  Text Preview: {text[:50]}...")
        print("-" * 20)

if __name__ == "__main__":
    check_reports()
