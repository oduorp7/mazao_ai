import os
import requests
import json
import time

api_key = "1sYV0SNZ2mr4SFyInS9AqUjmnk8Fu9cw"

def test_mistral_direct():
    print("--- Testing Mistral Direct (Sourced Key) ---")
    try:
        start_time = time.perf_counter()
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "open-mistral-nemo",
            "messages": [{"role": "user", "content": "Say OK"}],
        }
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        latency = int((time.perf_counter() - start_time) * 1000)
        
        if response.status_code == 200:
            print(f"MISTRAL: PASS - {response.json()['choices'][0]['message']['content'].strip()} (Latency: {latency}ms)")
            return True
        else:
            print(f"MISTRAL: FAIL - Status {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"MISTRAL: FAIL - {type(e).__name__}: {str(e)}")
        return False

if __name__ == "__main__":
    test_mistral_direct()
