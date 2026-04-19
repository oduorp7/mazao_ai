
import sys
import os

def harden():
    target = 'apps/tg_bot/handlers.py'
    with open(target, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    for i, line in enumerate(lines):
        line_num = i + 1
        # Specific line hardening based on audit
        if line_num == 163:
            line = '    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(_tg_id(update)))\n'
        elif line_num in (175, 214, 245, 534, 547, 613):
            line = '    tenant = await asyncio.get_event_loop().run_in_executor(None, lambda: db.get_tenant(tid))\n'
        elif line_num == 538:
            line = '    await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"status": "paused"}))\n'
        elif line_num == 551:
            line = '    await asyncio.get_event_loop().run_in_executor(None, lambda: db.update_tenant(tid, {"status": "active"}))\n'
        
        # Also fix the handle_callback business branch which I missed in the last sls
        if 'db.set_conv_state(tid, "awaiting_name"' in line and 'await' not in line:
            line = line.replace('db.set_conv_state', 'await asyncio.get_event_loop().run_in_executor(None, lambda: db.set_conv_state')
            line = line.rstrip() + ')\n'
            
        new_lines.append(line)

    with open(target, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Surgically hardened handlers.py")

if __name__ == "__main__":
    harden()
