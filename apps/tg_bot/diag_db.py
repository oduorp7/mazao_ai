import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Path setup
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))
load_dotenv()

def diagnostic():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    print(f"URL: {url}")
    print(f"Key Prefix: {key[:10]}...")
    
    client = create_client(url, key)
    
    print("\n1. Testing 'tenants' table...")
    try:
        resp = client.table("tenants").select("id").limit(1).execute()
        print(f"SUCCESS: {resp.data}")
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n2. Testing 'reports' table...")
    try:
        resp = client.table("reports").select("id").limit(1).execute()
        print(f"SUCCESS: {resp.data}")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    diagnostic()
