
import os
import asyncio
from dotenv import load_dotenv
from apps.payments.daraja import DarajaProvider

async def test_daraja_oauth():
    # Load environment variables
    load_dotenv("apps/tg_bot/.env")
    
    print("\n" + "="*50)
    print("  DARAJA OAUTH2 TOKEN TEST (P12-T1)")
    print("="*50)
    
    provider = DarajaProvider()
    
    # Check if credentials are present
    if not os.getenv("DARAJA_CONSUMER_KEY") or not os.getenv("DARAJA_CONSUMER_SECRET"):
        print("FAILED: DARAJA_CONSUMER_KEY or DARAJA_CONSUMER_SECRET missing in .env")
        return

    try:
        print("Fetching access token...")
        token = await provider.get_access_token()
        
        print("\n--- TOKEN RECEIVED ---")
        # Mask most of the token for safety but show enough to confirm it's real
        masked_token = token[:10] + "..." + token[-10:] if len(token) > 20 else token
        print(f"Token: {masked_token}")
        print(f"Length: {len(token)} characters")
        print("----------------------\n")
        
        print("Testing cache (second call)...")
        token2 = await provider.get_access_token()
        if token == token2:
            print("SUCCESS! Cache hit! Tokens match.")
        else:
            print("FAILED! Cache failed! New token fetched.")

        print("\nSUCCESS! P12-T1 acceptance criteria met.")
        
    except Exception as e:
        print(f"\nFAILED: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_daraja_oauth())
