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
    *   `AT_USERNAME` / `AT_API_KEY` / `AT_SHORTCODE`
2.  **Database**: Run the contents of `apps/tg_bot/schema.sql` in the Supabase SQL Editor.
3.  **Deploy**: `fly deploy` (Port 8080 exposed for health checks & webhooks).

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
