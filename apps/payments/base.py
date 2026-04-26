from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ParsedTransaction:
    trans_id: str
    amount: float
    msisdn: str
    first_name: str
    bill_ref: str
    timestamp: datetime
    provider: str

class PaymentProvider(ABC):
    @abstractmethod
    async def handle_webhook(self, payload: dict) -> ParsedTransaction:
        """Parse provider-specific webhook payload into ParsedTransaction."""
        pass

    @abstractmethod
    async def register_callback_url(self, callback_url: str) -> bool:
        """Register the webhook callback URL with the provider."""
        pass

    @abstractmethod
    async def initiate_stk_push(self, phone_number: str, amount: int, account_ref: str, narrative: str = "Mazao AI Subscription") -> dict:
        """Initiate STK push for the active provider."""
        pass
