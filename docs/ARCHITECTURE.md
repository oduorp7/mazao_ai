# Mazao AI System Architecture

## High-Level Flow
1. **User Ingestion**: Users interact via Telegram Bot (`apps/tg_bot/bot.py`).
2. **Data Processing**: M-Pesa statements are parsed via `apps/tg_bot/mpesa_parser.py` and stored in Supabase.
3. **Intelligence Pipeline**: `/report` triggers a LangGraph workflow (`apps/agent/pipeline.py`).
4. **State Management**: Data flows through `AgentState` (`apps/agent/state.py`) across specialized nodes (`nodes.py`).
5. **Output**: Bilingual (English/Swahili) reports are delivered back to the user via Telegram.

## Component Map
- **Bot Layer**: Handles sessions, commands, and file uploads.
- **Agent Layer**: Handles business logic, VAT estimates, and LLM-driven insights.
- **Data Layer**: Supabase (PostgreSQL) for persistence; `live_transactions` for real-time feeds.

## Deployment
- **Platform**: Fly.io.
- **Orchestration**: `fly.toml` manages scaling and health checks.
- **Secrets**: Managed via Fly Secrets (e.g., `OPENROUTER_API_KEY`).
