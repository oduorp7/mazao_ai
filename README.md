# Mazao AI — The Smart Kenyan Business Manager

Mazao AI is a sovereign-grade Telegram AI Bot designed to automate tax compliance (KRA VAT/PAYE), financial reporting, and utility management for businesses and individuals in Kenya.

## 🚀 Key Features

*   **Real-time M-Pesa Tracking**: Automatic payment alerts via Africa's Talking C2B Bridge.
*   **AI Financial Reporting**: Forward your M-Pesa statements for instant profit/loss analysis and tax estimates.
*   **Tax Compliance**: Automated reminders for VAT (20th), PAYE (9th), and annual returns.
*   **Utility Predictions**: Track Electricity (Token) depletion and Fuliza loan due dates.
*   **Contextual Command Menus**: Dynamic command lists based on user profile and status-aware settings (e.g., current Home Type/Lang visible on buttons).
*   **Dynamic Switcher**: Inline keyboard-based switcher with checkmark indicators and instant projection feedback.
*   **Multi-Provider AI Engine**: Resilient "brain" supporting Anthropic (Claude) and OpenRouter (DeepSeek-V3) with automatic fallback.
*   **Real-time M-Pesa (Daraja C2B)**: Native Safaricom integration (Sandbox live, Production pending Paybill approval).
*   **Multi-language**: Seamless switching between English and Swahili.
*   **Robust Trial Management**: Automated 14-day trials for all new users.

## �️ Architecture & Knowledge Base

Mazao AI follows **FAANG/Enterprise-grade** documentation standards. All technical and strategic artifacts are consolidated in the `/docs` directory.

### 📚 Documentation Map
- **[Strategy & Roadmap](docs/strategy/ROADMAP.md)**: Product vision, growth milestones, and first-customer outreach guide.
- **[Architecture](docs/architecture/LLM_FACTORY.md)**: Technical design of the Multi-LLM factory, fallback logic, and data flow.
- **[Governance & Protocols](docs/governance/PROTOCOL.json)**: Engineering rules, security protocols, and Phase-Gate requirements.
- **[Legal & Compliance](docs/legal/PRIVACY_POLICY.md)**: Data protection (ODPC), privacy disclosures, and KRA/ODPC compliance.
- **[Engineering Contract](docs/governance/CONTRACT.md)**: Service Level Agreements (SLA) and development standards.
- [x] **Regression & Certification**: System-wide protection tiers, deploy gates, and Tier A flow invariants.
- [x] **Regression & Certification**: System-wide protection tiers, deploy gates, and Tier A flow invariants.
- **[Subscription Policy](docs/strategy/SUBSCRIPTION_POLICY.md)**: Tiered access gating:
    - **Free (KES 0)**: Manual tracking & basic dashboard.
    - **Core (KES 149/mo)**: Proactive alerts & utility projections.
    - **Pro (KES 399/mo)**: AI Insights, Tips, and Anomaly Detection.
    - **Trial (7 Days)**: Full **PRO** access for all new users.

---
| `/till` | Register M-Pesa Till | Business | Any |
| `/vat` | VAT liability check | Business | Any |
| `/kra` | KRA obligation check | Business | Any |
| `/statement` | View parsed statement | Business | Any |
| `/tokens` | Log electricity units | Individual | Any |
| `/fuliza` | Log Fuliza balance | Individual | Any |
| `/subscribe` | Add bill reminder | Individual | Any |
| `/subscriptions` | Manage recurring payments | Individual | Any |
| `/upgrade` | Upgrade to paid plan | Any | Free |
| `/refer` | Refer a friend & get discount | Any | Any |
| `/settings` | Edit your profile | Any | Any |
| `/language` | Change language (EN/SW) | Any | Any |
| `/privacy` | Read Privacy Policy | Any | Any |
| `/feedback` | Send feedback/report issue | Any | Any |
| `/stop` | Pause daily alerts | Any | Any |
| `/resume` | Resume daily alerts | Any | Any |
| `/admin` | Admin Dashboard | Admin | N/A |

## 📡 Utility Alert Lifecycle

Mazao AI implements a unified, stateful alerting system for Electricity (Tokens) and Gas depletion to prevent notification fatigue while ensuring critical urgency.

| Utility | Thresholds | Lifecycle | Dedup Logic |
|---------|------------|-----------|-------------|
| **Electricity** | 7d, 3d, 1d | Proactive | 7d/3d: Once per refill; 1d: Daily repeat |
| **Gas** | 7d, 3d, 1d | Proactive | 7d/3d: Once per refill; 1d: Daily repeat |

**Rules of Engagement:**
1.  **Confidence Gating**: Proactive alerts are suppressed if confidence is "Grid baseline" (0-1 history entries) to avoid low-accuracy noise.
2.  **Durable State**: 7-day and 3-day alerts are recorded in the database and will not refire until a new refill row is detected.
3.  **Critical Urgency**: 1-day alerts bypass deduplication and fire daily until a refill is logged.
4.  **Universal Stop-Gate**: All automated alerts (Utilities, Fuliza, Subscriptions) strictly respect the user `/stop` command. Paused or lapsed accounts receive zero scheduled messages.
5.  **Automated Tier Lifecycle**: M-Pesa payments of KES 149 and 399 automatically activate **Core** and **Pro** tiers for 30 days. Expired subscriptions are automatically downgraded to the **Free** tier.

