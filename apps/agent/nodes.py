"""
LangGraph nodes for the Mazao AI M-Pesa agent pipeline.

Each node:
  1. Receives the full AgentState
  2. Does ONE thing well
  3. Returns a dict of ONLY the fields it modifies (LangGraph merges)
  4. Never raises — always catches and writes to state.errors
  5. Records its outcome in node_results for observability

Node execution order:
  fetch_transactions
       ↓
  categorize_transactions   (calls Claude API)
       ↓
  reconcile
       ↓
  compute_obligations        (KRA deadline engine)
       ↓
  generate_report            (calls Claude API)
       ↓
  send_whatsapp
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any

import httpx
from anthropic import Anthropic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from state import (
    AgentState,
    CategorizedTransaction,
    TransactionCategory,
    TransactionType,
    ReconciliationSummary,
    VATReturn,
    KRAObligation,
    ObligationType,
    NodeResult,
    NodeStatus,
)
from utils.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(
    node: str,
    status: NodeStatus,
    start: float,
    error: str | None = None,
    retry_count: int = 0,
) -> NodeResult:
    return NodeResult(
        node=node,
        status=status,
        duration_ms=round((time.perf_counter() - start) * 1000, 2),
        error=error,
        retry_count=retry_count,
    )


def _abort(state: AgentState, reason: str) -> dict:
    """Return an abort signal — the router will skip remaining nodes."""
    log.error("pipeline_abort", tenant_id=state.tenant_id, reason=reason)
    return {"should_abort": True, "abort_reason": reason, "errors": [reason]}


# ---------------------------------------------------------------------------
# KRA obligation calendar (static, extend as needed)
# ---------------------------------------------------------------------------

KRA_CALENDAR: dict[ObligationType, dict] = {
    ObligationType.VAT: {
        "due_day": 20,            # 20th of following month
        "frequency": "monthly",
        "penalty_pct": 0.05,
    },
    ObligationType.PAYE: {
        "due_day": 9,             # 9th of following month
        "frequency": "monthly",
        "penalty_pct": 0.05,
    },
    ObligationType.NSSF: {
        "due_day": 15,
        "frequency": "monthly",
        "penalty_pct": 0.05,
    },
    ObligationType.NHIF: {
        "due_day": 9,
        "frequency": "monthly",
        "penalty_pct": 0.025,
    },
}

VAT_RATE = 0.16


# ============================================================================
# NODE 1 — fetch_transactions
# ============================================================================

def fetch_transactions(state: AgentState) -> dict:
    """
    In a real deployment this node would call the Daraja Transaction Status
    API to pull recent C2B transactions for the tenant's shortcode.

    For the pipeline we work with whatever raw_transactions were injected
    by the webhook handler or the scheduler. This node validates and
    normalises them, and sets the report period if not already set.
    """
    node_name = "fetch_transactions"
    start = time.perf_counter()

    log.info(
        "node_start",
        node=node_name,
        tenant_id=state.tenant_id,
        run_id=state.run_id,
        tx_count=len(state.raw_transactions),
    )

    try:
        if not state.raw_transactions:
            return {
                "node_results": [_record(node_name, NodeStatus.SKIPPED, start)],
                **_abort(state, "No transactions to process"),
            }

        # Derive period from transaction timestamps if not supplied
        timestamps = [t.timestamp for t in state.raw_transactions]
        period_start = state.report_period_start or min(timestamps)
        period_end = state.report_period_end or max(timestamps)

        log.info(
            "node_success",
            node=node_name,
            tenant_id=state.tenant_id,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            tx_count=len(state.raw_transactions),
        )

        return {
            "report_period_start": period_start,
            "report_period_end": period_end,
            "node_results": [_record(node_name, NodeStatus.SUCCESS, start)],
        }

    except Exception as exc:
        msg = f"{node_name} failed: {exc}"
        log.exception("node_error", node=node_name, tenant_id=state.tenant_id)
        return {
            "errors": [msg],
            "node_results": [_record(node_name, NodeStatus.FAILED, start, error=str(exc))],
            **_abort(state, msg),
        }


# ============================================================================
# NODE 2 — categorize_transactions
# ============================================================================

CATEGORIZATION_SYSTEM_PROMPT = """\
You are a Kenyan business bookkeeper. Your job is to categorise M-Pesa
transactions for a small business owner.

