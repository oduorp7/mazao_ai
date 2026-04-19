# Mazao AI — Payment Abstraction Layer

This module provides a provider-agnostic interface for handling mobile money transactions (currently M-Pesa).

## Architecture

1.  **`PaymentProvider` (Base)**: An abstract class defining the contract for parsing webhooks and registering callback URLs.
2.  **`ParsedTransaction` (Dataclass)**: A standardized format for transaction data, regardless of the provider's native JSON structure.
3.  **`AfricasTalkingProvider`**: Implementation for Africa's Talking C2B notifications.
4.  **`Factory (get_provider)`**: Dynamically loads the provider specified in the `PAYMENT_PROVIDER` environment variable.

## Adding a New Provider (e.g., Daraja)

1.  Create `apps/payments/daraja.py`.
2.  Inherit from `PaymentProvider`.
3.  Implement `handle_webhook` (parsing Safaricom's native payload).
4.  Implement `register_callback_url` (C2B URL registration API).
5.  Update `get_provider()` in `__init__.py` to include the new type.

## Migration Steps (Bridge -> Daraja)

When moving from Africa's Talking to direct Daraja:
1.  Update `.env` with `PAYMENT_PROVIDER=daraja` and required credentials.
2.  The bot's core logic (`bot.py` and `handlers.py`) requires **zero changes**.