### 📅 Backfill & Historical Learning

Mazao AI supports backfilling historical utility data (past token purchases or gas refills) to accelerate model learning without destabilizing current predictions.

- **Chronological Stability**: The system automatically re-sorts historical entries by date, allowing users to add data out of order.
- **Recency Weighting**: Newer intervals carry significantly more weight than older ones. Current forecasts are always anchored to the user's most recent behavior.
- **Improved Confidence**: Adding historical data increases the sample size (`n`), allowing the system to graduate from "Grid baseline" to high-accuracy "Personal Average" faster.
- **Alert Anchoring**: Proactive alerts are always calculated relative to the most recent entry in time. Backfilled data improves the *rate* but does not trigger "phantom" historical reminders.

---

## 📡 M-Pesa Daraja C2B Integration (Sprint 5)

Mazao AI now supports native Safaricom Daraja C2B integration for real-time transaction monitoring.

### Current State: **Sandbox Live**
- **OAuth2 Token Manager**: Implemented with caching (3600s).
- **C2B RegisterURL**: Functional, points to Fly.io validation/confirmation endpoints.
- **Validation Logic**: Automated "Accepted" response (ResultCode 0) for all sandbox transactions.
- **Confirmation Logic**: Parsed and logged to `live_transactions` table for reconciliation.

### Production Migration Requirements
Once the official Safaricom Paybill/Till is approved:
1.  **Update Secrets**: 
    - `DARAJA_CONSUMER_KEY` & `DARAJA_CONSUMER_SECRET` (Production versions)
    - `DARAJA_SHORTCODE` (Your Paybill number)
    - `DARAJA_ENV` set to `production`
2.  **Rerun Registration**: The bot will automatically attempt to register the URLs on the next startup.

## 📦 Production Setup (Fly.io)

1.  **Environment**: Clone `.env.example` to `.env` and fill in:
    *   `TELEGRAM_BOT_TOKEN`
    *   `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`
    *   `ANTHROPIC_API_KEY`
    *   `FLY_APP_URL` (Required for Webhooks)
    *   `INTASEND_PUBLISHABLE_KEY` / `INTASEND_SECRET_KEY` / `INTASEND_WEBHOOK_CHALLENGE`
2.  **Database**: Run the contents of `apps/tg_bot/schema.sql` in the Supabase SQL Editor.
3.  **Deploy**: `fly deploy` (Port 8080 exposed for health checks & webhooks).

## 🛡️ Production Readiness (Phase 10 Checklist)

- [x] **Environment Variables**: All 11 confirmed set in Fly.io (including `INTASEND_*`, `FLY_APP_URL`, and `ADMIN_TELEGRAM_ID`).
- [x] **Stability**: Command handlers hardened for edge cases (non-numeric units, pre-onboarding checks).
- [x] **Feedback Loop**: Deliverable via `/feedback` command; auto-forwards to Chief Engineer.
- [x] **Organic Growth**: Referral program active via `/refer` (20% discount reward).
- [x] **Admin Visibility**: Daily digest at 8:00 AM EAT and invisible `/admin` dashboard.
- [x] **Command Menu**: Progressive disclosure implemented via `apps/tg_bot/menu.py`.
- [x] **Daraja Bridge**: Native C2B integration (Sandbox Verified).
- [ ] **ODPC Registration**: [ACTION REQUIRED] Data Controller registration pending.
- [ ] **Safaricom Paybill**: [ACTION REQUIRED] Application for production paybill pending.
- [ ] **Privacy Policy URL**: [ACTION REQUIRED] Hosted URL pending (currently bot-only).

## 🚀 Activation & Onboarding

### First Customer Acquisition Guide
**What to say to a business owner:**
> "Hey [Name], I'm testing a new tool called Mazao AI that automates your M-Pesa bookkeeping and tax estimates. It's built for Kenyan SMEs. You just forward your statements or register your Till, and it handles the rest. Want to try it? I can set you up as a Founding Member (KES 300/mo instead of 500)."

**The Demo:**
1. Open [@MazaoAIBot](https://t.me/MazaoAIBot).
2. Type `/start` and select "Business Owner".
3. Forward a recent M-Pesa statement SMS.
4. Type `/report` to see the AI analysis.
5. Register a Till via `/till` to see real-time alerts.

## ⚠️ Known Limitations (April 2026)
- **Daraja Approval**: Real-time feed via direct Daraja integration is pending Paybill approval. Currently uses Africa's Talking / Intasend bridge.
- **Statement Parsing**: Supports standard M-Pesa business and individual statement formats. Custom bank formats pending.
- **Payments**: STK Push currently runs in Intasend Sandbox mode.

---

## 💻 Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the bot
python -m apps.tg_bot.bot
```

## 🛡️ Architecture
*   **Agent**: Anthropic Claude-3.5-Sonnet (via standard pipeline).
*   **Database**: Supabase (PostgreSQL with RLS).
*   **Payments**: Provider-agnostic bridge (Africa's Talking -> Daraja ready).
*   **Deployment**: Fly.io (Containerized, auto-health checks).

---

## 🛡️ System Certification: **STABLE**
**Current State**: Phase 15 Hardening Complete. 
**Directive**: WAITING FOR CHIEF ENGINEER / CUSTOMER FEEDBACK.
**Stability**: Certified Sovereign-Grade. No further unsolicited changes permitted.
