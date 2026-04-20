import os
from .base import PaymentProvider, ParsedTransaction
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

class DarajaProvider(PaymentProvider):
    def __init__(self):
        # Set these in Fly.io secrets when Paybill is approved.
        self.consumer_key = os.getenv("DARAJA_CONSUMER_KEY")
        self.consumer_secret = os.getenv("DARAJA_CONSUMER_SECRET")
        self.shortcode = os.getenv("DARAJA_SHORTCODE")
        self.passkey = os.getenv("DARAJA_PASSKEY")
        self.env = os.getenv("DARAJA_ENV", "sandbox")
        
        self.base_url = (
            "https://sandbox.safaricom.co.ke"
            if self.env == "sandbox"
            else "https://api.safaricom.co.ke"
        )

    async def handle_webhook(self, payload: dict) -> ParsedTransaction:
        """
        Parses Daraja C2B Confirmation payload.
        Expected fields: TransID, TransAmount, MSISDN, FirstName, BillRefNumber, TransTime
        """
        log.info("daraja_webhook_received", trans_id=payload.get("TransID"))
        
        from datetime import datetime
        
        # Daraja TransTime format: YYYYMMDDHHMMSS
        t_str = payload.get("TransTime")
        try:
            ts = datetime.strptime(t_str, "%Y%m%d%H%M%S") if t_str else datetime.utcnow()
        except (ValueError, TypeError):
            ts = datetime.utcnow()

        return ParsedTransaction(
            trans_id=payload.get("TransID", "unknown"),
            amount=float(payload.get("TransAmount", 0)),
            msisdn=payload.get("MSISDN", "unknown"),
            first_name=payload.get("FirstName", "Guest"),
            bill_ref=payload.get("BillRefNumber", ""),
            timestamp=ts,
            provider="daraja"
        )

    async def register_callback_url(self, callback_url: str) -> bool:
        """
        P9-T3: Stub for RegisterURL.
        This will be activated once Safaricom Paybill is approved.
        """
        if not self.consumer_key or not self.consumer_secret:
            log.info("daraja_registration_skipped", reason="credentials_not_set")
            return False
            
        log.info("daraja_registration_pending", url=callback_url)
        # TODO: Implement OAuth + RegisterURL call
        return False
