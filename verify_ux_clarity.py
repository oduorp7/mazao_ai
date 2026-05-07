
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append(os.getcwd())

import apps.agent.nodes as nodes
from apps.agent.state import AgentState, RawTransaction, TransactionType, ReconciliationSummary

def verify():
    print("=== UX_01_FINANCIAL_SURFACE_CLARITY VERIFICATION (RPEK-LITE-V2) ===")
    
    # 1. Setup Mock State
    raw_txs = [
        RawTransaction(
            mpesa_ref="REF123",
            amount=1000.0,
            phone="254712345678",
            name="Customer A",
            shortcode="123456",
            transaction_type=TransactionType.C2B,
            timestamp=datetime.now()
        ),
        RawTransaction(
            mpesa_ref="REF456",
            amount=500.0,
            phone="254712345678",
            name="Supplier B",
            shortcode="123456",
            transaction_type=TransactionType.B2C,
            timestamp=datetime.now()
        )
    ]
    
    recon = ReconciliationSummary(
        period_start=datetime.now(),
        period_end=datetime.now(),
        total_income=1000.0,
        total_expenses=500.0,
        net_profit=500.0,
        transaction_count=2,
        category_breakdown={"SALES": 1000.0, "SUPPLIER": 500.0}
    )
    
    state = AgentState(
        tenant_id="test-tenant",
        run_id="test-run",
        raw_transactions=raw_txs,
        reconciliation=recon,
        report_period_start=datetime.now(),
        report_period_end=datetime.now()
    )
    
    # 2. Test _build_report_prompt
    print("\n[STEP 1: Verify LLM Prompt Instructions]")
    prompt = nodes._build_report_prompt(state)
    
    required_prompt_markers = [
        "Business Performance (AI Categorized)",
        "Raw Statement Totals",
        "Total Inflows: KES 1,000.00",
        "Total Outflows: KES 500.00",
        "Clarity Note: Categorized totals may differ from raw statement totals"
    ]
    
    success = True
    for marker in required_prompt_markers:
        if marker in prompt:
            print(f"✅ Found in Prompt: '{marker}'")
        else:
            print(f"❌ Missing in Prompt: '{marker}'")
            success = False
            
    if not success:
        print("\n--- FULL PROMPT DEBUG ---")
        print(prompt)
        print("--------------------------")

    # 3. Test generate_report Fallback (QA Verification Evidence)
    print("\n[STEP 2: Verify Fallback Report (QA Evidence)]")
    
    # Mock get_llm to trigger fallback
    with patch('apps.agent.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("Simulated LLM Failure for Fallback Verification")
        mock_get_llm.return_value = mock_llm
        
        result = nodes.generate_report(state)
        report_text = result.get("report_text_en", "")
        
        print("\n--- RENDERED FALLBACK REPORT ---")
        print(report_text)
        print("--------------------------------\n")
        
        required_fallback_markers = [
            "*Business Performance (AI Categorized)*",
            "*Raw Statement Totals*",
            "Total Inflows: KES 1,000.00",
            "Total Outflows: KES 500.00",
            "Categorized totals may differ from raw statement totals"
        ]
        
        success_fallback = True
        for marker in required_fallback_markers:
            if marker in report_text:
                print(f"✅ Found in Fallback: '{marker}'")
            else:
                print(f"❌ Missing in Fallback: '{marker}'")
                success_fallback = False
                
    if success and success_fallback:
        print("\n🏆 VERIFICATION SUCCESSFUL: UX_01 logic correctly distinguishes totals.")
    else:
        print("\n⚠️ VERIFICATION FAILED: Missing required labels or logic.")
        sys.exit(1)

if __name__ == "__main__":
    verify()
