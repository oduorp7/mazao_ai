"""
scheduler.py — Scheduled jobs for Mazao AI.

Jobs:
  1. daily_reports    — 07:00 EAT every day → run pipeline for all active tenants
  2. deadline_alerts  — 08:00 EAT every day → send KRA deadline warnings
  3. trial_warnings   — 09:00 EAT every day → warn users whose trial is ending

Uses APScheduler with AsyncIOScheduler so it runs inside the same
event loop as the Telegram bot — no separate process needed.
"""

from __future__ import annotations

import os
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.constants import ParseMode
from telegram.ext import ContextTypes # P10-T5

import apps.tg_bot.db as db
import apps.tg_bot.messages as M
from apps.agent import estimator
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

# Kenya is UTC+3
KENYA_TZ = "Africa/Nairobi"


# ── Job 0: Admin Daily Digest (P10-T5) ────────────────────────────────────────

async def job_admin_daily_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    """P10-T5: Sends a daily stats digest to Chief Engineer."""
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if not admin_id:
        log.warn("admin_daily_digest_skipped", reason="ADMIN_TELEGRAM_ID_not_set")
        return

    client = db.get_client()
    now = datetime.utcnow()
    last_24h = (now - timedelta(days=1)).isoformat()
    three_days_out = (now + timedelta(days=3)).isoformat()

    # 1. New Tenants
    new_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("tenants").select("id", count="exact").gte("created_at", last_24h).execute()
    )
    new_tenants = new_resp.count or 0

    # 2. Payments (last 24h)
    rev_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("payment_requests").select("amount").eq("status", "confirmed").gte("confirmed_at", last_24h).execute()
    )
    rev_data = rev_resp.data or []
    revenue = sum(float(r["amount"]) for r in rev_data)
    payments_count = len(rev_data)

    # 3. Active Trials
    trials_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("tenants").select("id", count="exact").eq("plan", "trial").execute()
    )
    active_trials = trials_resp.count or 0

    # 4. Expiring Trials (3 days)
    expiring_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("tenants").select("id", count="exact").eq("plan", "trial").lte("trial_ends_at", three_days_out).execute()
    )
    expiring_trials = expiring_resp.count or 0

    # 5. Feedback (last 24h)
    fb_resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.table("feedback").select("id", count="exact").gte("created_at", last_24h).execute()
    )
    feedback_count = fb_resp.count or 0

    digest = M.ADMIN_DAILY_DIGEST.format(
        new_tenants=new_tenants,
        revenue=revenue,
        payments_count=payments_count,
        active_trials=active_trials,
        expiring_trials=expiring_trials,
        feedback_count=feedback_count
    )

    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=digest,
            parse_mode=ParseMode.MARKDOWN
        )
        log.info("admin_daily_digest_sent", telegram_id=admin_id)
    except Exception as e:
        log.error("admin_daily_digest_failed", error=str(e))


# ── Job 1: Daily reports ──────────────────────────────────────────────────────

async def job_daily_reports(context: ContextTypes.DEFAULT_TYPE) -> None:
    tenants = await asyncio.get_event_loop().run_in_executor(None, db.get_all_active_tenants)
    log.info("daily_reports_start", tenant_count=len(tenants))
    
    bot = context.bot

    for tenant in tenants:
        tid = tenant["telegram_id"]
        try:
            await _process_tenant(bot, tenant)
        except Exception as exc:
            log.exception(
                "daily_report_failed",
                telegram_id=tid,
                error=str(exc),
            )
            # Don't let one failure block the rest

    log.info("daily_reports_complete", tenant_count=len(tenants))


