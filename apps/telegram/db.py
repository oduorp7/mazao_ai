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
from datetime import datetime
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
    resp = (
        get_client()
        .table("tenants")
        .select("*")
        .eq("telegram_id", telegram_id)
        .maybe_single()
        .execute()
    )
    return resp.data


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
    resp = (
        get_client()
        .table("conversations")
        .select("*")
        .eq("telegram_id", telegram_id)
        .maybe_single()
        .execute()
    )
    return resp.data


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
