import os, sys, httpx, json
sys.path.insert(0, 'C:/Users/LENOVO/Documents/mazao_ai')
from dotenv import load_dotenv
load_dotenv('C:/Users/LENOVO/Documents/mazao_ai/apps/tg_bot/.env')

url = os.environ['SUPABASE_URL']
key = os.environ['SUPABASE_SERVICE_KEY']

headers = {
    'apikey': key,
    'Authorization': 'Bearer ' + key,
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

# Use Supabase PostgREST introspection endpoint
r = httpx.get(
    url + '/rest/v1/token_entries?limit=0',
    headers=headers,
    timeout=15
)
print("STATUS:", r.status_code)
# Print the response headers which contain column info
for k, v in r.headers.items():
    print(f"  {k}: {v}")

print()
print("Body:", r.text[:500])
