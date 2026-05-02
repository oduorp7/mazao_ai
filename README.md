# Mazao AI — Practical Business Automation for Kenya

Mazao AI is a Telegram-based automation tool for Kenyan businesses and individuals. It streamlines tax compliance, financial reporting, and utility management, with a focus on reliability, transparency, and local context.

## Core Features

- **M-Pesa Integration:** Real-time tracking and categorization of business and personal transactions (Daraja, Intasend supported).
- **Automated Tax Reminders:** VAT, PAYE, and annual return alerts based on your actual transaction data.
- **Financial Reporting:** Upload M-Pesa statements for instant profit/loss, VAT, and PAYE estimates.
- **Utility Monitoring:** Track electricity token usage and Fuliza loan deadlines.
- **Multi-language:** English and Swahili support.
- **Tiered Access:**
  - Free: Manual tracking
  - Core: Proactive alerts, utility tracking (KES 149/mo)
  - Pro: AI-powered tips, anomaly detection (KES 399/mo)
  - 7-day free trial for all new users

## How It Works

1. **Start the Bot:**
    - Run python apps/tg_bot/bot.py after setting up your environment variables (see .env.example).
2. **Register:**
    - Onboard via Telegram, set your business details, and connect your M-Pesa till or upload statements.
3. **Automate:**
    - Receive daily reports, tax reminders, and actionable insights directly in Telegram.

## Recent Developments

- Improved M-Pesa parsing and categorization (supports more statement formats)
- Enhanced AI fallback logic for financial tips (Anthropic, OpenRouter)
- Streamlined onboarding and trial management
- Expanded utility tracking (electricity, Fuliza)
- More robust Supabase integration for data reliability
- Native Daraja C2B integration (production-ready, pending Paybill approval)

## Documentation

All technical, legal, and strategic documentation is in the docs/ directory:
- Architecture: docs/architecture/LLM_FACTORY.md
- Roadmap: docs/strategy/ROADMAP.md
- Protocols & Compliance: docs/governance/PROTOCOL.json, docs/legal/PRIVACY_POLICY.md

## Production Setup (Fly.io)

1. **Environment**: Clone .env.example to .env and fill in:
   - TELEGRAM_BOT_TOKEN
   - SUPABASE_URL / SUPABASE_SERVICE_KEY
   - ANTHROPIC_API_KEY (or OPENROUTER_API_KEY)
   - FLY_APP_URL
   - Payment provider keys (Intasend, Daraja - optional)

2. **Database**: Run pps/tg_bot/schema.sql in Supabase SQL Editor.

3. **Deploy**: ly deploy (Port 8080 for webhooks).

## Local Development

\\\ash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Fill in your credentials

# Run the bot
python apps/tg_bot/bot.py
\\\

## Project Structure

\\\
apps/
├── agent/          # AI pipeline (LangGraph, LLM selection, state)
├── payments/       # Payment provider integrations (Daraja, Intasend)
└── tg_bot/         # Telegram bot logic (handlers, scheduler, database)
docs/               # Technical, legal, strategy documentation
tools/              # Utilities and helpers
\\\

## System Status

- **Current Phase**: Phase 19 Daraja Production Readiness Complete
- **Status**: Stable & Certified (All 38 smoke tests passing)
- **Next Step**: Await DARAJA_PASSKEY for Phase 19E Live Activation

## Contributing

Contributions are welcome. Please see the roadmap and open issues for areas to help.

---

## License

MIT

## Authors & Maintainers

**Developed and maintained by:** Peter O. Oluoch — Backend Engineer & AI Architect/Engineer

## Support

For issues, feature requests, or feedback, please use the /feedback command in the bot or open an issue on GitHub.
