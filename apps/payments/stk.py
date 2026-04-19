import os
import aiohttp
import re
from apps.agent.utils.logging import get_logger

log = get_logger(__name__)

async def initiate_stk_push(phone_number: str, amount: int, account_ref: str) -> dict:
    """
    P7-T1: Initiates M-Pesa STK Push via Africa's Talking.
    Standardizes phone to 254XXXXXXXXX format.
    """
    username = os.getenv("AT_USERNAME", "sandbox")
    api_key = os.getenv("AT_API_KEY", "")
    product_name = os.getenv("AT_SHORTCODE", "MazaoAI")
    
    # 1. Phone Formatting (254XXXXXXXXX)
    clean_phone = re.sub(r"\D", "", phone_number)
    if clean_phone.startswith("0"):
        clean_phone = "254" + clean_phone[1:]
    elif clean_phone.startswith("+"):
        clean_phone = clean_phone[1:]
    elif not clean_phone.startswith("254"):
        clean_phone = "254" + clean_phone
        
    if len(clean_phone) != 12:
        return {"error": f"Invalid phone format: {phone_number}"}

    # 2. AT Checkout Payload
    url = "https://payments.sandbox.africastalking.com/mobile/checkout/request" if username == "sandbox" else "https://payments.africastalking.com/mobile/checkout/request"
    
    payload = {
        "username": username,
        "productName": product_name,
        "phoneNumber": f"+{clean_phone}",
        "currencyCode": "KES",
        "amount": float(amount),
        "metadata": {
            "account_ref": account_ref
        }
    }
    headers = {
        "ApiKey": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    log.info("stk_push_initiation", phone=clean_phone, amount=amount, ref=account_ref)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=15) as resp:
                res_json = await resp.json()
                if resp.status == 201 or (resp.status == 200 and res_json.get("status") == "PendingConfirmation"):
                    log.info("stk_push_success", tid=res_json.get("transactionId"))
                    return res_json
                else:
                    log.error("stk_push_failed", status=resp.status, response=res_json)
                    return {"error": res_json.get("errorMessage", "Unknown AT error")}
    except Exception as e:
        log.exception("stk_push_exception", error=str(e))
        return {"error": str(e)}
