"""
trial.py — Trial & Plan Gating Logic (Phase 7).

Manages trial initialization, expiry calculation, and feature access
control based on user plans.

Plans:
  - 'free': Manual tracking only.
  - 'core': Unlimited utility tracking + proactive alerts.
  - 'pro': Full AI insights + AI tips.
  - 'trial': Temporary PRO access for 7 days.
"""

TIER_TRIAL = "trial"
TIER_FREE = "free"
TIER_CORE = "core"
TIER_PRO = "pro"

TIER_MATRIX = {
    TIER_TRIAL: ["manual_tracking", "status_dashboards", "proactive_alerts", "projections", "ai_tips", "insights"],
    TIER_FREE:  ["manual_tracking", "status_dashboards"],
    TIER_CORE:  ["manual_tracking", "status_dashboards", "proactive_alerts", "projections"],
    TIER_PRO:   ["manual_tracking", "status_dashboards", "proactive_alerts", "projections", "ai_tips", "insights"],
}

import asyncio
import os
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
    ends = now + timedelta(days=7)

    def _sync_start():
        try:
            return db.table("tenants").update({
                "trial_started_at": now.isoformat(),
                "trial_ends_at": ends.isoformat(),
                "plan": "free",
                "subscription_active": False # Trials count as inactive for sub status
            }).eq("id", tenant_id).execute()
        except Exception as e:
            log.warning("db_update_trial_failed", error=str(e))
            # Fallback if primary trial columns are missing: update existing 'plan' and 'trial_days_left' if possible
            try:
                return db.table("tenants").update({
                    "plan": "trial",
                    "trial_days_left": 7
                }).eq("id", tenant_id).execute()
            except Exception as e2:
                log.error("fallback_trial_start_failed", error=str(e2))
                raise e2

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


def _get_superadmin_ids() -> list:
    """Build superadmin list from ADMIN_TELEGRAM_ID env var (canonical source)."""
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    return [str(admin_id)] if admin_id else []

SUPERADMIN_TELEGRAM_IDS = _get_superadmin_ids()

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
    # Superadmin bypass: resolve telegram_id and check against env-sourced list
    if SUPERADMIN_TELEGRAM_IDS:
        try:
            db = get_client()
            def _get_tid():
                resp = db.table("tenants").select("telegram_id").eq("id", tenant_id).maybe_single().execute()
                return str(resp.data["telegram_id"]) if resp and resp.data else None

            tid = await asyncio.get_event_loop().run_in_executor(None, _get_tid)
            if tid and tid in SUPERADMIN_TELEGRAM_IDS:
                log.info("superadmin_gate_bypass", telegram_id=tid, feature=feature)
                return True
        except Exception:
            pass  # Fail closed: normal gating continues


    if feature == "compliance_alerts":
        return True

    status = await get_trial_status(tenant_id)
    plan = status["plan"]
    trial_active = status["active"]

    # Trial plan uses TIER_TRIAL permissions if active
    if trial_active and plan == TIER_TRIAL:
        return feature in TIER_MATRIX[TIER_TRIAL]

    # Paid tiers (Core/Pro) require active subscription
    sub_active = status.get("active", False) # get_trial_status returns active=True if subscription_active is True
    if not sub_active:
        plan = TIER_FREE

    # Otherwise use plan-specific matrix (treat legacy as free)
    allowed_features = TIER_MATRIX.get(plan, TIER_MATRIX[TIER_FREE])
    return feature in allowed_features
