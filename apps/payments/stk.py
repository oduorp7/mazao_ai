"""
stk.py — Payment Bridge (Phase 17 Unification).

Proxies STK initiation to the active PaymentProvider.
"""

from apps.payments import get_provider

async def initiate_stk_push(
    phone_number: str,
    amount: int,
    account_ref: str,
    narrative: str = "Mazao AI Subscription"
) -> dict:
    """
    Initiate STK Push via the active payment provider.
    
    This ensures that /upgrade command in handlers.py doesn't need to know
    which provider is currently active.
    """
    provider = get_provider()
    return await provider.initiate_stk_push(
        phone_number=phone_number,
        amount=amount,
        account_ref=account_ref,
        narrative=narrative
    )
