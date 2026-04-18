"""
Mazao AI — M-Pesa Agent Pipeline (LangGraph state machine)

Graph topology:

  [START]
     │
  fetch_transactions ──(abort?)──► [END]
     │
  categorize_transactions ──(no txs?)──► [END]
     │
  reconcile
     │
  compute_obligations
     │
  generate_report
     │
  send_whatsapp
     │
  [END]

Routing: after every node, `route_or_continue` checks state.should_abort.
If True, we short-circuit to END to avoid cascading failures.
"""

from __future__ import annotations

import os
import uuid
import time
from datetime import datetime

from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

from state import AgentState, RawTransaction, TransactionType
from nodes import (
    fetch_transactions,
    categorize_transactions,
    reconcile,
    compute_obligations,
    generate_report,
    send_whatsapp,
)
from utils.logging import get_logger, setup_logging

load_dotenv()
setup_logging()
log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Router — runs after every node
# ---------------------------------------------------------------------------

def route_or_continue(state: AgentState, next_node: str) -> str:
    """
    If the pipeline has been aborted (e.g. empty transaction list, fatal error),
    skip to END rather than propagating failures through remaining nodes.
    """
    if state.should_abort:
        log.warning(
            "pipeline_short_circuit",
            tenant_id=state.tenant_id,
            reason=state.abort_reason,
            skipping_to="END",
        )
        return END
    return next_node


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """
    Construct and compile the LangGraph state machine.
    Call once at startup; the compiled graph is thread-safe and reusable.
    """
    builder = StateGraph(AgentState)

    # ── Register nodes ─────────────────────────────────────────────────────
    builder.add_node("fetch_transactions",      fetch_transactions)
    builder.add_node("categorize_transactions", categorize_transactions)
    builder.add_node("reconcile",               reconcile)
    builder.add_node("compute_obligations",     compute_obligations)
    builder.add_node("generate_report",         generate_report)
    builder.add_node("send_whatsapp",           send_whatsapp)

    # ── Entry point ────────────────────────────────────────────────────────
    builder.set_entry_point("fetch_transactions")

    # ── Conditional edges — abort check after every node ──────────────────
    builder.add_conditional_edges(
        "fetch_transactions",
        lambda s: route_or_continue(s, "categorize_transactions"),
        {"categorize_transactions": "categorize_transactions", END: END},
    )
    builder.add_conditional_edges(
        "categorize_transactions",
        lambda s: route_or_continue(s, "reconcile"),
        {"reconcile": "reconcile", END: END},
    )
    builder.add_conditional_edges(
        "reconcile",
        lambda s: route_or_continue(s, "compute_obligations"),
        {"compute_obligations": "compute_obligations", END: END},
    )
    builder.add_conditional_edges(
        "compute_obligations",
        lambda s: route_or_continue(s, "generate_report"),
        {"generate_report": "generate_report", END: END},
    )
    builder.add_conditional_edges(
        "generate_report",
        lambda s: route_or_continue(s, "send_whatsapp"),
        {"send_whatsapp": "send_whatsapp", END: END},
    )

    # ── Terminal edge ──────────────────────────────────────────────────────
    builder.add_edge("send_whatsapp", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Public runner — called by the FastAPI background task
# ---------------------------------------------------------------------------

def run_pipeline(
    tenant_id: str,
    raw_transactions: list[RawTransaction],
    triggered_by: str = "webhook",
) -> AgentState:
    """
    Execute the full agent pipeline for a tenant.

    Args:
        tenant_id:         UUID of the business/tenant
        raw_transactions:  List of RawTransaction objects from Daraja webhook
        triggered_by:      "webhook" | "scheduled" | "manual"

    Returns:
        Final AgentState after all nodes have run.
    """
    run_id = str(uuid.uuid4())
    pipeline_start = time.perf_counter()

    log.info(
        "pipeline_start",
        tenant_id=tenant_id,
        run_id=run_id,
        triggered_by=triggered_by,
        tx_count=len(raw_transactions),
    )

    graph = build_graph()

    initial_state = AgentState(
        tenant_id=tenant_id,
        run_id=run_id,
        triggered_by=triggered_by,
        raw_transactions=raw_transactions,
    )

    try:
        # LangGraph invoke returns a dictionary matching the AgentState schema
        raw_result = graph.invoke(initial_state)
        final_state = AgentState.model_validate(raw_result)

        duration = round((time.perf_counter() - pipeline_start) * 1000, 2)
        success = final_state.whatsapp_sent
        error_count = len(final_state.errors)

        log.info(
            "pipeline_complete",
            tenant_id=tenant_id,
            run_id=run_id,
            duration_ms=duration,
            whatsapp_sent=success,
            error_count=error_count,
            node_statuses={
                r.node: r.status.value for r in final_state.node_results
            },
        )

        if error_count:
            log.warning(
                "pipeline_completed_with_errors",
                tenant_id=tenant_id,
                run_id=run_id,
                errors=final_state.errors,
            )

        return final_state

    except Exception as exc:
        duration = round((time.perf_counter() - pipeline_start) * 1000, 2)
        log.exception(
            "pipeline_crashed",
            tenant_id=tenant_id,
            run_id=run_id,
            duration_ms=duration,
        )
        raise


# ---------------------------------------------------------------------------
# Local dev runner — execute with:  python pipeline.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from state import RawTransaction, TransactionType

    SAMPLE_TRANSACTIONS = [
        RawTransaction(
            mpesa_ref="QHF4X8ZK1A",
            amount=3500.0,
            phone="0712345678",
            name="JANE WANJIKU",
            shortcode="123456",
            transaction_type=TransactionType.C2B,
            timestamp=datetime(2026, 4, 10, 9, 15),
            bill_ref="ORDER-001",
        ),
        RawTransaction(
            mpesa_ref="QHF4X8ZK1B",
            amount=12000.0,
            phone="0723456789",
            name="KAMAU HARDWARE",
            shortcode="123456",
            transaction_type=TransactionType.C2B,
            timestamp=datetime(2026, 4, 11, 14, 30),
        ),
        RawTransaction(
            mpesa_ref="QHF4X8ZK1C",
            amount=8500.0,
            phone="0734567890",
            name="JOHN MWANGI",
            shortcode="123456",
            transaction_type=TransactionType.B2C,   # salary
            timestamp=datetime(2026, 4, 14, 8, 0),
            bill_ref="SALARY-APR",
        ),
        RawTransaction(
            mpesa_ref="QHF4X8ZK1D",
            amount=4800.0,
            phone="0745678901",
            name="NAIVAS SUPERMARKET",
            shortcode="123456",
            transaction_type=TransactionType.B2B,   # supplier
            timestamp=datetime(2026, 4, 15, 10, 45),
        ),
        RawTransaction(
            mpesa_ref="QHF4X8ZK1E",
            amount=2400.0,
            phone="0756789012",
            name="KRA iTax PAYE",
            shortcode="123456",
            transaction_type=TransactionType.B2C,   # tax payment
            timestamp=datetime(2026, 4, 9, 7, 0),
            bill_ref="PAYE-MAR",
        ),
        RawTransaction(
            mpesa_ref="QHF4X8ZK1F",
            amount=75000.0,            # large — should flag for review
            phone="0767890123",
            name="UNKNOWN CORP LTD",
            shortcode="123456",
            transaction_type=TransactionType.C2B,
            timestamp=datetime(2026, 4, 12, 16, 20),
        ),
    ]

    print("\n" + "=" * 60)
    print("  MAZAO AI — M-Pesa Agent Pipeline (dev run)")
    print("=" * 60 + "\n")

    result = run_pipeline(
        tenant_id="tenant-demo-001",
        raw_transactions=SAMPLE_TRANSACTIONS,
        triggered_by="manual",
    )

    print("\n" + "=" * 60)
    print("  PIPELINE RESULTS")
    print("=" * 60)

    if result.reconciliation:
        r = result.reconciliation
        print(f"\n  Income:    KES {r.total_income:>12,.2f}")
        print(f"  Expenses:  KES {r.total_expenses:>12,.2f}")
        print(f"  Profit:    KES {r.net_profit:>12,.2f}")
        print(f"  Flagged:   {r.flagged_count} transactions")

    if result.vat_return:
        v = result.vat_return
        print(f"\n  VAT payable ({v.period}): KES {v.net_vat_payable:,.2f}")

    print(f"\n  WhatsApp sent: {result.whatsapp_sent}")

    print("\n  Node timing:")
    for nr in result.node_results:
        status_icon = "✓" if nr.status.value == "success" else (
            "⚠" if nr.status.value == "skipped" else "✗"
        )
        print(f"    {status_icon} {nr.node:<30} {nr.duration_ms:>8.1f}ms")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for e in result.errors:
            print(f"    • {e}")

    if result.report_text_en:
        print("\n" + "=" * 60)
        print("  WHATSAPP REPORT (EN)")
        print("=" * 60)
        print(result.report_text_en)

    print("\n")
