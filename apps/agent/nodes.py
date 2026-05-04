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

import time
import json
import httpx
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, List

from langchain_core.messages import SystemMessage, HumanMessage
from apps.agent.llm import get_llm
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from apps.agent.state import (
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
from apps.agent import obligations as agent_obs
import apps.tg_bot.db as db
from apps.agent.utils.logging import get_logger

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
        "due_day": agent_obs.NSSF_DUE_DAY,
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


def _call_llm_categorize(transactions: list[dict]) -> list[dict]:
    """Uses the unified LLM factory for categorization."""
    llm = get_llm()
    tx_text = json.dumps(transactions, indent=2, default=str)
    
    messages = [
        SystemMessage(content=CATEGORIZATION_SYSTEM_PROMPT),
        HumanMessage(content=f"Categorise these transactions:\n\n{tx_text}")
    ]
    
    try:
        response = llm.invoke(messages)
        raw = response.content.strip()
        # Handle cases where model might wrap in ```json ... ```
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        return json.loads(raw)
    except Exception as e:
        log.error("llm_categorization_error", error=str(e))
        raise

def categorize_transactions(state: AgentState) -> dict:
    """
    Calls unified LLM to categorise every raw transaction.
    Falls back to rule-based if LLM fails all retries.
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

        llm_results: list[dict] = []
        used_fallback = False

        # T40: Implement chunked categorization to prevent OpenRouter 402/token-limit errors.
        # 50 transactions per chunk is a safe balance of speed and token usage.
        chunk_size = 50
        for i in range(0, len(tx_dicts), chunk_size):
            chunk = tx_dicts[i : i + chunk_size]
            try:
                res = _call_llm_categorize(chunk)
                llm_results.extend(res)
            except Exception as exc:
                used_fallback = True
                log.warning(
                    "llm_categorization_chunk_failed",
                    node=node_name,
                    tenant_id=state.tenant_id,
                    chunk_index=i // chunk_size,
                    error=str(exc),
                )
                # Fallback only for this chunk
                for t in chunk:
                    # Find original tx object for rule-based
                    orig_tx = next(tx for tx in state.raw_transactions if tx.mpesa_ref == t["mpesa_ref"])
                    llm_results.append({
                        "mpesa_ref": t["mpesa_ref"],
                        **_rule_based_categorize(orig_tx)
                    })

        # Build lookup keyed by mpesa_ref
        result_map = {r["mpesa_ref"]: r for r in llm_results}

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
            "pipeline_failed": True,
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
            "pipeline_failed": True,
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

    log.info(
        "node_entry",
        node=node_name,
        tenant_id=state.tenant_id,
        recon_available=state.reconciliation is not None,
        tx_count=len(state.raw_transactions)
    )

    try:
        recon = state.reconciliation
        today = datetime.utcnow()

        # ── VAT estimate (P3-T3) ──────────────────────────────────────────
        tenant = db.get_tenant(state.tenant_id) if isinstance(state.tenant_id, int) else None
        # Note: tenant_id in state might be the UUID string or Telegram ID. 
        # The db.get_tenant takes Telegram ID.
        # Let's assume for now we can determine business status from state or context.
        # Actually, let's use a simpler check if we don't have the full tenant object in state.
        
        # P3-T3: 16% of total inflows (C2B)
        total_inflows = sum(t.amount for t in state.raw_transactions if t.transaction_type == TransactionType.C2B)
        net_vat = round(total_inflows * 0.16, 2)

        period_str = (state.report_period_start or today).strftime("%Y-%m")
        vat_return = VATReturn(
            period=period_str,
            gross_sales=total_inflows,
            taxable_sales=total_inflows,
            output_vat=net_vat,
            input_vat=0.0,
            net_vat_payable=net_vat,
            vat_refund=0.0,
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
            else:
                amount = 0.0 # P3-T2: No hardcoded or estimated values.

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
            "node_exit",
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
        import traceback
        st = traceback.format_exc()
        log.error(
            "node_failure",
            node=node_name,
            tenant_id=state.tenant_id,
            error=str(exc),
            stack_trace=st
        )
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
You are a Kenyan business financial advisor for small business owners.
Write a WhatsApp business report — concise, warm, actionable.
Use ONLY the structured data provided. Do NOT invent figures or add categories not present in the data.
All categorisation is AI-estimated — label it clearly as *estimated* in your narrative.
Use M-Pesa-style formatting with bold via *asterisks*.
Keep under 400 words.
Use Kenyan shilling (KES) notation.
STRICT: Use the provided KES values exactly as written. Do not round, recompute, or approximate financial totals.
End with ONE clear next action.
Write in {language}."""


def _call_llm_report(prompt: str, language: str) -> str:
    """Uses the unified LLM factory for report generation."""
    llm = get_llm()
    messages = [
        SystemMessage(content=REPORT_SYSTEM_PROMPT.format(language=language)),
        HumanMessage(content=prompt)
    ]
    try:
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        log.error("llm_report_error", error=str(e), language=language)
        raise

def _build_report_prompt(state: AgentState) -> str:
    r = state.reconciliation
    v = state.vat_return
    obs = state.upcoming_obligations

    next_ob = obs[0] if obs else None
    next_ob_str = (
        f"({next_ob.obligation_type.value} due in {next_ob.days_until_due} days, "
        f"est. KES {next_ob.estimated_amount:,.2f})"
        if next_ob else "No immediate obligations"
    )

    # REQUIRED FIX 1: Ensure only pre-aggregated summary is sent. No raw rows.
    # We also filter out zero categories to prevent trust-damaging hallucinations (e.g. Salary: 0%).
    breakdown = r.category_breakdown if r else {}
    active_categories = {k: v for k, v in breakdown.items() if v > 0}
    breakdown_str = "\n".join([f"  - {cat}: KES {amt:,.2f}" for cat, amt in active_categories.items()])
    
    # Sanitize errors to prevent token bloat
    clean_errors = [e[:200] + "..." if len(e) > 200 else e for e in state.errors]
    error_summary = clean_errors[:3] if clean_errors else "None"

    caveat = "Note: Transaction categorisation is AI-estimated based on payment patterns. Review flagged transactions for accuracy."

    return f"""
Business report summary (STRICT SCOPE):
- Period: {state.report_period_start} to {state.report_period_end}
- Financials:
  - Total income: KES {(r.total_income if r else 0):,.2f}
  - Total expenses: KES {(r.total_expenses if r else 0):,.2f}
  - Net profit: KES {(r.net_profit if r else 0):,.2f}
- Estimated Categorization Breakdown:
{breakdown_str}
- Metadata:
  - Total Transactions: {r.transaction_count if r else 0}
  - Flagged for review: {r.flagged_count if r else 0}
  - Top customers: {r.top_customers[:3] if r else []}
- Compliance:
  - VAT payable this month: KES {(v.net_vat_payable if v else 0):,.2f}
  - Most urgent KRA obligation: {next_ob_str}
- System Warnings: {error_summary}

Required Caveat: {caveat}

Write the WhatsApp report now. Provide a warm narrative and one clear next action.
Label all categorisation as ESTIMATED. Use the exact financial totals above.
""".strip()


def generate_report(state: AgentState) -> dict:
    """
    Calls LLM (Claude or DeepSeek) to write bilingual (English + Swahili) WhatsApp reports.
    Falls back to a template-based report if LLM fails.
    
    GUARANTEE: This node must ALWAYS return a valid dict with 'report_text_en' 
    to prevent downstream crashes in send_whatsapp.
    """
    node_name = "generate_report"
    start = time.perf_counter()

    log.info(
        "node_entry",
        node=node_name,
        tenant_id=state.tenant_id,
        vat_available=state.vat_return is not None,
        obs_count=len(state.upcoming_obligations)
    )

    # 1. Outer Guard: Initialize critical return keys
    report_en: str = ""
    report_sw: str = ""
    ai_degraded: bool = False

    # T36: Gate — refuse to generate a report on a failed pipeline.
    if state.pipeline_failed:
        msg = f"{node_name} skipped: pipeline_failed is True (upstream node failure)"
        log.warning("node_skipped_pipeline_failed", node=node_name, tenant_id=state.tenant_id, errors=state.errors)
        return {
            "errors": [msg],
            "node_results": [_record(node_name, NodeStatus.FAILED, start, error=msg)],
        }

    try:
        # 2. Extract Data
        r = state.reconciliation
        v = state.vat_return
        obs = state.upcoming_obligations

        # 3. Inner LLM Try-Block (already hardened in T9AS)
        try:
            prompt = _build_report_prompt(state)
            report_en = _call_llm_report(prompt, "English")
            report_sw = _call_llm_report(prompt, "Swahili")
        except Exception as llm_exc:
            log.warning(
                "llm_report_failed_using_template",
                node=node_name,
                tenant_id=state.tenant_id,
                error=str(llm_exc),
            )
            # T36: Mark AI specifically as degraded while preserving financial success
            ai_degraded = True
            
            # FAANG-Grade Deterministic Fallback (P19-T9AS/T9AT Enforcement)
            vat_line = f"📋 *Estimated VAT:* KES {(v.net_vat_payable if v else 0):,.2f}\n" if v and v.net_vat_payable > 0 else ""
            next_ob = obs[0] if obs else None
            ob_line = f"⏰ *Next Deadline:* {next_ob.obligation_type.value} ({next_ob.due_date.strftime('%d %b')}) — {next_ob.days_until_due} days left\n" if next_ob else ""
            
            # Capture a user-friendly failure reason
            reason = "connection issue" if "timeout" in str(llm_exc).lower() else "service busy"
            fallback_header = f"📊 *Mazao AI Business Summary*\n_AI insights unavailable ({reason}); showing computed metrics_\n\n"
            metrics_body = (
                f"💰 *Total Income:* KES {(r.total_income if r else 0):,.2f}\n"
                f"💸 *Total Expenses:* KES {(r.total_expenses if r else 0):,.2f}\n"
                f"📈 *Net Profit:* KES {(r.net_profit if r else 0):,.2f}\n"
                f"{vat_line}{ob_line}"
                f"\n⚠️ *Alert:* {r.flagged_count if r else 0} transactions need review.\n\n"
                f"Next Action: Use /help for filing guides while we restore AI insights."
            )
            report_en = fallback_header + metrics_body
            report_sw = report_en

        # 4. Final Validation: Never return empty
        if not report_en:
            report_en = "📊 *Mazao AI Summary*\n\nYour report is being processed. Please check back in a few minutes or use /status for a quick overview."

        log.info(
            "node_exit",
            node=node_name,
            tenant_id=state.tenant_id,
            en_length=len(report_en),
            sw_length=len(report_sw),
            ai_degraded=ai_degraded,
        )

        return {
            "report_text_en": report_en,
            "report_text_sw": report_sw or report_en,
            "ai_degraded": ai_degraded,
            "node_results": [_record(node_name, NodeStatus.SUCCESS, start)],
        }

    except Exception as exc:
        # 5. Outermost Fail-Safe Return Contract
        msg = f"{node_name} critical failure: {exc}"
        import traceback
        st = traceback.format_exc()
        log.error("node_critical_failure", node=node_name, tenant_id=state.tenant_id, error=str(exc), stack_trace=st)
        
        emergency_report = "📊 *Mazao AI Business Summary*\n\nI encountered a technical issue generating your full report. Please use /status to see your latest income and expenses directly from the dashboard."
        
        return {
            "report_text_en": emergency_report,
            "report_text_sw": emergency_report,
            "errors": [msg],
            "node_results": [_record(node_name, NodeStatus.FAILED, start, error=str(exc))],
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

        # --- PHASE 3: STUBBED AWAITING PAYMENT ---
        log.warning(
            "whatsapp_delivery_stubbed",
            node=node_name,
            tenant_id=state.tenant_id,
            status="AWAITING_PAYMENT"
        )
        
        return {
            "whatsapp_sent": False,
            "whatsapp_message_id": None,
            "node_results": [_record(node_name, NodeStatus.SKIPPED, start, error="WhatsApp disabled: AWAITING_PAYMENT")],
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


# ── Helpers ─────────────────────────────────────────────────────────────

def _rule_based_categorize(tx: RawTransaction) -> dict:
    """Deterministic fallback categorization for M-Pesa transactions."""
    name = tx.name.upper()
    bill_ref = (tx.bill_ref or "").upper()
    amount = tx.amount
    tx_type = tx.transaction_type
    
    # Defaults
    category = TransactionCategory.UNKNOWN
    confidence = 0.5
    needs_review = amount > 50000
    reasoning = "Rule-based fallback"

    # Rule 1: TAX
    tax_keywords = ["KRA", "ITAX", "NSSF", "NHIF", "PAYE", "WHT", "VAT"]
    if any(k in name for k in tax_keywords) or any(k in bill_ref for k in tax_keywords):
        category = TransactionCategory.TAX
        confidence = 0.9
        reasoning = "Matched statutory keyword (KRA/iTax/NSSF/NHIF)"

    # Rule 2: SALES (Income)
    elif tx_type == TransactionType.C2B:
        category = TransactionCategory.SALES
        confidence = 0.8
        reasoning = "C2B income (Customer to Business)"

    # Rule 3: SALARY
    elif "SALARY" in name or "WAGES" in name:
        category = TransactionCategory.SALARY
        confidence = 0.9
        reasoning = "Matched keyword 'Salary/Wages'"

    # Rule 4: SUPPLIER
    elif tx_type == TransactionType.B2C:
        category = TransactionCategory.SUPPLIER
        confidence = 0.6
        reasoning = "B2C payout (likely Supplier)"

    return {
        "category": category,
        "confidence": confidence,
        "needs_review": needs_review,
        "reasoning": reasoning
    }
