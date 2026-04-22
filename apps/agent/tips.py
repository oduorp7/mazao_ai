"""
AI Tips Engine (P16-T1)

Generates short, contextual, culturally-aware engagement tips after user
actions (e.g. token entry). Designed to be a safe, optional enhancement:
- Uses the cheap "tips" LLM tier (free Mistral 7B by default)
- Never raises: returns None on any failure (caller must handle gracefully)
- Rate-limited by the caller (show every Nth entry or on anomaly)
- Strict output shape: max 2 short sentences, plain text

WWFD Protocol: This module MUST NOT crash the core token flow.
All errors are swallowed and logged; fallback is simply no tip shown.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from apps.agent.llm import get_llm
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

# Hard cap on generation time. If the free model is slow/rate-limited,
# we abort quickly and the user sees the normal response without a tip.
TIP_TIMEOUT_SECONDS = 6.0

SYSTEM_PROMPT = (
    "You are MazaoAI, a warm, brief energy coach for Kenyan households. "
    "Given a user's latest electricity token purchase and usage context, "
    "write ONE short, specific, actionable tip in plain English.\n\n"
    "STRICT RULES:\n"
    "- Maximum 2 sentences (under 35 words total).\n"
    "- Be specific using the numbers provided. No generic advice.\n"
    "- Friendly and empowering tone. Never shaming.\n"
    "- No emojis. No markdown. No preamble like 'Tip:' or 'Here is'.\n"
    "- Do NOT invent numbers. Only reference values given in the context.\n"
    "- Kenyan context: KES currency, Stima tokens, common appliances "
    "(fridge, iron box, water heater, kettle)."
)


def _build_user_prompt(ctx: dict[str, Any]) -> str:
    """Build a compact, grounded user message from context."""
    lines = [
        "User's electricity token context:",
        f"- Units purchased now: {ctx.get('units')} kWh",
        f"- Household type: {ctx.get('household_type', 'standard')}",
        f"- Daily usage rate: {ctx.get('daily_rate')} kWh/day",
        f"- Days of supply remaining: {ctx.get('days_remaining')}",
        f"- Total token entries so far: {ctx.get('entry_count')}",
    ]
    if ctx.get("amount_paid"):
        lines.append(f"- Amount paid: KES {ctx['amount_paid']}")
    if ctx.get("personal_rate"):
        lines.append(
            f"- Personal avg rate: {ctx['personal_rate']} kWh/day "
            f"(vs Kenya baseline "
            f"{ctx.get('population_rate', 'n/a')} kWh/day)"
        )
    if ctx.get("anomaly"):
        lines.append(
            "- ANOMALY: This reading is unusual vs their history."
        )
    lines.append("")
    lines.append("Write the tip now.")
    return "\n".join(lines)


def _sanitize(text: str) -> Optional[str]:
    """Trim, strip markdown/emojis basics, and enforce length cap."""
    if not text:
        return None
    cleaned = text.strip().strip('"').strip("'")
    # Remove common preambles the model sometimes emits.
    for prefix in ("Tip:", "TIP:", "Here is a tip:", "Here's a tip:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
    # Hard cap at ~240 chars to keep Telegram UX tight.
    if len(cleaned) > 240:
        cleaned = cleaned[:237].rsplit(" ", 1)[0] + "..."
    return cleaned or None


def _generate_sync(ctx: dict[str, Any]) -> Optional[str]:
    """Blocking LLM call. Runs in a thread via asyncio.to_thread."""
    try:
        llm = get_llm(model_type="tips")
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_user_prompt(ctx)),
        ]
        resp = llm.invoke(messages)
        content = getattr(resp, "content", None)
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return _sanitize(content or "")
    except Exception as exc:
        log.warning("tip_generation_failed", error=str(exc))
        return None


async def generate_tip(ctx: dict[str, Any]) -> Optional[str]:
    """
    Async, timeout-protected tip generation. Returns None on failure.
    Safe to call unconditionally; caller decides when to show.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_generate_sync, ctx),
            timeout=TIP_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.warning("tip_generation_timeout", timeout=TIP_TIMEOUT_SECONDS)
        return None
    except Exception as exc:
        log.warning("tip_generation_unexpected", error=str(exc))
        return None


def should_show_tip(entry_count: int, anomaly: bool) -> bool:
    """
    Engagement rate-limiter.
    - TESTING PHASE: Show every time for the first 100 entries.
    - Always show on anomaly.
    """
    if anomaly:
        return True
    if entry_count <= 0:
        return False
    
    # Force show for testing quality (will revert to every 3rd later)
    if entry_count <= 100:
        return True
        
    return (entry_count - 1) % 3 == 0
