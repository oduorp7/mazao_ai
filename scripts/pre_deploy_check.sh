#!/bin/bash
set -e

echo "🚀 Running Pre-Deploy Checks..."

# GATE 1: Static Analysis
echo "🔍 Gate 1: Running Ruff (Critical F errors)..."
if ! python -m ruff check apps/ --select F --ignore F401; then
    echo "❌ Gate 1 Failed: Ruff found critical errors."
    exit 1
fi

echo "🔍 Gate 1: Running Pyflakes (Critical errors)..."
# Filter out common unused import noise for this surgical gate
if ! python -m pyflakes apps/tg_bot/bot.py | grep -v "imported but unused"; then
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        echo "❌ Gate 1 Failed: Pyflakes found critical errors in bot.py."
        exit 1
    fi
fi

# GATE 2: Import Test
echo "📦 Gate 2: Confirming imports load..."
if ! python -c 'import sys; sys.path.insert(0, "."); import importlib.util; spec = importlib.util.spec_from_file_location("bot", "apps/tg_bot/bot.py"); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); print("✅ Bot imports loaded successfully.")'; then
    echo "❌ Gate 2 Failed: bot.py failed to load (Import/Syntax Error)."
    exit 1
fi

echo "✅ All pre-deploy gates passed!"
exit 0
