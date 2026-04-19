import os
import sys
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

# Path setup
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

from dotenv import load_dotenv
load_dotenv()

import db
from pipeline import run_pipeline
from state import RawTransaction, TransactionType

# ── MOCK DATABASE LAYER ──────────────────────────────────────────────────────
class MockDB:
    def get_tenant(self, tid):
        return {"id": "mock-tenant-123", "telegram_id": tid, "status": "trial", "mpesa_till": "123456"}
    def get_all_active_tenants(self):
        return [{"id": "mock-tenant-123", "telegram_id": 999, "status": "trial"}]
    def save_report(self, *args, **kwargs):
        print("💾 [MockDB] Saving report to database...")

# Monkey-patch db module for testing
db.get_tenant = MockDB().get_tenant
db.get_all_active_tenants = MockDB().get_all_active_tenants
db.save_report = MockDB().save_report

async def simulate_logic():
    print("🚀  Starting Mazao AI Logic Simulation (MOCK MODE)\n")
    
    # 1. Agent Pipeline Simulation
    print("🧠  Simulating AI Agent Pipeline (LangGraph + Claude 3.5 Sonnet)...")
    
    # Mock data: A typical M-Pesa receipt string
    sample_txs = [
        RawTransaction(
            mpesa_ref="LMN4567890",
            amount=2500.0,
            phone="0712345678",
            name="PETER OLUOCH",
            shortcode="123456",
            transaction_type=TransactionType.C2B,
            timestamp=datetime.utcnow()
        ),
        RawTransaction(
            mpesa_ref="XYZ0987654",
            amount=1500.0,
            phone="0712345678",
            name="SUPPLIER LTD",
            shortcode="123456",
            transaction_type=TransactionType.B2B,
            timestamp=datetime.utcnow()
        )
    ]
    
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_pipeline(
                tenant_id="mock-tenant-123",
                raw_transactions=sample_txs,
                triggered_by="simulation"
            )
        )
        
        print("\n📝  --- SIMULATED AGENT OUTPUT ---")
        if result.report_text_en:
            print(f"\n{result.report_text_en}\n")
        
        if result.reconciliation:
            r = result.reconciliation
            print(f"📊 [Internal State]: Income=KES {r.total_income}, Expenses=KES {r.total_expenses}")
            
        print("\n✅  Logic Simulation SUCCESS. The engine is ready.")
        
    except Exception as e:
        print(f"❌  Logic Simulation FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(simulate_logic())
