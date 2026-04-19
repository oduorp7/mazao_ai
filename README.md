# Mazao AI — Financial Operating System for Kenyan SMEs

**Mazao AI** is an agentic SaaS platform designed to automate bookkeeping and tax compliance for small and medium enterprises in Kenya. By bridging the gap between M-Pesa transactions and KRA iTax obligations, Mazao AI empowers business owners to focus on growth while the AI handles the paperwork.

## 🌟 Vision
To be the default financial intelligence layer for every SME in East Africa, starting with Kenya.

## 🗺️ Documentation & Strategy
- **[Strategic Roadmap](STRATEGIC_ROADMAP.md)**: Our 6-sprint mission to build the "Financial Nervous System" of Kenya.
- **[Privacy Policy](PRIVACY_POLICY.md)**: ODPC-compliant data management principles.

## 🏗️ Technical Architecture
Mazao AI uses a "High-Assurance" architecture designed for precision and reliability:

- **Agent Engine**: Built with **LangGraph**, utilizing a custom state machine for deterministic transaction processing.
- **AI Core**: Powered by **Claude 3.5 Sonnet** (via Anthropic) for surgical data extraction.
- **Persistence**: **Supabase (PostgreSQL)** with strict Row Level Security (RLS).
- **Interface**: Asynchronous **Telegram Bot** featuring multi-step onboarding and automated daily reporting.

## 🚀 Deployment Status: PRODUCTION READY
The platform is optimized for cloud deployment on **Railway.app**.

### Local Startup
1. `pip install -r requirements.txt`
2. Create `.env` from the provided template.
3. `python apps/tg_bot/bot.py`

### Cloud Deployment (Fly.io)
1. Link your GitHub repository to Fly.io or use the Fly CLI.
2. The `fly.toml` and `Dockerfile` are already configured for a non-web worker bot.
3. Use `fly secrets set` to add your `.env` variables to the cloud.
4. Run `fly deploy`.

---
*Built for the hustle. Optimized for the harvest.*
