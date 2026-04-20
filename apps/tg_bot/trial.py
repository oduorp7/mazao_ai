"""
trial.py — Trial & Plan Gating Logic (Phase 7).

Manages trial initialization, expiry calculation, and feature access
control based on user plans.

Plans:
  - 'free': Expired trial, compliance alerts only.
  - 'mtu_wenyewe': Individual business tracking (reports, utility).
  - 'biashara': Full suite (daily reports, AI insights).
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from apps.tg_bot.db import get_client
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)


async def start_trial(tenant_id: str):
    """
    Initialize 14-day trial for a new tenant.
    Sets trial_started_at, trial_ends_at, and plan='free'.
    """
    db = get_client()
    now = datetime.utcnow()
    ends = now + timedelta(days=14)

    def _sync_start():
        return db.table("tenants").update({
            "trial_started_at": now.isoformat(),
            "trial_ends_at": ends.isoformat(),
            "plan": "free",
            "subscription_active": False # Trials count as inactive for sub status
        }).eq("id", tenant_id).execute()

    await asyncio.get_event_loop().run_in_executor(None, _sync_start)
    log.info("trial_started", tenant_id=tenant_id, ends=ends.isoformat())


async def get_trial_status(tenant_id: str) -> dict:
    """
    Return trial metrics: days_remaining, is_expired, is_active, plan.
    """
    db = get_client()

    def _sync_get():
        # Fallback to trial_days_left and default subscription_active if missing from schema
        return db.table("tenants").select("plan, trial_days_left").eq("id", tenant_id).maybe_single().execute()

    resp = await asyncio.get_event_loop().run_in_executor(None, _sync_get)
    if not resp or not resp.data:
        return {"active": False, "days_remaining": 0, "is_expired": True, "plan": "free"}

    data = resp.data
    plan = data.get("plan", "free")
    days_left = data.get("trial_days_left", 0)
    # Default to False if column is missing from DB
    sub_active = data.get("subscription_active", False)

    if sub_active:
        return {"active": True, "days_remaining": 999, "is_expired": False, "plan": plan}

    is_expired = days_left <= 0

    return {
        "active": not is_expired,
        "days_remaining": max(0, days_left),
        "is_expired": is_expired,
        "plan": plan
    }


async def is_feature_allowed(tenant_id: str, feature: str) -> bool:
    """
    Central gatekeeper for Mazao AI features.

    Feature Matrix:
    - 'report': active_trial | mtu_wenyewe | biashara
    - 'utility_tracking': active_trial | mtu_wenyewe | biashara
    - 'daily_report': biashara only
    - 'ai_insights': biashara only
    - 'compliance_alerts': always True (even for expired free)
    """
    if feature == "compliance_alerts":
        return True

    status = await get_trial_status(tenant_id)
    plan = status["plan"]
    trial_active = status["active"]

    if plan == "biashara":
        return True

    if plan == "mtu_wenyewe":
        # Block biashara-only features
        if feature in ("daily_report", "ai_insights"):
            return False
        return True

    # Free plan relies entirely on active trial
    if trial_active:
        # Trials get 'mtu_wenyewe' level access
        if feature in ("daily_report", "ai_insights"):
            return False
        return True

    return False
