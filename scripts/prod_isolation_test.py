import os
import requests
import json
import time

def test_api(name, url, model, key_env, headers_extra=None):
    key = os.getenv(key_env)
    print(f"\n[TIER: {name}]")
    if not key:
        print(f"STATUS: SKIP - No {key_env}")
        return
    
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if headers_extra:
        headers.update(headers_extra)
        
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say OK"}]
    }
    
    try:
        start = time.perf_counter()
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        latency = int((time.perf_counter() - start) * 1000)
        print(f"HTTP_CODE: {res.status_code}")
        print(f"LATENCY: {latency}ms")
        print(f"RESPONSE: {res.text[:200]}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    # Tier 1: Anthropic (Should fail or skip if no key)
    test_api("ANTHROPIC", "https://api.anthropic.com/v1/messages", "claude-3-5-sonnet-20240620", "ANTHROPIC_API_KEY", 
             {"x-api-key": os.getenv("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"})
    
    # Tier 2: OpenRouter Paid
    test_api("OPENROUTER_PAID", "https://openrouter.ai/api/v1/chat/completions", "deepseek/deepseek-chat", "OPENROUTER_API_KEY")
    
    # Tier 3: OpenRouter Free
    test_api("OPENROUTER_FREE", "https://openrouter.ai/api/v1/chat/completions", "liquid/lfm-2.5-1.2b-instruct:free", "OPENROUTER_API_KEY")
    
    # Tier 4: Mistral Direct
    test_api("MISTRAL_DIRECT", "https://api.mistral.ai/v1/chat/completions", "open-mistral-nemo", "MISTRAL_API_KEY")
