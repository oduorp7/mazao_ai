import os
import requests
import json
import time
from dotenv import load_dotenv

# Load key from environment file
load_dotenv("apps/tg_bot/.env")
api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")

def test_model(model_id):
    print(f"Testing {model_id}...")
    if not api_key:
        print(f"ERROR: {model_id} - OPENROUTER_API_KEY not found in environment")
        return False
        
    try:
        start_time = time.perf_counter()
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "Mazao AI Diagnostic"
        }
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Say OK"}],
        }
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        latency = int((time.perf_counter() - start_time) * 1000)
        
        if response.status_code == 200:
            print(f"PASS: {model_id} (Latency: {latency}ms)")
            return True
        else:
            print(f"FAIL: {model_id} - Status {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"ERROR: {model_id} - {type(e).__name__}: {str(e)}")
        return False

if __name__ == "__main__":
    test_model("qwen/qwen3-next-80b-a3b-instruct:free")
    test_model("meta-llama/llama-3.2-3b-instruct:free")
    test_model("liquid/lfm-2.5-1.2b-instruct:free")