Categories (use EXACTLY these strings):
- SALES      : payments received from customers
- SUPPLIER   : payments made to suppliers or vendors
- SALARY     : payments to employees (recurring same amount weekly/monthly)
- TAX        : payments to KRA, NSSF, NHIF or other statutory bodies
- TRANSFER   : owner withdrawals or inter-account transfers
- REFUND     : money returned to a customer
- UNKNOWN    : cannot determine with confidence

Rules:
- If "KRA", "iTax", "NSSF", "NHIF" appears in name or bill_ref → TAX
- C2B (money IN) with amount > 0 → likely SALES unless name suggests otherwise
- B2C (money OUT) with recurring same amount → likely SALARY
- Amounts > KES 50,000 from/to unknown numbers → set needs_review=true
- confidence must be between 0.0 and 1.0

Respond with a JSON array, one object per transaction, in input order:
[
  {
    "mpesa_ref": "...",
    "category": "SALES",
    "confidence": 0.95,
    "needs_review": false,
    "reasoning": "C2B payment from retail customer"
  },
  ...
]

Return ONLY the JSON array. No markdown, no explanation."""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, Exception)),
    reraise=False,
)
def _call_claude_categorize(transactions: list[dict], client: Anthropic) -> list[dict]:
    """Isolated Claude call with tenacity retry — keeps the node clean."""
    import json

    tx_text = json.dumps(transactions, indent=2, default=str)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=CATEGORIZATION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Categorise these transactions:\n\n{tx_text}",
            }
        ],
    )

    raw = response.content[0].text.strip()
    return json.loads(raw)


def _rule_based_categorize(tx: Any) -> dict:
    """
    Deterministic fallback if Claude is unavailable.
    Simple but correct — better than returning nothing.
    """
    name_upper = (tx.name or "").upper()
    ref_upper = (tx.bill_ref or "").upper()

    if any(k in name_upper or k in ref_upper for k in ["KRA", "ITAX", "NSSF", "NHIF"]):
        return {"category": "TAX", "confidence": 0.9, "needs_review": False}

    if tx.transaction_type == TransactionType.C2B:
        return {"category": "SALES", "confidence": 0.7, "needs_review": tx.amount > 50000}

    if tx.transaction_type == TransactionType.B2C:
        return {"category": "TRANSFER", "confidence": 0.6, "needs_review": tx.amount > 50000}

    return {"category": "UNKNOWN", "confidence": 0.3, "needs_review": True}


def categorize_transactions(state: AgentState) -> dict:
    """
    Calls Claude to categorise every raw transaction.
    Falls back to rule-based if Claude fails all retries.
    """
    node_name = "categorize_transactions"
    start = time.perf_counter()
    retry_count = 0

    log.info(
        "node_start",
        node=node_name,
        tenant_id=state.tenant_id,
        tx_count=len(state.raw_transactions),
    )

    try:
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        tx_dicts = [
            {
                "mpesa_ref": t.mpesa_ref,
                "amount": t.amount,
                "phone": t.phone,
                "name": t.name,
                "transaction_type": t.transaction_type.value,
                "bill_ref": t.bill_ref,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in state.raw_transactions
        ]

        claude_results: list[dict] = []
        used_fallback = False

        try:
            claude_results = _call_claude_categorize(tx_dicts, client)
            log.info(
                "claude_categorization_complete",
                node=node_name,
                tenant_id=state.tenant_id,
                result_count=len(claude_results),
            )
        except Exception as exc:
            used_fallback = True
            retry_count = 3
            log.warning(
                "claude_categorization_failed_using_fallback",
                node=node_name,
                tenant_id=state.tenant_id,
                error=str(exc),
            )
            # Build a lookup by mpesa_ref for fallback
            claude_results = [
                {"mpesa_ref": t["mpesa_ref"], **_rule_based_categorize(
                    state.raw_transactions[i]
                )}
                for i, t in enumerate(tx_dicts)
            ]

        # Build lookup keyed by mpesa_ref
        result_map = {r["mpesa_ref"]: r for r in claude_results}

        categorized: list[CategorizedTransaction] = []
        for tx in state.raw_transactions:
            result = result_map.get(tx.mpesa_ref, {})
            if not result:
                result = _rule_based_categorize(tx)
                used_fallback = True

            categorized.append(
                CategorizedTransaction(
                    mpesa_ref=tx.mpesa_ref,
                    amount=tx.amount,
                    phone=tx.phone,
                    name=tx.name,
                    transaction_type=tx.transaction_type,
                    category=TransactionCategory(
                        result.get("category", "UNKNOWN")
                    ),
                    confidence=float(result.get("confidence", 0.5)),
                    needs_review=bool(result.get("needs_review", False)),
                    timestamp=tx.timestamp,
                    categorization_reasoning=result.get("reasoning"),
                )
            )

        log.info(
            "node_success",
            node=node_name,
            tenant_id=state.tenant_id,
            used_fallback=used_fallback,
            categorized_count=len(categorized),
            review_count=sum(1 for c in categorized if c.needs_review),
        )

        return {
            "categorized_transactions": categorized,
            "node_results": [
                _record(node_name, NodeStatus.SUCCESS, start, retry_count=retry_count)
            ],
        }

    except Exception as exc:
        msg = f"{node_name} failed: {exc}"
        log.exception("node_error", node=node_name, tenant_id=state.tenant_id)
        return {
            "errors": [msg],
            "node_results": [
                _record(node_name, NodeStatus.FAILED, start, error=str(exc))
            ],
        }


# ============================================================================
# NODE 3 — reconcile
# ============================================================================

def reconcile(state: AgentState) -> dict:
    """
    Pure arithmetic node — no external calls.
    Aggregates categorized transactions into a business summary.
    """
    node_name = "reconcile"
    start = time.perf_counter()

    log.info("node_start", node=node_name, tenant_id=state.tenant_id)

    try:
        txs = state.categorized_transactions
        if not txs:
            return {
                "node_results": [_record(node_name, NodeStatus.SKIPPED, start)],
            }

        income_cats = {TransactionCategory.SALES, TransactionCategory.REFUND}
        expense_cats = {
            TransactionCategory.SUPPLIER,
            TransactionCategory.SALARY,
            TransactionCategory.TAX,
            TransactionCategory.TRANSFER,
        }

        total_income = sum(
            t.amount for t in txs if t.category in income_cats
        )
        total_expenses = sum(
            t.amount for t in txs if t.category in expense_cats
        )

        # Category breakdown
        breakdown: dict[str, float] = defaultdict(float)
        for t in txs:
            breakdown[t.category.value] += t.amount

        # Top customers (C2B payers, by total spend)
        customer_spend: dict[str, float] = defaultdict(float)
        for t in txs:
            if t.category == TransactionCategory.SALES:
                key = t.name or t.phone
                customer_spend[key] += t.amount

        top_customers = sorted(
            [{"name": k, "total": v} for k, v in customer_spend.items()],
            key=lambda x: x["total"],
            reverse=True,
        )[:5]

        summary = ReconciliationSummary(
            period_start=state.report_period_start or txs[0].timestamp,
            period_end=state.report_period_end or txs[-1].timestamp,
            total_income=round(total_income, 2),
            total_expenses=round(total_expenses, 2),
            net_profit=round(total_income - total_expenses, 2),
            transaction_count=len(txs),
            flagged_count=sum(1 for t in txs if t.needs_review),
            top_customers=top_customers,
            category_breakdown=dict(breakdown),
        )

        log.info(
            "node_success",
            node=node_name,
            tenant_id=state.tenant_id,
            net_profit=summary.net_profit,
            flagged=summary.flagged_count,
        )

        return {
            "reconciliation": summary,
            "node_results": [_record(node_name, NodeStatus.SUCCESS, start)],
        }

    except Exception as exc:
        msg = f"{node_name} failed: {exc}"
        log.exception("node_error", node=node_name, tenant_id=state.tenant_id)
        return {
            "errors": [msg],
            "node_results": [
                _record(node_name, NodeStatus.FAILED, start, error=str(exc))
            ],
        }


# ============================================================================
# NODE 4 — compute_obligations
# ============================================================================

def compute_obligations(state: AgentState) -> dict:
    """
    Computes KRA deadlines relative to today.
    Also pre-fills VAT-3 from reconciliation data.
    """
    node_name = "compute_obligations"
    start = time.perf_counter()

    log.info("node_start", node=node_name, tenant_id=state.tenant_id)

    try:
        recon = state.reconciliation
        today = datetime.utcnow()

        # ── VAT pre-fill ──────────────────────────────────────────────────
        supplier_spend = recon.category_breakdown.get(
            TransactionCategory.SUPPLIER.value, 0.0
        ) if recon else 0.0

        taxable_sales = recon.total_income if recon else 0.0
        output_vat = round(taxable_sales * VAT_RATE, 2)
        input_vat = round(supplier_spend * VAT_RATE, 2)
        net_vat = round(max(output_vat - input_vat, 0), 2)

        period_str = (state.report_period_start or today).strftime("%Y-%m")
        vat_return = VATReturn(
            period=period_str,
            gross_sales=taxable_sales,
            taxable_sales=taxable_sales,
            output_vat=output_vat,
            input_vat=input_vat,
            net_vat_payable=net_vat,
            vat_refund=round(max(input_vat - output_vat, 0), 2),
        )

        # ── Upcoming obligations ──────────────────────────────────────────
        obligations: list[KRAObligation] = []
        for ob_type, config in KRA_CALENDAR.items():
            # Due on config["due_day"] of the NEXT month from period end
            ref_date = state.report_period_end or today
            next_month = (ref_date.replace(day=1) + timedelta(days=32)).replace(day=1)
            due_date = next_month.replace(day=config["due_day"])

            days_until = (due_date.date() - today.date()).days

            # Estimate obligation amount
            if ob_type == ObligationType.VAT:
                amount = net_vat
            elif ob_type in (ObligationType.PAYE, ObligationType.NSSF, ObligationType.NHIF):
                salary_total = recon.category_breakdown.get(
                    TransactionCategory.SALARY.value, 0.0
                ) if recon else 0.0
                amount = round(salary_total * 0.30, 2)  # rough PAYE estimate
            else:
                amount = 0.0

            obligations.append(
                KRAObligation(
                    obligation_type=ob_type,
                    due_date=due_date,
                    estimated_amount=amount,
                    penalty_per_month=round(amount * config["penalty_pct"], 2),
                    days_until_due=days_until,
                    is_overdue=days_until < 0,
                )
            )

        # Sort: overdue first, then soonest
        obligations.sort(key=lambda x: x.days_until_due)

        log.info(
            "node_success",
            node=node_name,
            tenant_id=state.tenant_id,
            vat_payable=net_vat,
            obligations_count=len(obligations),
            overdue_count=sum(1 for o in obligations if o.is_overdue),
        )

        return {
            "vat_return": vat_return,
            "upcoming_obligations": obligations,
            "node_results": [_record(node_name, NodeStatus.SUCCESS, start)],
        }

    except Exception as exc:
        msg = f"{node_name} failed: {exc}"
        log.exception("node_error", node=node_name, tenant_id=state.tenant_id)
        return {
            "errors": [msg],
            "node_results": [
                _record(node_name, NodeStatus.FAILED, start, error=str(exc))
            ],
        }


# ============================================================================
# NODE 5 — generate_report
# ============================================================================

REPORT_SYSTEM_PROMPT = """\
You are a friendly business advisor for Kenyan small business owners.
Write a WhatsApp business report — concise, warm, actionable.
Use M-Pesa-style formatting with bold via *asterisks*.
Keep under 400 words.
Use Kenyan shilling (KES) notation.
Mention specific numbers from the data.
End with ONE clear next action.
Write in {language}."""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=False,
)
def _call_claude_report(prompt: str, language: str, client: Anthropic) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=REPORT_SYSTEM_PROMPT.format(language=language),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _build_report_prompt(state: AgentState) -> str:
    r = state.reconciliation
    v = state.vat_return
    obs = state.upcoming_obligations

    next_ob = obs[0] if obs else None
    next_ob_str = (
        f"{next_ob.obligation_type.value} due in {next_ob.days_until_due} days "
        f"(est. KES {next_ob.estimated_amount:,.0f})"
        if next_ob else "No immediate obligations"
    )

    return f"""
