"""
STK Push initiator via Intasend SDK (Phase 6 Amendment 2 / Phase 7 prep).

Usage:
    result = await initiate_stk_push("0712345678", 500, "MAZAO-abc12345")
"""

import os
import re
import asyncio
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)


def _format_phone(phone: str) -> str:
    """Normalize phone to 2547XXXXXXXX format."""
    phone = re.sub(r"[^0-9]", "", phone)  # Strip non-digits
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("7"):
        phone = "254" + phone
    elif phone.startswith("+"):
        phone = phone.lstrip("+")
    # Already 254... — pass through
    return phone


async def initiate_stk_push(
    phone_number: str,
    amount: int,
    account_ref: str,
    narrative: str = "Mazao AI Subscription"
) -> dict:
    """
    Initiate M-Pesa STK Push via Intasend SDK.

    Args:
        phone_number: Customer phone (any format: 07XX, +2547XX, 2547XX)
        amount: Amount in KES (integer)
        account_ref: Reference string (format: MAZAO-{tenant_id[:8]})
        narrative: User-facing payment description

    Returns:
        dict with Intasend response on success, or {"error": "..."} on failure.
    """
    token = os.getenv("INTASEND_SECRET_KEY", "")
    publishable_key = os.getenv("INTASEND_PUBLISHABLE_KEY", "")

    if not token or not publishable_key:
        log.error("stk_push_missing_credentials")
        return {"error": "Intasend credentials not configured"}

    formatted_phone = _format_phone(phone_number)
    is_test = os.getenv("INTASEND_ENV", "sandbox").lower() in ("sandbox", "test")

    log.info("stk_push_initiating",
             phone=formatted_phone,
             amount=amount,
             account_ref=account_ref,
             test_mode=is_test)

    try:
        from intasend import APIService

        # Run SDK call in executor (it's synchronous)
        def _do_stk():
            service = APIService(
                token=token,
                publishable_key=publishable_key,
                test=is_test
            )
            return service.collect.mpesa_stk_push(
                phone_number=formatted_phone,
                email="noreply@mazao.ai",
                amount=amount,
                narrative=narrative
            )

        response = await asyncio.get_event_loop().run_in_executor(None, _do_stk)

        log.info("stk_push_success",
                 phone=formatted_phone,
                 amount=amount,
                 response=str(response)[:200])
        return response if isinstance(response, dict) else {"response": str(response)}

    except Exception as e:
        log.exception("stk_push_failed",
                      phone=formatted_phone,
                      amount=amount,
                      error=str(e))
        return {"error": str(e)}
