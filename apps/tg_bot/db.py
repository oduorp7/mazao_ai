"""
db.py — Tenant data layer

Thin wrapper around Supabase. Every function is synchronous and
returns plain dicts or None. No ORM, no magic.

Tables expected (run schema.sql to create):
  tenants       — one row per business/user
  reports       — one row per generated report
  conversations — last_command per user for multi-step flows
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from supabase import create_client, Client

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client

# ── Tenant helpers ────────────────────────────────────────────────────────────

def get_tenant(telegram_id: int) -> Optional[dict]:
    """Return tenant row or None if not registered."""
    try:
        resp = (
            get_client()
            .table("tenants")
            .select("*")
            .eq("telegram_id", telegram_id)
            .maybe_single()
            .execute()
        )
        return resp.data if resp else None
    except Exception:
        return None


def create_tenant(
    telegram_id: int,
    telegram_username: str,
    full_name: str,
) -> dict:
    """Insert a new tenant in PENDING state. Returns the created row."""
    resp = (
        get_client()
        .table("tenants")
        .insert(
            {
                "telegram_id": telegram_id,
                "telegram_username": telegram_username,
                "full_name": full_name,
                "status": "pending",        # pending → active after M-Pesa setup
                "plan": "trial",            # trial → hustler → biashara
                "trial_days_left": 14,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )
    return resp.data[0]


def update_tenant(telegram_id: int, updates: dict) -> dict:
    """Patch any fields on a tenant row. Returns updated row."""
    resp = (
        get_client()
        .table("tenants")
        .update({**updates, "updated_at": datetime.utcnow().isoformat()})
        .eq("telegram_id", telegram_id)
        .execute()
    )
    return resp.data[0]


def get_all_active_tenants() -> list[dict]:
    """Return all tenants the scheduler should process today."""
    resp = (
        get_client()
        .table("tenants")
        .select("*")
        .in_("status", ["active", "trial"])
        .execute()
    )
    return resp.data or []


# ── Conversation state (multi-step flows) ─────────────────────────────────────

def get_conv_state(telegram_id: int) -> Optional[dict]:
    try:
        resp = (
            get_client()
            .table("conversations")
            .select("*")
            .eq("telegram_id", telegram_id)
            .maybe_single()
            .execute()
        )
        return resp.data if resp else None
    except Exception:
        return None


def set_conv_state(telegram_id: int, state: str, data: dict | None = None) -> None:
    """Upsert the current conversation state for a user."""
    get_client().table("conversations").upsert(
        {
            "telegram_id": telegram_id,
            "state": state,
            "data": data or {},
            "updated_at": datetime.utcnow().isoformat(),
        }
    ).execute()


def clear_conv_state(telegram_id: int) -> None:
    set_conv_state(telegram_id, "idle")


# ── Reports ───────────────────────────────────────────────────────────────────

def save_report(tenant_id: str, period: str, summary: dict) -> None:
    get_client().table("reports").insert(
        {
            "tenant_id": tenant_id,
            "period": period,
            "summary": summary,
            "created_at": datetime.utcnow().isoformat(),
        }
    ).execute()


def get_latest_report(tenant_id: str) -> Optional[dict]:
    resp = (
        get_client()
        .table("reports")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return resp.data


# ── Statements (P3-T4) ────────────────────────────────────────────────────────

def save_statement(
    tenant_id: str,
    period: str,
    total_inflows: float,
    total_outflows: float,
    net: float,
    vat_estimate: float,
) -> dict:
    """Store a summary of a parsed M-Pesa statement."""
    resp = (
        get_client()
        .table("statements")
        .insert(
            {
                "tenant_id": tenant_id,
                "period": period,
                "total_inflows": total_inflows,
                "total_outflows": total_outflows,
                "net": net,
                "vat_estimate": vat_estimate,
                "parsed_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )
    return resp.data[0]


def get_latest_statement(tenant_id: str) -> Optional[dict]:
    """Retrieve the most recent parsed statement summary."""
    resp = (
        get_client()
        .table("statements")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("parsed_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return resp.data


def update_tenant_sha(telegram_id: int, sha_number: str) -> dict:
    """Update the SHA number for an individual tenant."""
    return update_tenant(telegram_id, {"sha_number": sha_number})


def get_tenants_by_type(user_type: str) -> List[dict]:
    """Return all tenants of a specific type (business/individual)."""
    resp = (
        get_client()
        .table("tenants")
        .select("*")
        .eq("user_type", user_type)
        .execute()
    )
    return resp.data or []


def get_individual_obligations(telegram_id: int) -> List[dict]:
    """
    Returns a list of calculated obligations for an individual.
    This logic inverts the 'business' perspective to personal KRA/SHA deadlines.
    """
    tenant = get_tenant(telegram_id)
    if not tenant or tenant.get("user_type") != "individual":
        return []

    status = tenant.get("employment_status", "unemployed")
    today = datetime.utcnow()
    
    # Income Tax Return: June 30
    return_year = today.year
    if today.month > 6:
        return_year += 1
    return_due = datetime(return_year, 6, 30)
    
    obligations = [
        {
            "name": "Annual Income Tax Return",
            "due_date": return_due,
            "description": "Declaration of income for the previous year.",
            "penalty": "KES 2,000 or 5% of tax due"
        }
    ]

    if status == "unemployed":
        obligations[0]["name"] = "Nil Return"
        obligations[0]["description"] = "Mandatory zero-income declaration to avoid penalties."

    next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)

    if status == "employed":
        # SHA: 9th of next month
        sha_due = next_month.replace(day=9)
        obligations.append({
            "name": "SHA Contribution",
            "due_date": sha_due,
            "description": "2.75% of gross salary. Remind employer to verify.",
            "penalty": "Interest on late payment"
        })

    if status == "self_employed":
        # NSSF: 15th of next month
        nssf_due = next_month.replace(day=15)
        obligations.append({
            "name": "NSSF Tier 1 + 2",
            "due_date": nssf_due,
            "description": "Tier 1: KES 420. Tier 2: 6% of pensionable pay.",
            "penalty": "Compounded interest"
        })

    return obligations