Business report data:
- Period: {state.report_period_start} to {state.report_period_end}
- Total income: KES {r.total_income:,.0f if r else 0}
- Total expenses: KES {r.total_expenses:,.0f if r else 0}
- Net profit: KES {r.net_profit:,.0f if r else 0}
- Transactions: {r.transaction_count if r else 0}
- Flagged for review: {r.flagged_count if r else 0}
- Top customers: {r.top_customers[:3] if r else []}
- VAT payable this month: KES {v.net_vat_payable:,.0f if v else 0}
- Most urgent KRA obligation: {next_ob_str}
- Errors during processing: {state.errors}

Write the WhatsApp report now.
""".strip()


def generate_report(state: AgentState) -> dict:
    """
    Calls Claude to write bilingual (English + Swahili) WhatsApp reports.
    Falls back to a template-based report if Claude fails.
    """
    node_name = "generate_report"
    start = time.perf_counter()

    log.info("node_start", node=node_name, tenant_id=state.tenant_id)

    try:
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        prompt = _build_report_prompt(state)

        report_en: str = ""
        report_sw: str = ""

        try:
            report_en = _call_claude_report(prompt, "English", client)
            report_sw = _call_claude_report(prompt, "Swahili", client)
        except Exception as exc:
            log.warning(
                "claude_report_failed_using_template",
                node=node_name,
                tenant_id=state.tenant_id,
                error=str(exc),
            )
            r = state.reconciliation
            v = state.vat_return
            report_en = (
                f"📊 *Business Report*\n\n"
                f"💰 *Income:* KES {r.total_income:,.0f if r else 0}\n"
                f"💸 *Expenses:* KES {r.total_expenses:,.0f if r else 0}\n"
                f"📈 *Profit:* KES {r.net_profit:,.0f if r else 0}\n"
                f"📋 *VAT due:* KES {v.net_vat_payable:,.0f if v else 0}\n\n"
                f"⚠️ Flagged: {r.flagged_count if r else 0} transactions need review.\n\n"
                f"Reply *HELP* for details."
            )
            report_sw = report_en  # fallback — improve later

        log.info(
            "node_success",
            node=node_name,
            tenant_id=state.tenant_id,
            en_length=len(report_en),
            sw_length=len(report_sw),
        )

        return {
            "report_text_en": report_en,
            "report_text_sw": report_sw,
            "node_results": [_record(node_name, NodeStatus.SUCCESS, start)],
        }

    except Exception as exc:
        msg = f"{node_name} failed: {exc}"
        log.exception("node_error", node=node_name, tenant_id=state.tenant_id)
        return {
            "errors": [msg],
            "node_results": [
                _record(node_name, NodeStatus.FAILED, start, error=str(exc))
            ],
        }


# ============================================================================
# NODE 6 — send_whatsapp
# ============================================================================

WHATSAPP_API_URL = (
    "https://graph.facebook.com/v19.0/{phone_number_id}/messages"
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    reraise=True,
)
def _dispatch_whatsapp(
    to: str, body: str, phone_number_id: str, token: str
) -> str:
    """Returns WhatsApp message_id on success, raises on failure."""
    url = WHATSAPP_API_URL.format(phone_number_id=phone_number_id)
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body, "preview_url": False},
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["messages"][0]["id"]


def send_whatsapp(state: AgentState) -> dict:
    """
    Sends the generated report to the tenant's WhatsApp number.
    Sends English report — extend to detect preferred language per tenant.
    """
    node_name = "send_whatsapp"
    start = time.perf_counter()

    log.info("node_start", node=node_name, tenant_id=state.tenant_id)

    try:
        report = state.report_text_en
        if not report:
            return {
                "node_results": [_record(node_name, NodeStatus.SKIPPED, start)],
            }

        phone_number_id = os.environ.get("WHATSAPP_PHONE_ID", "")
        token = os.environ.get("WHATSAPP_TOKEN", "")
        # In production, load tenant's whatsapp_number from DB
        to_number = os.environ.get("TEST_WHATSAPP_NUMBER", "254700000000")

        if not phone_number_id or not token:
            log.warning(
                "whatsapp_credentials_missing",
                node=node_name,
                tenant_id=state.tenant_id,
            )
            return {
                "node_results": [
                    _record(
                        node_name,
                        NodeStatus.SKIPPED,
                        start,
                        error="WhatsApp credentials not configured",
                    )
                ],
            }

        message_id = _dispatch_whatsapp(to_number, report, phone_number_id, token)

        log.info(
            "node_success",
            node=node_name,
            tenant_id=state.tenant_id,
            message_id=message_id,
            to=to_number,
        )

        return {
            "whatsapp_sent": True,
            "whatsapp_message_id": message_id,
            "node_results": [_record(node_name, NodeStatus.SUCCESS, start)],
        }

    except Exception as exc:
        msg = f"{node_name} failed: {exc}"
        log.exception("node_error", node=node_name, tenant_id=state.tenant_id)
        return {
            "errors": [msg],
            "whatsapp_sent": False,
            "node_results": [
                _record(node_name, NodeStatus.FAILED, start, error=str(exc))
            ],
        }
