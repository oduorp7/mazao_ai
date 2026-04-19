# Mazao AI — Strategic Roadmap & Architecture Guide

This document distills the core observations and strategic principles to guide the evolution of Mazao AI from a "bookkeeper" to a "Financial Awareness + Prediction Layer for Kenyan Life."

## 1. The Core Vision: "Autopilot for Kenyan Life"

Mazao AI is not just accounting software; it is a system that **predicts and prevents everyday financial stress.** Its value lies in solving real-world consequences (penalties, service disruptions, out-of-stock essentials).

## 2. The Three-Engine Architecture

| Engine | Focus | User Value | Data Source |
|:---|:---|:---|:---|
| **Compliance** | KRA Rules | Avoid Penalties | Rules + PIN |
| **Accounting-Lite** | M-Pesa Flow | Cashflow Visibility | M-Pesa statements/SMS |
| **Prediction** | Utility Consumption | Prevent Disruption | Usage trends (Tokens/Gas) |

---

## 3. Implementation Principles

### Layering, Not Merging
Do not force full accounting at the start. SMEs will drop off.
- **Start with Compliance**: Low friction, high urgency.
- **Introduce Visibility**: Progressive onboarding for M-Pesa tracking.
- **Unlock Insights**: Predictive alerts as data accumulates.

### Estimates > Perfection
Imperfect data with clear "Estimate" labeling is better than no data.
- Use M-Pesa inflows for revenue.
- Use rough heuristics for expense categories.
- Use ranges for predictions (e.g., "Electricity will last 2-4 days").

---

## 4. Phase-Specific Roadmap

### Phase 1: The Trust Foundation (Completed)
- [x] KRA Deadline Engine (VAT, PAYE, NSSF)
- [x] Basic M-Pesa Statement Parsing (CSV)
- [x] Individual vs. Business Onboarding
- [x] Rule-based "Standard Mode" fallback

### Phase 2: The Persistence Layer (Immediate Next)
- **Feature**: **Electricity Token Tracker & Prediction**
  - Input: Token amount + past history.
  - Logic: `remaining_units / avg_daily_usage`.
- **Feature**: **Gas Depletion Predictor**
  - Heuristics based on cylinder size (6kg/13kg) + household size.
- **Workflow**: Automated SMS parsing (forwarding) to feed the engine.

### Phase 3: The Insight Layer (Premium)
- **Feature**: **Cashflow Prediction**
  - "At current spending, you'll need Fuliza in 3 days."
- **Feature**: **Smart Reconciliation**
  - AI-assisted categorization with high confidence thresholds.
- **Feature**: **Credit Readiness Dashboard**
  - Behavioral insights formatted for potential lending partners.

---

## 5. Data & UX Strategy

### Low-Friction Onboarding (The 2-Minute Rule)
- Step 1: User Type (Business vs. Individual).
- Step 2: Instant "Upcoming Deadlines" view (No KRA PIN required initially).
- Step 3: Optional PIN/Till entry for "Deeper Visibility."

### Data Acquisition
- Encourage forwarding M-Pesa and KPLC SMS messages directly to the bot.
- Use `mpesa_parser.py` as the central ingestion hub for all formats.

---

## 6. Your Unfair Advantage
Most accounting tools focus on reports. Mazao AI combines **money + real-life consumption + deadlines**.

This is not just bookkeeping software. It is a **financial awareness + prediction layer for everyday Kenyan life**.
