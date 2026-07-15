# WhereIt'sCheap (Mazao AI Integration) - Roadmap

This roadmap outlines the phased integration of the "WhereIt'sCheap" smart shopping module into the native **Mazao AI** Python ecosystem. The focus is on strict adherence to the **Zero Token Waste** policy and leveraging the existing B2C infrastructure (Telegram, Supabase, Daraja).

## Phase 1: Foundation & Zero-Token Caching
* **Objective:** Establish the routing and database layers without involving any LLM or Agent execution.
* **Tasks:**
  - [ ] Create the `price_cache` table in the existing Mazao AI Supabase instance.
  - [ ] Implement a lightweight text/regex handler in `apps/tg_bot/handlers.py` (e.g., listening for `/compare [item]`).
  - [ ] Wire the handler to query Supabase directly for active cache hits.
  - [ ] Return cached prices instantly to the user (Token Cost = 0).

## Phase 2: Agentic Integration (Cache Miss Handler)
* **Objective:** Connect the "Brain" to handle queries that are not in the Supabase cache.
* **Tasks:**
  - [ ] Implement an async Python service using `httpx` to trigger the **Manus AI** (or equivalent OpenAI browser agent) API.
  - [ ] Structure the prompt payload to instruct the agent to navigate Carrefour/Naivas and extract prices.
  - [ ] Parse the returned JSON from the agent and insert it into the Supabase `price_cache` with a TTL (Time-To-Live).
  - [ ] Ensure the architecture remains **Vendor Agnostic**, allowing simple hot-swapping between Manus and OpenAI based on API costs and reliability.

## Phase 3: Monetization & B2C Scaling
* **Objective:** Leverage Mazao AI's existing payment infrastructure to gatekeep advanced features.
* **Tasks:**
  - [ ] Hook the shopping module into the existing `apps/payments` (Daraja/Intasend) billing flags.
  - [ ] Define the "Free Tier" (Users only get access to cached prices).
  - [ ] Define the "Pro Tier" (Users can force a live agentic search overriding the cache).
  - [ ] Stress test the direct Telegram webhook connection (bypassing n8n/Publora) to ensure concurrent B2C scalability.

## Phase 4: Advanced Shopping Utilities
* **Objective:** Evolve from a simple price lookup to a personal financial assistant.
* **Tasks:**
  - [ ] **Price Drop Alerts:** Automated background jobs (`apscheduler`) that periodically invoke the agent for popular items and notify Pro users if prices drop.
  - [ ] **Cart Optimization:** Allow users to submit a list of 10 items, and the bot calculates the cheapest combination across multiple supermarkets, factoring in delivery fees.
