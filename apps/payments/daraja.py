import os
import base64
import time
import httpx
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
        
        # Token Caching (P12-T1)
        self._access_token = None
        self._token_expiry = 0

    async def get_access_token(self) -> str:
        """
        P12-T1: Implement OAuth2 token acquisition with caching.
        Returns the access token from Safaricom.
        """
        # Return cached token if still valid
        if self._access_token and time.time() < self._token_expiry:
            log.info("daraja_token_cache_hit")
            return self._access_token

        if not self.consumer_key or not self.consumer_secret:
            log.error("daraja_missing_credentials")
            raise ValueError("DARAJA_CONSUMER_KEY and DARAJA_CONSUMER_SECRET must be set")

        log.info("daraja_token_fetch_start")
        
        # Prepare Basic Auth header
        auth_str = f"{self.consumer_key}:{self.consumer_secret}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        headers = {"Authorization": f"Basic {encoded_auth}"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            
            if resp.status_code != 200:
                log.error("daraja_token_fetch_failed", status=resp.status_code, body=resp.text)
                raise Exception(f"Failed to fetch Daraja token: {resp.status_code}")
                
            data = resp.json()
            self._access_token = data["access_token"]
            # Set expiry with a 60s buffer
            self._token_expiry = time.time() + int(data["expires_in"]) - 60
            
            log.info("daraja_token_fetch_success", expires_in=data["expires_in"])
            return self._access_token

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
