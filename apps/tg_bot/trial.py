import asyncio
from datetime import datetime, timedelta
from apps.tg_bot.db import get_client
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

async def start_trial(tenant_id: str):
    """P7-T3: Initializes a 14-day trial for a new tenant."""
    db = get_client()
    now = datetime.utcnow()
    ends = now + timedelta(days=14)
    
    log.info("starting_trial", tenant_id=tenant_id)
    
    def _db_update():
        return db.table("tenants").update({
            "plan": "free",
            "trial_started_at": now.isoformat(),
            "trial_ends_at": ends.isoformat(),
            "subscription_active": True # Active during trial
        }).eq("id", tenant_id).execute()
        
    await asyncio.get_event_loop().run_in_executor(None, _db_update)

async def get_trial_status(tenant_id: str) -> dict:
    """P7-T3: Returns trial status and plan details."""
    db = get_client()
    
    def _db_get():
        return db.table("tenants").select("*").eq("id", tenant_id).maybe_single().execute()
        
    resp = await asyncio.get_event_loop().run_in_executor(None, _db_get)
    if not resp or not resp.data:
        return {"is_active": False, "plan": "free", "is_expired": True, "days_remaining": 0}
        
    tenant = resp.data
    plan = tenant.get("plan", "free")
    sub_active = tenant.get("subscription_active", False)
    ends_at_str = tenant.get("trial_ends_at")
    
    if not ends_at_str:
        return {"is_active": sub_active, "plan": plan, "is_expired": True, "days_remaining": 0}
        
    ends_at = datetime.fromisoformat(ends_at_str.replace("Z", "+00:00"))
    now = datetime.utcnow().replace(tzinfo=ends_at.tzinfo)
    
    days_left = (ends_at - now).days
    
    return {
        "plan": plan,
        "is_active": sub_active,
        "is_expired": days_left < 0,
        "days_remaining": max(0, days_left)
    }

async def is_feature_allowed(tenant_id: str, feature: str) -> bool:
    """
    P7-T3: Enforces plan gating.
    report = mtu_wenyewe + biashara
    utility_tracking = mtu_wenyewe + biashara
    daily_report/ai_insights = biashara
    """
    status = await get_trial_status(tenant_id)
    plan = status["plan"]
    
    # If subscription is dead and trial is over, block everything except compliance
    if not status["is_active"] and status["is_expired"] and plan == "free":
        return False
        
    # Gating Map
    if feature in ["report", "utility_tracking"]:
        return plan in ["mtu_wenyewe", "biashara"] or (not status["is_expired"])
        
    if feature in ["daily_report", "ai_insights"]:
        return plan == "biashara" or (not status["is_expired"])
        
    # Compliance is always free (handled in handlers.py via bypass)
    return True
