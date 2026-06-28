# Cloudflare Edge Migration Runbook

## Purpose

This runbook describes the safe first step toward Cloudflare hosting for Mazao AI.
It keeps Fly.io as the running Python bot, scheduler, and payment-processing origin,
while Cloudflare Workers serves `mazao.codegxtechnologies.org` as a free edge layer.

This is intentionally additive. It does not change `bot.py`, `fly.toml`, the Dockerfile,
or the current Fly deployment path.

## Current split

- Fly.io remains responsible for the always-on Python process:
  - Telegram polling
  - APScheduler jobs
  - payment webhook processing
  - `/health`
- Cloudflare Workers handles the public subdomain:
  - `https://mazao.codegxtechnologies.org/`
  - `GET /health`
  - `POST /payments/webhook`
  - `POST /mpesa/c2b`
  - `POST /mpesa/c2b/validation`
  - `POST /mpesa/c2b/confirmation`
  - `POST /mpesa/stk/callback`

## Why this avoids production risk

The Worker is a proxy in front of the existing Fly origin. If Cloudflare has a problem,
payment providers can be pointed back to `https://mazao-ai.fly.dev` without changing the
Python app.

The Worker only proxies explicit paths. Unknown paths return `404`, which avoids making
the whole Fly app surface public through the new domain by accident.

## Subdomain safety

`mazao.codegxtechnologies.org` will not conflict with other apps under
`codegxtechnologies.org` unless another Cloudflare Worker, DNS record, Page, Tunnel, or
SaaS mapping already uses the exact same hostname.

Safe examples that can coexist:

- `app.codegxtechnologies.org`
- `api.codegxtechnologies.org`
- `www.codegxtechnologies.org`
- `mazao.codegxtechnologies.org`

Avoid using a broad wildcard route like `*.codegxtechnologies.org/*` for this Worker,
because that could intercept unrelated subdomain apps.

## Deploy

From the Worker folder:

```bash
cd cloudflare/mazao-edge-worker
npx wrangler deploy
```

The Worker config uses a Cloudflare Worker Custom Domain:

```toml
[[routes]]
pattern = "mazao.codegxtechnologies.org"
custom_domain = true
```

Cloudflare creates the DNS record and certificate for that exact hostname. If a DNS
record for `mazao.codegxtechnologies.org` already exists, remove or rename it before
attaching the Custom Domain.

## Verify

After deployment:

```bash
curl https://mazao.codegxtechnologies.org/
curl https://mazao.codegxtechnologies.org/health
```

Expected behavior:

- `/` returns a JSON response from Cloudflare edge.
- `/health` is proxied to the Fly origin and should return the same health JSON as
  `https://mazao-ai.fly.dev/health`.

## Next migration phase

After this edge layer is stable, the next production-safe migration is:

1. Convert Telegram from polling to Telegram webhooks.
2. Move payment webhook handlers from Fly into a Worker-native handler or queue.
3. Replace APScheduler with a consolidated Cloudflare Cron dispatcher.
4. Keep Supabase as the source of truth.
5. Retire Fly only after webhook, scheduler, retry, and idempotency checks pass in production.
