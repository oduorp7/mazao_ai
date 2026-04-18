"""
AgentState — the single source of truth that flows through every node
in the LangGraph pipeline.

Design principles (FAANG):
- Immutable fields are set once and never mutated
- Mutable lists use Annotated[list, operator.add] so LangGraph can
  merge parallel node outputs without clobbering each other
- Every field has a default so nodes can be tested in isolation
- Error fields are explicit — no silent failures via None
"""

from __future__ import annotations

import operator
from enum import Enum
from typing import Annotated, Optional
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class TransactionType(str, Enum):
    C2B = "C2B"          # Customer to Business (income)
    B2C = "B2C"          # Business to Customer (payout)
    B2B = "B2B"          # Business to Business
    REVERSAL = "REVERSAL"
    UNKNOWN = "UNKNOWN"


class TransactionCategory(str, Enum):
    SALES = "SALES"
    SUPPLIER = "SUPPLIER"
    SALARY = "SALARY"
    TAX = "TAX"
    TRANSFER = "TRANSFER"
    REFUND = "REFUND"
    UNKNOWN = "UNKNOWN"


class ObligationType(str, Enum):
    VAT = "VAT"
    PAYE = "PAYE"
    WHT = "WHT"
    NSSF = "NSSF"
    NHIF = "NHIF"


class NodeStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class RawTransaction(BaseModel):
    """Raw M-Pesa event exactly as received from Daraja webhook."""
    mpesa_ref: str
    amount: float
    phone: str
    name: str
    shortcode: str
    transaction_type: TransactionType
    timestamp: datetime
    bill_ref: Optional[str] = None
    raw_payload: dict = Field(default_factory=dict)


class CategorizedTransaction(BaseModel):
    """Transaction after AI categorization."""
    mpesa_ref: str
    amount: float
    phone: str
    name: str
    transaction_type: TransactionType
    category: TransactionCategory
    confidence: float          # 0.0 – 1.0
    needs_review: bool = False
    timestamp: datetime
    categorization_reasoning: Optional[str] = None


class ReconciliationSummary(BaseModel):
    """Output of the reconcile node."""
    period_start: datetime
    period_end: datetime
    total_income: float = 0.0
    total_expenses: float = 0.0
    net_profit: float = 0.0
    transaction_count: int = 0
    flagged_count: int = 0
    top_customers: list[dict] = Field(default_factory=list)
    category_breakdown: dict[str, float] = Field(default_factory=dict)


class VATReturn(BaseModel):
    """Pre-filled VAT-3 data."""
    period: str                    # e.g. "2026-03"
    gross_sales: float = 0.0
    exempt_sales: float = 0.0
    taxable_sales: float = 0.0
    output_vat: float = 0.0        # 16% of taxable_sales
    input_vat: float = 0.0         # claimable from supplier purchases
    net_vat_payable: float = 0.0
    vat_refund: float = 0.0


class KRAObligation(BaseModel):
    """A single upcoming KRA deadline."""
    obligation_type: ObligationType
    due_date: datetime
    estimated_amount: float
    penalty_per_month: float
    days_until_due: int
    is_overdue: bool = False


class NodeResult(BaseModel):
    """Tracks outcome of every node — nothing fails silently."""
    node: str
    status: NodeStatus
    duration_ms: float
    error: Optional[str] = None
    retry_count: int = 0


# ---------------------------------------------------------------------------
# Top-level state
# ---------------------------------------------------------------------------

class AgentState(BaseModel):
    """
    The complete state object passed between LangGraph nodes.

    Annotated[list, operator.add] tells LangGraph to *append* when
    merging parallel branches rather than replacing the whole list.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    tenant_id: str
    run_id: str                        # UUID for this pipeline execution
    triggered_by: str = "webhook"      # webhook | scheduled | manual

    # ── Input ─────────────────────────────────────────────────────────────
    raw_transactions: list[RawTransaction] = Field(default_factory=list)
    report_period_start: Optional[datetime] = None
    report_period_end: Optional[datetime] = None

    # ── Processing (mutated as pipeline progresses) ────────────────────────
    categorized_transactions: list[CategorizedTransaction] = Field(default_factory=list)
    reconciliation: Optional[ReconciliationSummary] = None
    vat_return: Optional[VATReturn] = None
    upcoming_obligations: list[KRAObligation] = Field(default_factory=list)

    # ── Output ────────────────────────────────────────────────────────────
    report_text_en: Optional[str] = None   # English WhatsApp message
    report_text_sw: Optional[str] = None   # Swahili WhatsApp message
    whatsapp_sent: bool = False
    whatsapp_message_id: Optional[str] = None

    # ── Observability — appended by every node ────────────────────────────
    node_results: Annotated[list[NodeResult], operator.add] = Field(default_factory=list)
    errors: Annotated[list[str], operator.add] = Field(default_factory=list)

    # ── Control flow ──────────────────────────────────────────────────────
    should_abort: bool = False         # set True → pipeline short-circuits
    abort_reason: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
