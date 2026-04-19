# Mazao AI — Strategic Roadmap & Architecture Guide
Version 1.0  |  April 2026

This document is the **definitive Source of Truth** for the Mazao AI platform. It distills the core vision, tactical roadmap, and operational requirements to transform Mazao AI into the financial nervous system of Kenya.

---

## 1. Executive Summary: "Predict. Prevent. Protect."

Mazao AI is Kenya’s first unified financial intelligence platform built natively on M-Pesa, KRA, and SHA infrastructure. We provide a predictive financial autopilot that solves real-world consequences: **penalties, service disruptions, and cash shortfalls.**

> [!IMPORTANT]
> **The Core Vision**: We aren't building "bookkeeping software." We are building a **Financial Awareness + Prediction Layer** for everyday Kenyan life.

---

## 2. Product Philosophy

### Engine 1: Compliance (Acquisition)
Built on fear of penalties. It must be simple, instant, and automated.
- **Value**: "Avoid KRA/SHA fines."
- **Onboarding Target**: < 2 minutes.

### Engine 2: Cash Awareness (Retention)
Built on daily habit. Uses M-Pesa statements and live feeds to show "where the money goes."
- **Value**: "Know your profit/spend instantly."

### Engine 3: Life Prediction (Virality)
The "Wow" factor. Predicts when electricity tokens, gas, or cash will run out.
- **Value**: "Never be caught off-guard."

---

## 3. Implementation Principles

- **Layering, Not Merging**: Lead with low-friction compliance. Layer accounting and predictions progressively.
- **Estimates Over Perfection**: Standard Mode (Estimates) is better than no data. Clearly label imperfect data as "Estimates."
- **Minimal Data footprint**: Collect only operationally necessary, low-sensitivity data. No KRA PINs required for first-value delivery.

---

## 4. User Types & Onboarding

| User Type | Profile | Key Priority |
|:---|:---|:---|
| **SME Business Owner** | Small/Medium shop owners. | Tax compliance & Profit visibility. |
| **Employed Individual** | Formal sector employees. | SHA/NSSF tracking & Monthly spend logs. |
| **Household Manager** | Residential power/gas users. | Utility prediction & Bill reminders. |

---

## 5. Detailed Roadmap (Sprints 1–6)

| Sprint | Timeline | Deliverables | Definition of Done |
|:---|:---|:---|:---|
| **Sprint 1** | **Completed** | Telegram bot live, Onboarding flow, Supabase DB. | Bot responds to `/start`. |
| **Sprint 2** | **In Progress** | M-Pesa Statement Parser (CSV/PDF), Individual Mode, SHA/NSSF engine. | Real statement produces correct numbers. |
| **Sprint 3** | **Completed** | **Utility Prediction (KPLC Tokens)**, Fuliza trackers, Logic Hardening. | Electricity depletion accurate within 2 days. |
| **Sprint 4** | Week 7–8 | Cooking gas estimator, Water bill tracker, Safaricom Paybill application. | Paybill application submitted for production. |
| **Sprint 5** | Week 9–12 | **Daraja C2B Webhook Integration**. Real-time transaction feed replaces file upload. | Live transactions reach bot in < 30s. |
| **Sprint 6** | Month 4–6 | Regional Expansion (Uganda/Tanzania), Swahili support, Credit scoring layer. | First paying customer outside Kenya. |

---

## 6. Monetisation Tiers

| Feature | **Msingi** (Free) | **Mtu Wenyewe** (K500) | **Biashara** (K2,500) |
|:---|:---|:---|:---|
| **Target** | Public / Entry | Individual | SME Owner |
| **KRA Reminders** | Basic | Personalised | Full + Penalty Estimates |
| **M-Pesa Reports** | No | Weekly Spend | **Daily (7:00 AM)** |
| **Utility Prediction** | No | Yes | Yes |
| **AI Insights** | No | No | **Claude 3.5 Sonnet Reports** |

---

## 7. Legal & Operational Requirements

### Pre-Launch Checklist
1. **ODPC Registration**: Register as a Data Controller with the Office of the Data Protection Commissioner Kenya ([odpc.go.ke](https://odpc.go.ke)).
2. **Privacy Policy**: Plain-language policy detailing what we collect and why.
3. **Safaricom Paybill**: Apply for a business Paybill to enable Daraja production access.
4. **Daraja Production Support**: Finalize verification for C2B live feeds.

---

## 8. Current Action Items (Urgent)

- [x] **Top up Anthropic Billing**: Unlock "Premium Mode" for Claude AI reports.
- [x] **Deploy to Fly.io**: Transfer from Local Workspace to 24/7 cloud hosting.
- [x] **Sprint 3 Execution**: Complete Utility Prediction & Bot Hardening (Done).
- [ ] **Sprint 4 Planning**: Cooking gas estimator & Water bill tracker.
- [ ] **Publish Privacy Policy**: Notion/Markdown page linked to bot greeting.

---
**Mazao AI** — *Predict. Prevent. Protect.*
