# Mazao AI — The Smart Kenyan Business Manager

Mazao AI is a sovereign-grade Telegram AI Bot designed to automate tax compliance (KRA VAT/PAYE), financial reporting, and utility management for businesses and individuals in Kenya.

## 🚀 Key Features

*   **Real-time M-Pesa Tracking**: Automatic payment alerts via Africa's Talking C2B Bridge.
*   **AI Financial Reporting**: Forward your M-Pesa statements for instant profit/loss analysis and tax estimates.
*   **Tax Compliance**: Automated reminders for VAT (20th), PAYE (9th), and annual returns.
*   **Utility Predictions**: Track Electricity (Token) depletion and Fuliza loan due dates.
*   **Contextual Command Menus**: Dynamic command lists based on user profile (Business vs Individual).
*   **Multi-language**: Seamless switching between English and Swahili.
*   **Robust Trial Management**: Automated 14-day trials for all new users.

## 🛠 Active Commands (15)

| Command | Description |
|---------|-------------|
| `/start` | Profile setup (Business or Individual) |
| `/report` | Generate AI Profit/Loss & Tax report |
| `/status` | Unified Business Dashboard (Live feed + Tax) |
| `/mystatus` | Personal obligation tracker |
| `/statement` | View latest statement summary |
| `/vat` | Detailed VAT liability projection |
| `/kra` | Full tax obligation calendar |
| `/till` | Register M-Pesa Till for live alerts |
| `/tokens` | Log electricity units (Predict depletion) |
| `/fuliza` | Log Fuliza loan & due date |
| `/subscribe` | Add monthly business bills |
| `/subscriptions` | Manage recurring payments |
| `/language` | Switch English/Swahili |
| `/stop` | Pause daily alerts |
| `/resume` | Resume daily alerts |

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
