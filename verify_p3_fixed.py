import os
import sys
import asyncio
from datetime import datetime

# Add root and apps/agent to sys.path
root = os.getcwd()
sys.path.append(root)
sys.path.append(os.path.join(root, "apps", "agent"))

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

    inflows = sum(t.amount for t in txs if t.transaction_type == TransactionType.C2B)
    outflows = sum(t.amount for t in txs if t.transaction_type == TransactionType.B2C)
    print(f"Inflows: {inflows}, Outflows: {outflows}")

    print("\n--- Verifying DB Storage ---")
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
    
    print("\n--- Verifying /statement logic output ---")
    # Simulate cmd_statement logic
    text = (
        "📂 *M-Pesa Statement Summary*\n"
        f"Period: {latest.get('period', 'N/A')}\n"
        f"Parsed: {latest.get('parsed_at', '').split('T')[0]}\n\n"
        f"💰 Total Inflows:  KES {latest.get('total_inflows', 0):,.2f}\n"
        f"💸 Total Outflows: KES {latest.get('total_outflows', 0):,.2f}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📈 *Net Amount:    KES {latest.get('net', 0):,.2f}*\n"
    )
    if latest.get("vat_estimate", 0) > 0:
        text += f"\n📋 *Est. VAT Liability: KES {latest.get('vat_estimate', 0):,.2f}*"
        text += "\n_(Label: Clearly an Estimate)_"
    print(text)

if __name__ == "__main__":
    asyncio.run(verify())
