
import os
import asyncio
from dotenv import load_dotenv
from apps.agent.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage

# Load env from the specific path we found
load_dotenv("apps/tg_bot/.env")

async def test_llm_connectivity():
    print("\n" + "="*50)
    print("  MAZAO AI — LLM CONNECTIVITY TEST")
    print("="*50)
    
    priority = os.getenv("LLM_PRIORITY", "openrouter")
    print(f"Current Priority: {priority}")
    
    try:
        llm = get_llm()
        print(f"Initialized LLM: {llm.__class__.__name__}")
        
        test_message = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello! Are you DeepSeek or Claude? Please identify yourself briefly.")
        ]
        
        print("\nSending test message...")
        response = await llm.ainvoke(test_message)
        
        print("\n--- RESPONSE ---")
        # Ensure we can print UTF-8 characters even if the terminal is cp1252
        print(response.content.encode('ascii', 'ignore').decode('ascii'))
        print("----------------\n")
        print("SUCCESS! The brain is connected and responding.")
        
    except Exception as e:
        print(f"\nFAILED: {str(e)}")
        if "API key" in str(e).lower():
            print("Tip: Check if you saved the API key in apps/tg_bot/.env")

if __name__ == "__main__":
    asyncio.run(test_llm_connectivity())
