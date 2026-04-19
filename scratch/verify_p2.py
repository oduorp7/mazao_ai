
import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.getcwd())

# Mock env
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_KEY"] = "test_key"

async def verify_p2():
    print("--- Phase 2 Logic Verification ---")
    
    # 1. Check Messages
    print("[1/4] Checking messages.py...")
    from apps.tg_bot.messages import INDIVIDUAL_SHA_ALERT, ASK_LANGUAGE, STATUS
    if "{language}" in STATUS and "{due_date}" in INDIVIDUAL_SHA_ALERT:
        print("[PASS] Messages constants OK")
    else:
        print("[FAIL] Messages constants missing placeholders")

    # 2. Check Handler Structure
    print("[2/4] Checking handlers.py (Static AST)...")
    import ast
    with open("apps/tg_bot/handlers.py", "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    
    found_mystatus = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "cmd_mystatus":
            found_mystatus = True
            break
    
    if found_mystatus:
        print("[PASS] cmd_mystatus function detected")
    else:
        print("[FAIL] cmd_mystatus function missing")

    # 3. Check Scheduler Logic (Individual branching)
    print("[3/4] Checking scheduler.py (Static AST)...")
    with open("apps/tg_bot/scheduler.py", "r", encoding="utf-8") as f:
        stree = ast.parse(f.read())
    
    found_individual_branch = False
    for node in ast.walk(stree):
        if isinstance(node, ast.If):
            # Try to find user_type check
            source = ast.unparse(node.test) if hasattr(ast, "unparse") else ""
            if "user_type" in source and "individual" in source:
                found_individual_branch = True
                break
    
    if found_individual_branch:
        print("[PASS] Individual obligation branch found in scheduler")
    else:
        print("[FAIL] Individual obligation branch missing in scheduler")

    # 4. Check DB obligations logic
    print("[4/4] Checking db.py obligations logic...")
    import apps.tg_bot.db as db
    # Mock tenant
    mock_tenant = {"user_type": "individual", "employment_status": "employed"}
    # We can't easily call db.get_individual_obligations without a mock client
    # but we can check if it exists
    if hasattr(db, "get_individual_obligations"):
        print("[PASS] db.get_individual_obligations exists")
    else:
        print("[FAIL] db.get_individual_obligations missing")

    print("\n--- Phase 2 Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(verify_p2())
