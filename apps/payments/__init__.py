"""
Payment provider factory (Phase 6 Amendment 2).

Returns the active payment provider based on PAYMENT_PROVIDER env var.
Default: intasend.
"""

import os
from .base import PaymentProvider
from .intasend import IntasendProvider


def get_provider() -> PaymentProvider:
    """Factory to return the active payment provider."""
    provider_type = os.getenv("PAYMENT_PROVIDER", "intasend").lower()

    if provider_type == "intasend":
        from .intasend import IntasendProvider
        return IntasendProvider()

    if provider_type == "daraja":
        from .daraja import DarajaProvider
        return DarajaProvider()

    # Default fallback
    from .intasend import IntasendProvider
    return IntasendProvider()
