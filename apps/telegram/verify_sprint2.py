import sys
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

# Path setup - add apps/agent to sys.path
AGENT_PATH = str(Path(__file__).parent.parent / "agent")
if AGENT_PATH not in sys.path:
    sys.path.insert(0, AGENT_PATH)

from dotenv import load_dotenv
load_dotenv()

import db
from mpesa_parser import parse

async def test_parser_and_pipeline():
    print("\n🧪 [TC-01] Testing MAZ-201/202: CSV Statement -> Pipeline")
    csv_data = """Receipt No,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance
QHF001,2024-04-18 14:30:00,JANE WANJIKU,Completed,3500.00,,3500.00
QHF002,2024-04-18 15:00:00,REVERSAL,Reversed,12000.00,,12000.00
QHF003,2024-04-18 16:00:00,NAIVAS,Completed,,4800.00,-1300.00
"""
    txs = parse(csv_data, "csv")
    print(f"✅ Expected 2 completed transactions, Parsed: {len(txs)}")
    
    if len(txs) != 2:
        print("❌ Transaction count mismatch!")
        return

    from pipeline import run_pipeline
    print("🧠 Running pipeline with parsed data...")
    
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: run_pipeline(
            tenant_id="verification-test",
            raw_transactions=txs,
            triggered_by="verification_script"
        )
    )
    
    print(f"✅ Pipeline complete. Report length: {len(result.report_text_en)} chars")
    print("📝 --- SNIPPET ---")
    print(result.report_text_en[:300] + "...")

async def test_obligation_engine():
    print("\n🧪 [TC-02/03] Testing MAZ-204: Individual Obligations Engine")
    
    # We need to monkeypatch db.get_tenant because get_individual_obligations calls it
    import db as db_module
    
    original_get_tenant = db_module.get_tenant
    
    def test_status(status_name, status_value):
        print(f"\nScenario: {status_name}")
        def mock_get(tid):
            return {
                "id": "mock-indiv", 
                "user_type": "individual", 
                "employment_status": status_value,
                "full_name": "Test User"
            }
        db_module.get_tenant = mock_get
        obs = db_module.get_individual_obligations(123)
        print(f"✅ Found {len(obs)} obligations")
        for o in obs:
            days_left = (o['due_date'].date() - datetime.now().date()).days
            print(f"  - [{o['name']}] Due {o['due_date'].strftime('%Y-%m-%d')} ({days_left} days left)")

    test_status("Employed", "employed")
    test_status("Unemployed", "unemployed")
    test_status("Self-Employed", "self_employed")

    db_module.get_tenant = original_get_tenant

if __name__ == "__main__":
    asyncio.run(test_parser_and_pipeline())
    asyncio.run(test_obligation_engine())
