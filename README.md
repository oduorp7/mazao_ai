# Mazao AI

A Telegram bot SaaS for Kenyan SMEs that automates M-Pesa bookkeeping and KRA tax compliance.

## Structure

- `apps/agent/` — Core AI agent logic
- `apps/telegram/` — Telegram bot and integrations

## Setup

1. Create and activate a Python virtual environment in `mazao_ai/`:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r apps/agent/requirements.txt
   pip install -r apps/telegram/requirements.txt
   ```
3. Copy `.env.example` to `.env` in `apps/telegram/` and fill in secrets.

## Usage

- Run the agent: `cd apps/agent && python pipeline.py`
- Start the bot: `cd ../telegram && python bot.py`
