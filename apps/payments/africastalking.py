import os
import aiohttp
import re
from datetime import datetime
from .base import PaymentProvider, ParsedTransaction
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

class AfricasTalkingProvider(PaymentProvider):
    def __init__(self, username: str, api_key: str, product_name: str):
        self.username = username
        self.api_key = api_key
        self.product_name = product_name
        self.base_url = "https://payments.sandbox.africastalking.com" if username == "sandbox" else "https://payments.africastalking.com"

    async def handle_webhook(self, payload: dict) -> ParsedTransaction:
        """
        Parses AT C2B payload:
        {
            "transactionId": "...",
            "value": "KES 500.00",
            "phoneNumber": "+254...",
            "firstName": "...",
            "productName": "...",
            "transactionDate": "2026-04-20 02:30:00"
        }
        """
        log.info("at_webhook_parsing", trans_id=payload.get("transactionId"))
        
        # Parse value: "KES 500.00" -> 500.0
        val_str = payload.get("value", "0")
        amount = 0.0
        match = re.search(r"([\d,]+\.?\d*)", val_str)
        if match:
            amount = float(match.group(1).replace(",", ""))

        # Parse timestamp
        t_str = payload.get("transactionDate")
        try:
            ts = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S") if t_str else datetime.utcnow()
        except ValueError:
            ts = datetime.utcnow()

        return ParsedTransaction(
            trans_id=payload.get("transactionId", "unknown"),
            amount=amount,
            msisdn=payload.get("phoneNumber", "unknown"),
            first_name=payload.get("firstName", "Guest"),
            bill_ref=payload.get("productName", "default"),
            timestamp=ts,
            provider="africastalking"
        )

    async def register_callback_url(self, callback_url: str) -> bool:
        """Registers the callback URL for C2B notifications."""
        url = f"{self.base_url}/mobile/callback/register"
        payload = {
            "username": self.username,
            "productName": self.product_name,
            "callbackUrl": callback_url
        }
        headers = {
            "ApiKey": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        log.info("at_registration_request", url=url, product=self.product_name)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                    res_json = await resp.json()
                    if resp.status == 201 or (resp.status == 200 and res_json.get("status") == "Success"):
                        log.info("at_registration_success", response=res_json)
                        return True
                    else:
                        log.error("at_registration_failed", status=resp.status, response=res_json)
                        return False
        except Exception as e:
            log.exception("at_registration_exception", error=str(e))
            return False
