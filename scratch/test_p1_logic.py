
import os
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add project root to path for the test script
sys.path.insert(0, os.getcwd())

# Mock and setup env vars for isolated test
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
os.environ["ANTHROPIC_API_KEY"] = "test_key"
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_KEY"] = "test_key"

async def test_logic():
    print("--- Phase 1 Logic Verification ---")
    
    # 1. Check Imports
    print("[1/3] Verifying absolute imports...")
    try:
        from apps.tg_bot.bot import main as bot_main
        from apps.tg_bot.handlers import cmd_start, handle_message
        from apps.tg_bot.scheduler import job_daily_reports
        from apps.agent.pipeline import run_pipeline
        print("✅ Imports OK")
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return

    # 2. Check removed commands
    print("[2/3] Checking removed commands...")
    from apps.tg_bot.handlers import BOT_COMMANDS
    commands_names = [c.command for c in BOT_COMMANDS]
    if "skip" in commands_names or "mystatus" in commands_names:
        print(f"❌ Removed commands still in menu: {commands_names}")
    else:
        print("✅ Removed commands gone from menu")

    # 3. Check for fake data sites
    print("[3/3] Checking for remaining fake data sites...")
    import apps.tg_bot.handlers as handlers
    if hasattr(handlers, "_get_sample_transactions"):
        print("❌ _get_sample_transactions still exists in handlers")
    else:
        print("✅ _get_sample_transactions deleted")

    print("\n--- Logic Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(test_logic())
