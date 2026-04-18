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

sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

import db
import messages as M
from utils.logging import get_logger

log = get_logger(__name__)

# Kenya is UTC+3
KENYA_TZ = "Africa/Nairobi"


# ── Job 1: Daily reports ──────────────────────────────────────────────────────

async def job_daily_reports(bot: Bot) -> None:
    """
    Runs the Mazao pipeline for every active/trial tenant
    and sends the result to their Telegram chat.
    """
    tenants = db.get_all_active_tenants()
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
    """Run pipeline for one tenant and send result."""
    tid = tenant["telegram_id"]

    log.info("processing_tenant", telegram_id=tid, tenant_id=tenant["id"])

    # Import here to avoid circular imports
    from pipeline import run_pipeline
    from state import RawTransaction, TransactionType

    # Production: pull from Daraja API using tenant's shortcode
    # Dev: use sample data
    sample_txs = [
        RawTransaction(
            mpesa_ref=f"SCHED{tenant['id'][:4]}01",
            amount=5000.0,
            phone="0712000001",
            name="CUSTOMER ONE",
            shortcode=tenant.get("mpesa_till", "123456"),
            transaction_type=TransactionType.C2B,
            timestamp=datetime.utcnow() - timedelta(hours=12),
        ),
        RawTransaction(
            mpesa_ref=f"SCHED{tenant['id'][:4]}02",
            amount=2500.0,
            phone="0723000002",
            name="SUPPLIER LTD",
            shortcode=tenant.get("mpesa_till", "123456"),
            transaction_type=TransactionType.B2B,
            timestamp=datetime.utcnow() - timedelta(hours=6),
        ),
    ]

    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: run_pipeline(
            tenant_id=str(tenant["id"]),
            raw_transactions=sample_txs,
            triggered_by="scheduled",
        ),
    )

    if result.report_text_en:
        await bot.send_message(
            chat_id=tid,
            text=result.report_text_en,
            parse_mode=ParseMode.MARKDOWN,
        )

        if result.reconciliation:
            r = result.reconciliation
            db.save_report(
                tenant_id=str(tenant["id"]),
                period=datetime.utcnow().strftime("%Y-%m"),
                summary={
                    "income": r.total_income,
                    "expenses": r.total_expenses,
                    "profit": r.net_profit,
                    "flagged": r.flagged_count,
                },
            )

        log.info("report_sent", telegram_id=tid)
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
    """
    Checks every active tenant against KRA obligation calendar.
    Sends alerts at T-7, T-2, and T+0 (overdue).
    """
    tenants = db.get_all_active_tenants()
    today = datetime.utcnow().date()

    log.info("deadline_alerts_start", tenant_count=len(tenants))

    for tenant in tenants:
        tid = tenant["telegram_id"]

        # Get last report to estimate obligation amounts
        report = db.get_latest_report(str(tenant["id"]))
        income = report["summary"].get("income", 0) if report else 0
        expenses = report["summary"].get("expenses", 0) if report else 0

        # VAT estimate
        net_vat = max((income - expenses) * 0.16, 0)
        # PAYE rough estimate: 30% of salary spend
        salary = expenses * 0.3
        paye_est = salary * 0.30

        ob_amounts = {
            "VAT": net_vat,
            "PAYE": paye_est,
            "NSSF": salary * 0.06,
            "NHIF/SHA": salary * 0.0275,
        }

        # Calculate due dates for current/next month
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
                    log.info("alert_sent_7d", telegram_id=tid, obligation=ob["type"])

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
                    log.info("alert_sent_2d", telegram_id=tid, obligation=ob["type"])

                elif days_until < 0:
                    await bot.send_message(
                        chat_id=tid,
                        text=M.DEADLINE_OVERDUE.format(
                            obligation_type=ob["type"],
                            penalty=penalty,
                        ),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    log.info("alert_sent_overdue", telegram_id=tid, obligation=ob["type"])

            except Exception as exc:
                log.exception(
                    "alert_failed",
                    telegram_id=tid,
                    obligation=ob["type"],
                    error=str(exc),
                )

    log.info("deadline_alerts_complete")


# ── Job 3: Trial expiry warnings ──────────────────────────────────────────────

async def job_trial_warnings(bot: Bot) -> None:
    """
    Warns users whose trial expires in 3 days.
    """
    tenants = db.get_all_active_tenants()

    for tenant in tenants:
        if tenant.get("plan") != "trial":
            continue

        days_left = tenant.get("trial_days_left", 0)

        # Decrement trial days
        db.update_tenant(
            tenant["telegram_id"],
            {"trial_days_left": max(days_left - 1, 0)},
        )

        if days_left in (3, 1):
            try:
                await bot.send_message(
                    chat_id=tenant["telegram_id"],
                    text=M.TRIAL_WARNING.format(
                        days=days_left,
                        till="522522",  # your M-Pesa Till
                        telegram_id=tenant["telegram_id"],
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as exc:
                log.exception(
                    "trial_warning_failed",
                    telegram_id=tenant["telegram_id"],
                    error=str(exc),
                )


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
        job_trial_warnings,
        CronTrigger(hour=9, minute=0, timezone=KENYA_TZ),
        args=[bot],
        id="trial_warnings",
        name="Trial expiry warnings",
        misfire_grace_time=300,
        coalesce=True,
    )

    log.info("scheduler_configured", job_count=len(scheduler.get_jobs()))
    return scheduler
