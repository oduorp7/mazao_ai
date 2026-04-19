
import re
import os

def harden():
    path = 'apps/tg_bot/handlers.py'
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        # Match 'tenant = db.get_tenant(tid)' or 'tenant = db.get_tenant(_tg_id(update))'
        # BUT only if it doesn't already have 'await'
        if 'db.get_tenant' in line and 'await' not in line:
            line = line.replace('db.get_tenant', 'await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant')
            line = line.rstrip() + '))\n'
        
        # Match 'db.update_tenant(tid, {"status": "paused"})'
        if 'db.update_tenant' in line and 'await' not in line:
            line = line.replace('db.update_tenant', 'await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant')
            line = line.rstrip() + '))\n'
            
        new_lines.append(line)

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Hardened handlers.py")

if __name__ == "__main__":
    harden()
