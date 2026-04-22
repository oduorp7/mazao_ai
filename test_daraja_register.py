
import os
import asyncio
from dotenv import load_dotenv
from apps.payments.daraja import DarajaProvider

async def test_daraja_register_url():
    # Load environment variables
    load_dotenv("apps/tg_bot/.env")
    
    print("\n" + "="*50)
    print("  DARAJA C2B REGISTER URL TEST (P12-T2)")
    print("="*50)
    
    provider = DarajaProvider()
    
    # Check if credentials are present
    if not os.getenv("DARAJA_CONSUMER_KEY") or not os.getenv("DARAJA_CONSUMER_SECRET"):
        print("FAILED: DARAJA_CONSUMER_KEY or DARAJA_CONSUMER_SECRET missing in .env")
        return

    # Use a dummy but correctly formatted URL for sandbox testing
    # In production, this must be the live Fly.io URL
    callback_url = "https://mazao-ai.fly.dev/payments"
    
    try:
        print(f"Registering URLs for ShortCode: {provider.shortcode}")
        print(f"Base URL: {provider.base_url}")
        print(f"Callback Base: {callback_url}")
        
        success = await provider.register_callback_url(callback_url)
        
        if success:
            print("\nSUCCESS! Safaricom returned ResponseCode 0.")
            print("P12-T2 acceptance criteria met.")
        else:
            print("\nFAILED: Safaricom did not return ResponseCode 0.")
            print("Check logs for the full response.")
            
    except Exception as e:
        print(f"\nFAILED: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_daraja_register_url())