async def _process_tenant(bot: Bot, tenant: dict) -> None:
    """Run pipeline for one tenant and send result (P2-T4)."""
    tid = tenant["telegram_id"]
    lang = tenant.get("preferred_language", "en")

    log.info("processing_tenant", telegram_id=tid, tenant_id=tenant["id"], lang=lang)

    # Fetch real transactions (none in Phase 1 as Daraja is Phase 3)
    real_txs = [] 

    from apps.agent.pipeline import run_pipeline
    from apps.agent.state import RawTransaction, TransactionType

    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: run_pipeline(
            tenant_id=str(tenant["id"]),
            raw_transactions=real_txs,
            triggered_by="scheduled",
        ),
    )

    # Language selection logic (P2-T4)
    report_text = result.report_text_sw if lang == "sw" else result.report_text_en

    if report_text:
        await bot.send_message(
            chat_id=tid,
            text=report_text,
            parse_mode=ParseMode.MARKDOWN,
        )

        if result.reconciliation:
            r = result.reconciliation
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.save_report(
                    tenant_id=str(tenant["id"]),
                    period=datetime.utcnow().strftime("%Y-%m"),
                    summary={
                        "income": r.total_income,
                        "expenses": r.total_expenses,
                        "profit": r.net_profit,
                        "flagged": r.flagged_count,
                    },
                )
            )

        log.info("report_sent", telegram_id=tid, lang=lang)
    else:
        log.warning("empty_report", telegram_id=tid, errors=result.errors)


# ── Job 2: KRA deadline alerts ────────────────────────────────────────────────

KRA_OBLIGATIONS = [
    {"type": "VAT",      "due_day": 20},
    {"type": "PAYE",     "due_day": 9},
    {"type": "NSSF",     "due_day": 15},
    {"type": "NHIF/SHA", "due_day": 9},
]

PENALTY_RATE = 0.05   # 5% per month


