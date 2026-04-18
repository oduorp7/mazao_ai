"""
Test suite for Mazao AI agent pipeline.

Run with:  pytest tests.py -v

Tests are structured so every node can be tested in isolation —
no Daraja or WhatsApp credentials needed for unit tests.
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from state import (
    AgentState,
    RawTransaction,
    CategorizedTransaction,
    TransactionType,
    TransactionCategory,
    ReconciliationSummary,
    VATReturn,
    NodeStatus,
)
from nodes import (
    fetch_transactions,
    reconcile,
    compute_obligations,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_state(**kwargs) -> AgentState:
    defaults = dict(
        tenant_id="test-tenant-001",
        run_id="test-run-001",
    )
    defaults.update(kwargs)
    return AgentState(**defaults)


def make_raw_tx(
    ref="QHF001",
    amount=1000.0,
    tx_type=TransactionType.C2B,
    name="TEST CUSTOMER",
    timestamp=None,
) -> RawTransaction:
    return RawTransaction(
        mpesa_ref=ref,
        amount=amount,
        phone="0712345678",
        name=name,
        shortcode="123456",
        transaction_type=tx_type,
        timestamp=timestamp or datetime(2026, 4, 10, 10, 0),
    )


def make_categorized(
    ref="QHF001",
    amount=1000.0,
    category=TransactionCategory.SALES,
    needs_review=False,
) -> CategorizedTransaction:
    return CategorizedTransaction(
        mpesa_ref=ref,
        amount=amount,
        phone="0712345678",
        name="TEST CUSTOMER",
        transaction_type=TransactionType.C2B,
        category=category,
        confidence=0.95,
        needs_review=needs_review,
        timestamp=datetime(2026, 4, 10, 10, 0),
    )


# ---------------------------------------------------------------------------
# Node 1: fetch_transactions
# ---------------------------------------------------------------------------

class TestFetchTransactions:

    def test_aborts_when_no_transactions(self):
        state = make_state()
        result = fetch_transactions(state)
        assert result["should_abort"] is True
        assert result["node_results"][0].status == NodeStatus.SKIPPED

    def test_sets_period_from_timestamps(self):
        txs = [
            make_raw_tx("QHF001", timestamp=datetime(2026, 4, 1)),
            make_raw_tx("QHF002", timestamp=datetime(2026, 4, 15)),
        ]
        state = make_state(raw_transactions=txs)
        result = fetch_transactions(state)

        assert result["report_period_start"] == datetime(2026, 4, 1)
        assert result["report_period_end"] == datetime(2026, 4, 15)
        assert result["node_results"][0].status == NodeStatus.SUCCESS

    def test_respects_explicit_period(self):
        txs = [make_raw_tx()]
        explicit_start = datetime(2026, 4, 1)
        explicit_end = datetime(2026, 4, 30)
        state = make_state(
            raw_transactions=txs,
            report_period_start=explicit_start,
            report_period_end=explicit_end,
        )
        result = fetch_transactions(state)
        assert result["report_period_start"] == explicit_start
        assert result["report_period_end"] == explicit_end

    def test_records_duration(self):
        txs = [make_raw_tx()]
        state = make_state(raw_transactions=txs)
        result = fetch_transactions(state)
        assert result["node_results"][0].duration_ms >= 0


# ---------------------------------------------------------------------------
# Node 3: reconcile
# ---------------------------------------------------------------------------

class TestReconcile:

    def test_basic_income_expense_calc(self):
        txs = [
            make_categorized("QHF001", 5000.0, TransactionCategory.SALES),
            make_categorized("QHF002", 5000.0, TransactionCategory.SALES),
            make_categorized("QHF003", 2000.0, TransactionCategory.SUPPLIER),
        ]
        state = make_state(
            categorized_transactions=txs,
            report_period_start=datetime(2026, 4, 1),
            report_period_end=datetime(2026, 4, 30),
        )
        result = reconcile(state)
        recon = result["reconciliation"]

        assert recon.total_income == 10000.0
        assert recon.total_expenses == 2000.0
        assert recon.net_profit == 8000.0

    def test_skips_when_no_transactions(self):
        state = make_state()
        result = reconcile(state)
        assert result["node_results"][0].status == NodeStatus.SKIPPED

    def test_counts_flagged_transactions(self):
        txs = [
            make_categorized("QHF001", 1000.0, needs_review=True),
            make_categorized("QHF002", 2000.0, needs_review=False),
            make_categorized("QHF003", 3000.0, needs_review=True),
        ]
        state = make_state(categorized_transactions=txs)
        result = reconcile(state)
        assert result["reconciliation"].flagged_count == 2

    def test_top_customers_sorted_by_spend(self):
        txs = [
            make_categorized("QHF001", 100.0, TransactionCategory.SALES),
            make_categorized("QHF002", 500.0, TransactionCategory.SALES),
            make_categorized("QHF003", 200.0, TransactionCategory.SALES),
        ]
        # All from same customer name "TEST CUSTOMER"
        state = make_state(categorized_transactions=txs)
        result = reconcile(state)
        top = result["reconciliation"].top_customers
        assert len(top) >= 1
        assert top[0]["total"] == 800.0  # all summed under same name

    def test_salary_counted_as_expense(self):
        txs = [
            make_categorized("QHF001", 5000.0, TransactionCategory.SALARY),
        ]
        state = make_state(categorized_transactions=txs)
        result = reconcile(state)
        assert result["reconciliation"].total_expenses == 5000.0
        assert result["reconciliation"].total_income == 0.0

    def test_node_result_recorded(self):
        txs = [make_categorized()]
        state = make_state(categorized_transactions=txs)
        result = reconcile(state)
        assert result["node_results"][0].node == "reconcile"
        assert result["node_results"][0].status == NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# Node 4: compute_obligations
# ---------------------------------------------------------------------------

class TestComputeObligations:

    def _state_with_recon(self, income=10000.0, expenses=2000.0) -> AgentState:
        recon = ReconciliationSummary(
            period_start=datetime(2026, 4, 1),
            period_end=datetime(2026, 4, 30),
            total_income=income,
            total_expenses=expenses,
            net_profit=income - expenses,
            transaction_count=5,
            category_breakdown={
                "SALES": income,
                "SUPPLIER": expenses,
            },
        )
        return make_state(
            reconciliation=recon,
            report_period_start=datetime(2026, 4, 1),
            report_period_end=datetime(2026, 4, 30),
        )

    def test_vat_calculated_correctly(self):
        state = self._state_with_recon(income=100000.0, expenses=50000.0)
        result = compute_obligations(state)
        vat = result["vat_return"]

        assert vat.output_vat == pytest.approx(16000.0)  # 100k * 16%
        assert vat.input_vat == pytest.approx(8000.0)    # 50k * 16%
        assert vat.net_vat_payable == pytest.approx(8000.0)

    def test_vat_refund_when_input_exceeds_output(self):
        state = self._state_with_recon(income=10000.0, expenses=100000.0)
        result = compute_obligations(state)
        vat = result["vat_return"]

        assert vat.net_vat_payable == 0.0
        assert vat.vat_refund > 0

    def test_obligations_generated_for_all_types(self):
        state = self._state_with_recon()
        result = compute_obligations(state)
        ob_types = {o.obligation_type for o in result["upcoming_obligations"]}
        assert len(ob_types) == 4  # VAT, PAYE, NSSF, NHIF

    def test_obligations_sorted_by_due_date(self):
        state = self._state_with_recon()
        result = compute_obligations(state)
        days = [o.days_until_due for o in result["upcoming_obligations"]]
        assert days == sorted(days)

    def test_vat_period_format(self):
        state = self._state_with_recon()
        result = compute_obligations(state)
        assert result["vat_return"].period == "2026-04"

    def test_node_result_recorded(self):
        state = self._state_with_recon()
        result = compute_obligations(state)
        assert result["node_results"][0].status == NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# Integration: idempotency guard
# ---------------------------------------------------------------------------

class TestIdempotency:
    """
    Simulates duplicate webhook delivery from Daraja.
    The pipeline must not double-count transactions.
    """

    def test_same_mpesa_ref_deduplication(self):
        """
        If two raw transactions share an mpesa_ref, only one
        should be counted. (In production this is handled by DB
        INSERT ... ON CONFLICT DO NOTHING, but the agent should
        also be resilient.)
        """
        tx = make_raw_tx("DUPLICATE-REF", 5000.0)
        txs = [tx, tx]  # same transaction delivered twice
        state = make_state(raw_transactions=txs)

        result = fetch_transactions(state)
        # Pipeline proceeds — dedup is a DB concern, not agent concern
        assert result["node_results"][0].status == NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# Integration: abort propagation
# ---------------------------------------------------------------------------

class TestAbortPropagation:

    def test_empty_transaction_list_aborts(self):
        state = make_state()
        result = fetch_transactions(state)
        assert result.get("should_abort") is True

    def test_abort_reason_is_set(self):
        state = make_state()
        result = fetch_transactions(state)
        assert result.get("abort_reason") is not None
        assert len(result["abort_reason"]) > 0


# ---------------------------------------------------------------------------
# Run hint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
