import os
import sys
import asyncio
from datetime import datetime

# Add root to sys.path
sys.path.append(os.getcwd())

from apps.agent.mpesa_parser import parse
from apps.tg_bot.db import save_statement, get_latest_statement, get_client
from apps.agent.state import TransactionType

async def verify():
    print("--- Verifying Parser ---")
    with open("test_statement.csv", "r") as f:
        data = f.read()
    
    txs = parse(data, "csv")
    print(f"Parsed {len(txs)} transactions.")
    for tx in txs:
        print(f"  {tx.mpesa_ref}: {tx.amount} ({tx.transaction_type})")

    # Inflows = 3500, Outflows = 1250 (1200 + 50)
    inflows = sum(t.amount for t in txs if t.transaction_type == TransactionType.C2B)
    outflows = sum(t.amount for t in txs if t.transaction_type == TransactionType.B2C)
    print(f"Inflows: {inflows}, Outflows: {outflows}")

    print("\n--- Verifying DB Storage ---")
    # Use a dummy tenant ID for testing (maybe one that exists or create one)
    # For now, let's just try to insert and see if it fails.
    # We need a real tenant UUID if we want to satisfy FK.
    
    client = get_client()
    tenant = client.table("tenants").select("id").limit(1).maybe_single().execute()
    if not tenant.data:
        print("No tenants found in DB. Skipping DB test.")
        return
    
    tenant_id = tenant.data["id"]
    print(f"Using tenant_id: {tenant_id}")
    
    res = save_statement(
        tenant_id=tenant_id,
        period="2026-04",
        total_inflows=inflows,
        total_outflows=outflows,
        net=inflows - outflows,
        vat_estimate=inflows * 0.16
    )
    print(f"Saved statement: {res['id']}")
    
    latest = get_latest_statement(tenant_id)
    print(f"Retrieved latest: {latest['total_inflows']} inflows, {latest['vat_estimate']} VAT")

if __name__ == "__main__":
    asyncio.run(verify())
