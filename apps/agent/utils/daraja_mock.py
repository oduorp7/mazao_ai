import json
import uuid
from datetime import datetime

class MockDarajaClient:
    """
    High-assurance mock for Safaricom Daraja API.
    Simulates STK Push and Transaction status responses.
    """
    def __init__(self, consumer_key="MOCK", consumer_secret="MOCK"):
        self.base_url = "https://sandbox.safaricom.co.ke"

    async def get_token(self):
        """Simulates Oauth token retrieval."""
        return "MOCK_ACCESS_TOKEN_" + str(uuid.uuid4())[:8]

    async def trigger_stk_push(self, phone: str, amount: int, reference: str):
        """
        Simulates initiating an STK Push collection.
        Returns a mock CheckoutRequestID.
        """
        checkout_id = f"ws_CO_{uuid.uuid4().hex[:10]}"
        return {
            "MerchantRequestID": str(uuid.uuid4()),
            "CheckoutRequestID": checkout_id,
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success"
        }

    async def query_transaction(self, checkout_id: str):
        """Simulates querying the status of an STK Push."""
        return {
            "ResponseCode": "0",
            "ResponseDescription": "The service is accepted successfully",
            "MerchantRequestID": str(uuid.uuid4()),
            "CheckoutRequestID": checkout_id,
            "ResultCode": "0",
            "ResultDesc": "The service request is processed successfully."
        }

# Singleton instance for high-assurance reuse
daraja = MockDarajaClient()