async def job_deadline_alerts(bot: Bot) -> None:
    tenants = await asyncio.get_event_loop().run_in_executor(None, db.get_all_active_tenants)
    today = datetime.utcnow().date()

    log.info("deadline_alerts_start", tenant_count=len(tenants))

    for tenant in tenants:
        tid = tenant["telegram_id"]
        user_type = tenant.get("user_type", "business")

        if user_type == "individual":
            # Individual Obligations Engine (P2-T1)
            obligations = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_individual_obligations(tid))

            for ob in obligations:
                due_date = ob["due_date"].date()
                days_until = (due_date - today).days
                name = ob["name"]
                
                alert_msg = None
                if "Return" in name and days_until in (30, 7, 2):
                    alert_msg = M.INDIVIDUAL_ANNUAL_RETURN_ALERT if "Annual" in name else M.INDIVIDUAL_NIL_RETURN_ALERT
                elif "SHA" in name and days_until == 2:
                    alert_msg = M.INDIVIDUAL_SHA_ALERT
                elif "NSSF" in name and days_until == 2:
                    alert_msg = M.INDIVIDUAL_NSSF_ALERT

                if alert_msg:
                    try:
                        await bot.send_message(
                            chat_id=tid,
                            text=alert_msg.format(
                                due_date=due_date.strftime("%d %b %Y"),
                                days_left=f"{days_until} days",
                                penalty=ob.get("penalty", "Standard iTax penalties apply"),
                            ),
                            parse_mode=ParseMode.MARKDOWN,
                        )
                        log.info("individual_alert_sent", telegram_id=tid, obligation=name)
                    except Exception as exc:
                        log.exception("individual_alert_failed", telegram_id=tid, error=str(exc))
            continue

        # Business Obligations
        report = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_latest_report(str(tenant["id"])))
        income = report["summary"].get("income", 0) if report else 0
        expenses = report["summary"].get("expenses", 0) if report else 0

        # VAT estimate
        net_vat = max((income - expenses) * 0.16, 0)
        # PAYE rough estimate
        salary = expenses * 0.3
        paye_est = salary * 0.30

        ob_amounts = {
            "VAT": net_vat,
            "PAYE": paye_est,
            "NSSF": salary * 0.06,
            "NHIF/SHA": salary * 0.0275,
        }

        first_of_next_month = (
            datetime.utcnow().replace(day=1) + timedelta(days=32)
        ).replace(day=1).date()

        for ob in KRA_OBLIGATIONS:
            due_date = first_of_next_month.replace(day=ob["due_day"])
            days_until = (due_date - today).days
            amount = ob_amounts.get(ob["type"], 0)
            penalty = round(amount * PENALTY_RATE, 0)

            try:
                if days_until == 7:
                    await bot.send_message(
                        chat_id=tid,
                        text=M.DEADLINE_7_DAYS.format(
                            obligation_type=ob["type"],
                            due_date=due_date.strftime("%d %b %Y"),
                            amount=amount,
                            penalty=penalty,
                        ),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                elif days_until == 2:
                    await bot.send_message(
                        chat_id=tid,
                        text=M.DEADLINE_2_DAYS.format(
                            obligation_type=ob["type"],
                            due_date=due_date.strftime("%d %b %Y"),
                            amount=amount,
                            penalty=penalty,
                        ),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                elif days_until < 0:
                    await bot.send_message(
                        chat_id=tid,
                        text=M.DEADLINE_OVERDUE.format(
                            obligation_type=ob["type"],
                            penalty=penalty,
                        ),
                        parse_mode=ParseMode.MARKDOWN,
                    )
            except Exception as exc:
                log.exception("alert_failed", telegram_id=tid, obligation=ob["type"], error=str(exc))

    log.info("deadline_alerts_complete")


# ── Job 3: Trial expiry alerts (P7-T7) ────────────────────────────────────────

async def job_trial_alerts(bot: Bot) -> None:
    """Check for trial expiry and send warnings at T-3 and T-0."""
    tenants = await asyncio.get_event_loop().run_in_executor(None, db.get_all_active_tenants)
    now = datetime.utcnow()
    
    log.info("trial_alerts_start", count=len(tenants))

    for tenant in tenants:
        if tenant.get("plan") != "free" or tenant.get("subscription_active"):
            continue # Already paid or not on trial

        ends_str = tenant.get("trial_ends_at")
        if not ends_str:
            continue
            
        ends = datetime.fromisoformat(ends_str.replace("Z", "+00:00"))
        now_tz = now.replace(tzinfo=ends.tzinfo)
        
        delta = (ends - now_tz).days
        tid = tenant["telegram_id"]
        
        # P15-T1: Superadmin skip alerts
        if os.getenv("ADMIN_TELEGRAM_ID") and str(tid) == str(os.getenv("ADMIN_TELEGRAM_ID")):
            continue

        try:
            if delta == 1:
                await bot.send_message(
                    chat_id=tid,
                    text=M.TRIAL_EXPIRY_WARNING.format(days_remaining=1),
                    parse_mode=ParseMode.MARKDOWN
                )
            elif delta <= 0:
                await bot.send_message(
                    chat_id=tid,
                    text=M.TRIAL_EXPIRED,
                    parse_mode=ParseMode.MARKDOWN
                )
                # Mark as expired and downgrade to Free plan
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: db.update_tenant(tid, {"status": "lapsed", "plan": "free"})
                )
        except Exception as exc:
            log.exception("trial_alert_failed", telegram_id=tid, error=str(exc))

# ── Job 4: Electricity token alerts (P4-T4) ──────────────────────────────────

# ── Job 4: Electricity token alerts (P19) ────────────────────────────────────

async def job_token_depletion_check(bot: Bot) -> None:
    """P19-T3: Proactive token depletion alerts."""
    tenants = await asyncio.get_event_loop().run_in_executor(None, db.get_all_active_tenants)
    log.info("token_depletion_check_start", count=len(tenants))

    for tenant in tenants:
        tid = tenant["telegram_id"]
        try:
            # 1. Fetch latest token entry
            resp = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("token_entries")
                .select("*")
                .eq("tenant_id", str(tenant["id"]))
                .order("purchase_date", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
            )
            
            if not resp or not resp.data:
                continue
                
            entry = resp.data
            
            # 2. Calculate Projection using history
            hist_resp = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("token_entries")
                .select("units, purchase_date")
                .eq("tenant_id", str(tenant["id"]))
                .order("purchase_date", desc=True)
                .execute()
            )
            history = hist_resp.data or []
            
            h_type = tenant.get("household_type", "standard")
            pop_rate = estimator.get_population_baseline(h_type)
            pers_rate, n_valid = estimator.calculate_weighted_personal_rate(history)
            daily_rate = estimator.blend_rates(pers_rate, pop_rate, len(history), n_valid)
            if daily_rate <= 0: daily_rate = pop_rate
            
            now = datetime.now(timezone.utc)
            l_date = datetime.fromisoformat(entry["purchase_date"].replace("Z", "+00:00"))
            if l_date.tzinfo is None: l_date = l_date.replace(tzinfo=timezone.utc)
            
            days_since = (now - l_date).days
            units_remaining = max(0, float(entry["units"]) - (daily_rate * days_since))
            days_rem = int(units_remaining / daily_rate)
            
            # 3. Check Thresholds (NORMALIZED Rule: [7, 3, 1] AND not Grid baseline)
            alert_msg = None
            update_field = None
            
            # Confidence Gating: Skip proactive alerts if confidence is 'Grid baseline'
            conf_label = estimator.get_confidence_info(len(history))["label"]
            
            if conf_label != "Grid baseline":
                if days_rem <= 1:
                    # 1-day alert (fires daily until resolved)
                    alert_msg = M.TOKEN_ALERT_1D
                elif days_rem <= 3:
                    # 3-day alert (once per cycle)
                    if not entry.get("alert_3d_sent"):
                        alert_msg = M.TOKEN_ALERT_3D
                        update_field = "alert_3d_sent"
                elif days_rem <= 7:
                    # 7-day alert (once per cycle)
                    if not entry.get("alert_7d_sent"):
                        alert_msg = M.TOKEN_ALERT_7D
                        update_field = "alert_7d_sent"

            if alert_msg:
                depletion_date = (now + timedelta(days=max(0, days_rem))).strftime("%d %b %Y")
                await bot.send_message(
                    chat_id=tid,
                    text=alert_msg.format(days=days_rem, date=depletion_date),
                    parse_mode=ParseMode.MARKDOWN
                )
                log.info("token_alert_sent", telegram_id=tid, threshold=update_field or "1d")
                
                # Mark as sent if applicable
                if update_field:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: db.get_client().table("token_entries")
                        .update({update_field: True})
                        .eq("id", entry["id"])
                        .execute()
                    )
                    
        except Exception as exc:
            log.error("token_depletion_check_failed", telegram_id=tid, error=str(exc))

    log.info("token_depletion_check_complete")


