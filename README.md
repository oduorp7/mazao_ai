# Mazao AI — Financial Operating System for Kenyan SMEs

**Mazao AI** is an agentic SaaS platform designed to automate bookkeeping and tax compliance for small and medium enterprises in Kenya. By bridging the gap between M-Pesa transactions and KRA iTax obligations, Mazao AI empowers business owners to focus on growth while the AI handles the paperwork.

## 🌟 Vision
To be the default financial intelligence layer for every SME in East Africa, starting with Kenya.

## 🎯 Purpose
- **Automated Bookkeeping**: Instantly categorize M-Pesa C2B and B2B transactions into structured financial records.
- **Tax Compliance**: Real-time tracking of VAT, PAYE, and NSSF obligations to avoid KRA penalties.
- **Decision Support**: Intelligent daily reports and profitability audits delivered directly via Telegram.

## 🏗️ Technical Architecture
Mazao AI uses a "High-Assurance" architecture designed for precision and reliability:

- **Agent Engine**: Built with **LangGraph**, utilizing a custom state machine for deterministic transaction processing.
- **AI Core**: Powered by **Claude 3.5 Sonnet** for surgical data extraction and bookkeeping reasoning.
- **Persistence**: **Supabase (PostgreSQL)** with strict Row Level Security (RLS) for multi-tenant data isolation.
- **Interface**: Asynchronous **Telegram Bot** featuring multi-step onboarding and automated daily reporting.

## 🚀 Deployment Status: PRE-FLIGHT
We are currently in the final verification phase.
- [x] Agent Pipeline Validated (19/19 Tests Pass)
- [x] Telegram Bot Polling Active
- [x] Database Schema Defined
- [x] Watchdog Persistence Implemented

---
*Built for the hustle. Optimized for the harvest.*
