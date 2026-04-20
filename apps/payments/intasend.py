"""
IntasendProvider — Replaces AfricasTalkingProvider (Phase 6 Amendment 2).

Parses Intasend C2B/STK webhook payloads into ParsedTransaction.
Uses the intasend Python SDK for outbound operations.
"""

import os
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
