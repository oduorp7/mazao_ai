import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import time

# Load env from apps/tg_bot/.env
load_dotenv("apps/tg_bot/.env")

def test_mistral_direct():
    print("--- Testing Mistral Direct ---")
    key = os.getenv("MISTRAL_API_KEY")
    if not key:
        print("MISTRAL: FAIL - No key in env")
        return False
    
    try:
        start_time = time.perf_counter()
        llm = ChatOpenAI(
            model="open-mistral-nemo",
            openai_api_key=key,
            openai_api_base="https://api.mistral.ai/v1",
            timeout=20
        )
        res = llm.invoke([HumanMessage(content="Say OK")])
        latency = int((time.perf_counter() - start_time) * 1000)
        print(f"MISTRAL: PASS - {res.content.strip()} (Latency: {latency}ms)")
        return True
    except Exception as e:
        print(f"MISTRAL: FAIL - {type(e).__name__}: {str(e)}")
        return False

def test_openrouter_free():
    print("\n--- Testing OpenRouter Free Stack ---")
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER: FAIL - No key in env")
        return
    
    free_models = [
        "deepseek/deepseek-chat:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "meta-llama/llama-3.3-70b-instruct:free"
    ]
    
    for model in free_models:
        try:
            start_time = time.perf_counter()
            llm = ChatOpenAI(
                model=model,
                openai_api_key=key,
                openai_api_base="https://openrouter.ai/api/v1",
                timeout=10,
                default_headers={"X-Title": "Mazao AI Diagnostic"}
            )
            res = llm.invoke([HumanMessage(content="Say OK")])
            latency = int((time.perf_counter() - start_time) * 1000)
            print(f"OPENROUTER ({model}): PASS - {res.content.strip()} (Latency: {latency}ms)")
        except Exception as e:
            print(f"OPENROUTER ({model}): FAIL - {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    test_mistral_direct()
    test_openrouter_free()
