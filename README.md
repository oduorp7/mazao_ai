# Mazao AI — The Smart Agri-Business Manager

Mazao AI is a sovereign-grade Telegram AI Bot designed to automate tax compliance (KRA VAT/PAYE), financial reporting, and utility management for businesses and individuals in Kenya.

## 🚀 Key Features

*   **Real-time M-Pesa Tracking**: Automatic payment alerts via Africa's Talking C2B Bridge.
*   **AI Financial Reporting**: Forward your M-Pesa statements for instant profit/loss analysis and tax estimates.
*   **Tax Compliance**: Automated reminders for VAT (20th), PAYE (9th), and annual returns.
*   **Utility Predictions**: Track Electricity (Token) depletion and Fuliza loan due dates.
*   **Multi-language**: Seamless switching between English and Swahili.

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

## 🛡️ Production Readiness (Phase 9 Checklist)

- [x] **Environment Variables**: All 11 confirmed set in Fly.io (including `INTASEND_*`, `FLY_APP_URL`, and `ADMIN_TELEGRAM_ID`).
- [x] **Supabase Security**: RLS policies active on `tenants`, `live_transactions`, and `payment_requests`.
- [x] **Bot Deployment**: Running 24/7 on Fly.io (Region: `ams`), health checks passing.
- [x] **Webhook Integration**: Consolidated to POST only; registered in Intasend Sandbox.
- [x] **Privacy Policy**: Deliverable via `/privacy` command.
- [x] **Founding Member Pricing**: Active for first 50 customers.
- [ ] **ODPC Registration**: [ACTION REQUIRED] Data Controller registration pending.
- [ ] **Safaricom Paybill**: [ACTION REQUIRED] Application for production paybill pending.
- [ ] **Privacy Policy URL**: [ACTION REQUIRED] Hosted URL pending (currently bot-only).

## 🚀 Activation & Onboarding

### How to Activate Daraja (When Paybill Approved)
1. Set the following Fly.io secrets:
   - `DARAJA_CONSUMER_KEY`
   - `DARAJA_CONSUMER_SECRET`
   - `DARAJA_SHORTCODE`
2. Set `PAYMENT_PROVIDER=daraja`.
3. Run `fly deploy`.

### First Customer Onboarding Guide
1. **Welcome**: Tell them to type `/start` in the bot.
2. **Setup**: They will select "Business Owner" and enter their business name.
3. **Agreement**: They must accept the privacy policy (noted in `/start`).
4. **Trial**: They immediately get a 14-day free trial.
5. **Founding Discount**: First 10 (up to 50) get the founding member badge and KES 300/mo pricing automatically.
6. **Automation**: Mazao AI will automatically start tracking their Till once registered via `/till`.

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
