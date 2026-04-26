"""
IntasendProvider — Replaces AfricasTalkingProvider (Phase 6 Amendment 2).

Parses Intasend C2B/STK webhook payloads into ParsedTransaction.
Uses the intasend Python SDK for outbound operations.
"""

import os
import re
import asyncio
from datetime import datetime
from typing import Optional
from .base import PaymentProvider, ParsedTransaction
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)


class IntasendProvider(PaymentProvider):

    async def handle_webhook(self, payload: dict) -> Optional[ParsedTransaction]:
        """
        Parse Intasend webhook payload into ParsedTransaction.

        Intasend webhook fields:
            invoice_id, state, value, account, name, provider,
            api_ref, failed_reason, created_at, updated_at

        Only process state='COMPLETE'. PENDING/FAILED return None.
        """
        log.info("intasend_webhook_received", state=payload.get("state"))

        state = payload.get("state", "").upper()
        if state != "COMPLETE":
            log.info("intasend_webhook_skipped", state=state,
                     reason="only COMPLETE processed")
            return None

        # Validate required fields
        invoice_id = payload.get("invoice_id")
        value = payload.get("value")
        account = payload.get("account")

        if not invoice_id or value is None or not account:
            log.warn("intasend_webhook_malformed", payload_keys=list(payload.keys()))
            return None

        # Parse amount
        try:
            amount = float(value)
        except (ValueError, TypeError):
            log.warn("intasend_amount_parse_failed", value=value)
            return None

        # Parse timestamp
        ts_str = payload.get("updated_at") or payload.get("created_at")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.utcnow()
        except (ValueError, AttributeError):
            ts = datetime.utcnow()

        return ParsedTransaction(
            trans_id=str(invoice_id),
            amount=amount,
            msisdn=str(account),
            first_name=payload.get("name", "Customer"),
            bill_ref=payload.get("api_ref", ""),
            timestamp=ts,
            provider="intasend"
        )

    async def register_callback_url(self, callback_url: str) -> bool:
        """
        Intasend webhook URL is set in the dashboard, not via API.
        This method logs the requirement and returns True (no-op).
        """
        log.info("intasend_callback_info",
                 msg="Webhook URL must be set manually in Intasend dashboard",
                 url=callback_url)
        return True

    async def initiate_stk_push(self, phone_number: str, amount: int, account_ref: str, narrative: str = "Mazao AI Subscription") -> dict:
        """Initiate STK push via Intasend SDK."""
        token = os.getenv("INTASEND_SECRET_KEY", "")
        publishable_key = os.getenv("INTASEND_PUBLISHABLE_KEY", "")

        if not token or not publishable_key:
            log.error("stk_push_missing_credentials")
            return {"error": "Intasend credentials not configured"}

        formatted_phone = self._format_phone(phone_number)
        is_test = os.getenv("INTASEND_ENV", "sandbox").lower() in ("sandbox", "test")

        log.info("intasend_stk_push_initiating",
                 phone=formatted_phone,
                 amount=amount,
                 account_ref=account_ref,
                 test_mode=is_test)

        try:
            from intasend import APIService

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

            log.info("intasend_stk_push_success",
                     phone=formatted_phone,
                     amount=amount)
            return response if isinstance(response, dict) else {"response": str(response)}

        except Exception as e:
            log.exception("intasend_stk_push_failed",
                          phone=formatted_phone,
                          amount=amount,
                          error=str(e))
            return {"error": str(e)}

    def _format_phone(self, phone: str) -> str:
        """Normalize phone to 2547XXXXXXXX format."""
        phone = re.sub(r"[^0-9]", "", phone)
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        elif phone.startswith("7"):
            phone = "254" + phone
        elif phone.startswith("+"):
            phone = phone.lstrip("+")
        return phone