# ── Job 5: Fuliza payment reminders (P4-T4) ──────────────────────────────────

async def job_fuliza_alerts(bot: Bot) -> None:
    today = datetime.utcnow().date()
    try:
        # Get all entries due soon
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db.get_client().table("fuliza_entries")
            .select("*, tenants!inner(telegram_id, status)")
            .in_("tenants.status", ["active", "trial"])
            .execute()
        )
        
        for entry in resp.data:
            due_date = datetime.fromisoformat(entry["due_date"]).date()
            days_until = (due_date - today).days
            
            if 0 <= days_until <= 2:
                tid = entry["tenants"]["telegram_id"]
                await bot.send_message(
                    chat_id=tid,
                    text=M.FULIZA_REMINDER_ALERT.format(
                        balance=float(entry["balance"]),
                        due_date=due_date.strftime("%d %b %Y"),
                        days_until_due=days_until
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
    except Exception as exc:
        log.exception("fuliza_alerts_failed", error=str(exc))


async def job_subscription_alerts(bot: Bot) -> None:
    today = datetime.utcnow().date()
    try:
        # Get all subscriptions
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db.get_client().table("subscriptions")
            .select("*, tenants!inner(telegram_id, status)")
            .in_("tenants.status", ["active", "trial"])
            .execute()
        )
        
        for s in resp.data:
            day = s["renewal_day"]
            # Calculate days until next renewal
            if day > today.day:
                days_until = day - today.day
                renewal_date = today.replace(day=day)
            else:
                # Next month
                next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
                days_until = (next_month.replace(day=day) - today).days
                renewal_date = next_month.replace(day=day)
            
            if days_until <= 3:
                tid = s["tenants"]["telegram_id"]
                await bot.send_message(
                    chat_id=tid,
                    text=M.SUBSCRIPTION_REMINDER_ALERT.format(
                        name=s["name"],
                        amount=float(s["amount_kes"]),
                        days_until_due=days_until,
                        renewal_date=renewal_date.strftime("%d %b %Y")
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
    except Exception as exc:
        log.exception("subscription_alerts_failed", error=str(exc))


# ── Job 6: Gas depletion alerts (P17-T1E) ───────────────────────────────────

async def job_gas_alerts(bot: Bot) -> None:
    """Sends gas refill reminders at T-3 and T-1 days (P17-T1E)."""
    from apps.agent.estimator import get_gas_projection_state
    
    tenants = await asyncio.get_event_loop().run_in_executor(None, db.get_all_active_tenants)
    log.info("gas_alerts_start", tenant_count=len(tenants))

    for tenant in tenants:
        tid = tenant["telegram_id"]
        try:
            # 1. Fetch history (including alert flags for the latest entry)
            resp = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.get_client().table("gas_entries")
                .select("*")
                .eq("tenant_id", str(tenant["id"]))
                .order("purchase_date", desc=True)
                .execute()
            )
            
            if not resp.data:
                continue
            
            latest_entry = resp.data[0]
                
            # 2. Map & Project
            history = [{"units": r["amount_kg"], "purchase_date": r["purchase_date"]} for r in resp.data]
            proj = get_gas_projection_state(history, tenant.get("household_type"))
            
            # 3. Filtering Logic (NORMALIZED Rule: [7, 3, 1] AND not Grid baseline)
            # Thresholds: 7-day, 3-day and 1-day
            # High-Confidence: Skip "Grid baseline" (0-1 history entries)
            days_rem = proj["days_remaining"]
            conf_label = proj["confidence"]["label"]
            
            if conf_label != "Grid baseline":
                alert_msg = None
                update_field = None
                
                if days_rem <= 1:
                    alert_msg = M.GAS_LOW_REMINDER
                elif days_rem <= 3:
                    # Deduplication (DB-backed)
                    if not latest_entry.get("alert_3d_sent"):
                        alert_msg = M.GAS_LOW_REMINDER
                        update_field = "alert_3d_sent"
                elif days_rem <= 7:
                    # Deduplication (DB-backed)
                    if not latest_entry.get("alert_7d_sent"):
                        alert_msg = M.GAS_LOW_REMINDER
                        update_field = "alert_7d_sent"

                if alert_msg:
                    await bot.send_message(
                        chat_id=tid,
                        text=alert_msg.format(
                            days_remaining=days_rem,
                            depletion_date=proj["depletion_date"]
                        ),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    log.info("gas_alert_sent", telegram_id=tid, days_left=days_rem, threshold=update_field or "1d")
                    
                    # Mark as sent if applicable
                    if update_field:
                        await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: db.get_client().table("gas_entries")
                            .update({update_field: True})
                            .eq("id", latest_entry["id"])
                            .execute()
                        )
                
        except Exception as exc:
            log.error("gas_alert_failed", telegram_id=tid, error=str(exc))

    log.info("gas_alerts_complete")


# ── Scheduler factory ─────────────────────────────────────────────────────────

def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    """
    Create and configure the scheduler.
    Call start() on the returned object to activate.
    """
    scheduler = AsyncIOScheduler(timezone=KENYA_TZ)

    # Daily reports — 7:00 AM Kenya time
    scheduler.add_job(
        job_daily_reports,
        CronTrigger(hour=7, minute=0, timezone=KENYA_TZ),
        args=[bot],
        id="daily_reports",
        name="Daily M-Pesa reports",
        misfire_grace_time=300,       # retry up to 5 min late
        coalesce=True,                # don't double-run if delayed
    )

    # Deadline alerts — 8:00 AM Kenya time
    scheduler.add_job(
        job_deadline_alerts,
        CronTrigger(hour=8, minute=0, timezone=KENYA_TZ),
        args=[bot],
        id="deadline_alerts",
        name="KRA deadline alerts",
        misfire_grace_time=300,
        coalesce=True,
    )

    # Trial warnings — 9:00 AM Kenya time
    scheduler.add_job(
        job_trial_alerts,
        CronTrigger(hour=9, minute=0, timezone=KENYA_TZ),
        args=[bot],
        id="trial_alerts",
        name="Trial expiry alerts",
    )
    
    # P19: Proactive token depletion alerts — 07:00 AM Kenya time
    scheduler.add_job(
        job_token_depletion_check,
        CronTrigger(hour=7, minute=0, timezone=KENYA_TZ),
        args=[bot],
        id="token_alerts",
        name="Electricity token alerts",
    )
    
    scheduler.add_job(
        job_fuliza_alerts,
        CronTrigger(hour=11, minute=0, timezone=KENYA_TZ),
        args=[bot],
        id="fuliza_alerts",
        name="Fuliza loan reminders",
    )
    
    # New Phase 5 jobs
    scheduler.add_job(
        job_subscription_alerts,
        CronTrigger(hour=12, minute=0, timezone=KENYA_TZ),
        args=[bot],
        id="subscription_alerts",
        name="Subscription bill reminders",
    )

    # P8-T5: Subscription renewal detection
    scheduler.add_job(
        job_subscription_renewal_alerts,
        CronTrigger(hour=9, minute=0, timezone=KENYA_TZ),
        args=[bot],
        id="subscription_renewal_alerts",
        name="Subscription renewal tracking",
    )

    # P17-T1E: Gas depletion alerts — 08:30 AM Kenya time
    scheduler.add_job(
        job_gas_alerts,
        CronTrigger(hour=8, minute=30, timezone=KENYA_TZ),
        args=[bot],
        id="gas_alerts",
        name="Gas depletion alerts",
    )

    log.info("scheduler_configured", job_count=len(scheduler.get_jobs()))
    return scheduler


# ── Job 7: Subscription renewal detection (P8-T5) ───────────────────────────

async def job_subscription_renewal_alerts(bot: Bot):
    """
    Checks for subscriptions expiring in 3 days or already expired.
    Deactivates expired ones and warns about upcoming expiry.
    """
    from apps.tg_bot.db import get_client
    import apps.tg_bot.messages as M
    from datetime import datetime, timezone, timedelta
    
    db = get_client()
    today = datetime.now(timezone.utc)
    
    # Get all active tenants
    resp = db.table("tenants").select("*").eq("subscription_active", True).in_("status", ["active", "trial"]).execute()
    tenants = resp.data or []
    
    log.info("job_subscription_renewal_check_start", count=len(tenants))
    
    for t in tenants:
        tid = t["telegram_id"]
        
        # P15-T1: Superadmin skip alerts
        if os.getenv("ADMIN_TELEGRAM_ID") and str(tid) == str(os.getenv("ADMIN_TELEGRAM_ID")):
            continue
            
        expires_at_str = t.get("subscription_expires_at")
        if not expires_at_str:
            continue
            
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            days_left = (expires_at - today).days
            
            upgrade_link = f"{os.getenv('FLY_APP_URL', 'https://mazao-ai.fly.dev')}/upgrade"
            
            # 1. Handle Expiry
            if today > expires_at:
                log.info("subscription_expired", telegram_id=tid)
                db.table("tenants").update({
                    "subscription_active": False,
                    "status": "lapsed",
                    "plan": "free"
                }).eq("id", t["id"]).execute()
                
                await bot.send_message(
                    chat_id=tid,
                    text=M.SUBSCRIPTION_EXPIRED.format(upgrade_link=upgrade_link),
                    parse_mode=ParseMode.MARKDOWN
                )
                
            # 2. Handle T-3 Reminder
            elif 0 <= days_left <= 3:
                log.info("subscription_renewal_reminder", telegram_id=tid, days_left=days_left)
                await bot.send_message(
                    chat_id=tid,
                    text=M.RENEWAL_REMINDER.format(
                        days_remaining=days_left,
                        plan_name=t.get("plan", "hustler").title(),
                        upgrade_link=upgrade_link
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
                
        except Exception as exc:
            log.error("renewal_check_failed", telegram_id=tid, error=str(exc))

