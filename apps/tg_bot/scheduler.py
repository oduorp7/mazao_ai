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

import sys
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.constants import ParseMode

import apps.tg_bot.db as db
import apps.tg_bot.messages as M
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

# Kenya is UTC+3
KENYA_TZ = "Africa/Nairobi"


# ── Job 1: Daily reports ──────────────────────────────────────────────────────

async def job_daily_reports(bot: Bot) -> None:
    tenants = await asyncio.get_event_loop().run_in_executor(None, db.get_all_active_tenants)
    log.info("daily_reports_start", tenant_count=len(tenants))

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


# ── Job 3: Trial execution & alerts (P7-T7) ───────────────────────────────────

async def job_trial_alerts(bot: Bot) -> None:
    """P7-T7: Daily trial monitoring and expiry notifications."""
    try:
        tenants = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db.get_client().table("tenants")
            .select("*")
            .eq("plan", "free")
            .not_.is_("trial_ends_at", "null")
            .execute()
        )
        
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        log.info("trial_alerts_start", count=len(tenants.data))

        for tenant in tenants.data:
            tid = tenant["telegram_id"]
            ends_at = datetime.fromisoformat(tenant["trial_ends_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            days_left = (ends_at - today).days

            try:
                if days_left == 3:
                    await bot.send_message(
                        chat_id=tid,
                        text=M.TRIAL_EXPIRY_WARNING.format(days_remaining=3),
                        parse_mode=ParseMode.MARKDOWN
                    )
                elif days_left <= 0:
                    # Deactive and notify
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: db.get_client().table("tenants")
                        .update({"subscription_active": False})
                        .eq("id", tenant["id"])
                        .execute()
                    )
                    await bot.send_message(
                        chat_id=tid,
                        text=M.TRIAL_EXPIRED,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    log.info("trial_expired_action", tenant=tenant["id"])
            except Exception as e:
                log.error("trial_alert_tenant_failed", tid=tid, error=str(e))

    except Exception as exc:
        log.exception("trial_alerts_job_failed", error=str(exc))

# ── Job 4: Electricity token alerts (P4-T4) ──────────────────────────────────

async def job_token_alerts(bot: Bot) -> None:
    tenants = await asyncio.get_event_loop().run_in_executor(None, db.get_all_active_tenants)
    today = datetime.utcnow().date()
    
    for tenant in tenants:
        tid = tenant["telegram_id"]
        try:
            # Get latest token entry
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
            
            if not resp.data:
                continue
                
            entry = resp.data
            units = float(entry["units"])
            
            # Default rate logic from P4-T1
            daily_rate = 6.0
            h_size = tenant.get("household_size", 4)
            if h_size <= 2: daily_rate = 3.0
            elif h_size >= 6: daily_rate = 10.0
            
            days_passed = (today - datetime.fromisoformat(entry["purchase_date"]).date()).days
            units_remaining = max(units - (days_passed * daily_rate), 0)
            days_remaining = int(units_remaining / daily_rate)
            
            if days_remaining <= 3:
                depletion_date = (today + timedelta(days=days_remaining)).strftime("%d %b %Y")
                await bot.send_message(
                    chat_id=tid,
                    text=M.TOKEN_DEPLETION_ALERT.format(
                        units_remaining=units_remaining,
                        depletion_date=depletion_date,
                        days_remaining=days_remaining
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as exc:
            log.exception("token_alert_failed", telegram_id=tid, error=str(exc))


# ── Job 5: Fuliza payment reminders (P4-T4) ──────────────────────────────────

async def job_fuliza_alerts(bot: Bot) -> None:
    today = datetime.utcnow().date()
    try:
        # Get all entries due soon
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db.get_client().table("fuliza_entries")
            .select("*, tenants(telegram_id)")
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
            .select("*, tenants(telegram_id)")
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

    # Trial expiry alerts — 9:00 AM Kenya time
    scheduler.add_job(
        job_trial_alerts,
        CronTrigger(hour=9, minute=0, timezone=KENYA_TZ),
        args=[bot],
        id="trial_alerts",
        name="Trial expiry monitor",
    )

    # New Phase 4 jobs
    scheduler.add_job(
        job_token_alerts,
        CronTrigger(hour=10, minute=0, timezone=KENYA_TZ),
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

    log.info("scheduler_configured", job_count=len(scheduler.get_jobs()))
    return scheduler
