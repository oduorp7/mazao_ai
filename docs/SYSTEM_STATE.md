# Mazao AI System State & Architecture

## System Architecture
Mazao AI is a **Standalone Telegram Bot** designed for Kenyan SME bookkeeping, integrating **LangGraph** for intelligent report generation.

### 1. Ingestion Layer (`apps/tg_bot/`)
- **`bot.py`**: Telegram entry point using `python-telegram-bot`.
- **`handlers.py`**: Stateless command routing and intent parsing.
- **`mpesa_parser.py`**: Unified parsing engine (CSV, PDF, SMS) for M-Pesa records.
- **`db.py`**: Supabase/PostgreSQL interface.

### 2. Intelligence Layer (`apps/agent/`)
- **`pipeline.py`**: LangGraph workflow orchestrating data aggregation and reporting.
- **`nodes.py`**: Functional nodes for VAT computation, KRA obligations, and LLM report generation.
- **`state.py`**: Shared `AgentState` schema across the graph.
- **`llm.py`**: Provider-agnostic LLM factory (Anthropic/OpenRouter).

## RPEK Governance Loop
System continuity is enforced via the **RPEK-LITE** governance model:
1. **Task Definition**: JSON definition in `projects/mazao_ai/tasks/`.
2. **Build**: `build_prompt.py` compiles task context + adapter context + base kernel.
3. **Execution**: Executor (Cascade) operates strictly within `scope_lock`.
4. **Report**: Machine-readable JSON Completion Report ensures verifiable progress.

## Known Issues & Drift
- **Schema Drift**: `live_transactions` table in Supabase lacks `tenant_id`. Handlers use `try-except` fallback to statement-only data.
- **AI Insights Degraded**: LLM nodes may fallback to deterministic metrics during provider downtime/timeout.
- **Recomputation Boundary**: `/report` triggers recomputation only if a newer statement is detected; otherwise uses cached AI reports.
