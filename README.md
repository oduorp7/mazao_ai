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
3. `python apps/telegram/bot.py`

### Cloud Deployment (Railway)
1. Link your GitHub repository to Railway.
2. Railway will automatically detect the `Procfile` and `runtime.txt`.
3. Add your `.env` variables to the Railway Dashboard.
4. Deploy.

---
*Built for the hustle. Optimized for the harvest.*
