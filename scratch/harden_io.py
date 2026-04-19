ok

import re
import os

def harden_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Pattern: match sync db calls in async functions
    # This is a simplified regex: it looks for 'db.get_tenant(tid)' and wraps it.
    # We target specific known sync calls:
    
    # 1. tenant = db.get_tenant(tid)
    content = re.sub(
        r'tenant = db\.get_tenant\(tid\)',
        'tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))',
        content
    )
    
    # 2. tenant = db.get_tenant(_tg_id(update))
    content = re.sub(
        r'tenant = db\.get_tenant\(_tg_id\(update\)\)',
        'tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(_tg_id(update)))',
        content
    )
    
    # 3. db.update_tenant(tid, {"status": "paused"})
    content = re.sub(
        r'db\.update_tenant\(tid, {"status": "paused"}\)',
        'await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"status": "paused"}))',
        content
    )
    
    # 4. db.update_tenant(tid, {"status": "active"})
    content = re.sub(
        r'db\.update_tenant\(tid, {"status": "active"}\)',
        'await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"status": "active"}))',
        content
    )

    # Clean up any "Riverside" typos
    content = re.sub(r' Riverside', '', content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Hardened {filepath}")

if __name__ == "__main__":
    harden_file('apps/tg_bot/handlers.py')
