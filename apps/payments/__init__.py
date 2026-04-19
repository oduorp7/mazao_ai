import os
from .base import PaymentProvider
from .africastalking import AfricasTalkingProvider

def get_provider() -> PaymentProvider:
    """Factory to return the active payment provider."""
    provider_type = os.getenv("PAYMENT_PROVIDER", "africastalking").lower()
    
    if provider_type == "africastalking":
        return AfricasTalkingProvider(
            username=os.getenv("AT_USERNAME", "sandbox"),
            api_key=os.getenv("AT_API_KEY", ""),
            product_name=os.getenv("AT_SHORTCODE", "MazaoAI")
        )
    
    # Placeholder for future Daraja provider (Phase 8)
    if provider_type == "daraja":
        # return DarajaProvider(...)
        raise NotImplementedError("Daraja provider integration pending (Phase 8).")
        
    return AfricasTalkingProvider(
        username=os.getenv("AT_USERNAME", "sandbox"),
        api_key=os.getenv("AT_API_KEY", ""),
        product_name=os.getenv("AT_SHORTCODE", "MazaoAI")
    )
