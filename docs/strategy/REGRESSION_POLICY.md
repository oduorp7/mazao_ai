# Mazao AI Regression & Certification Policy

This document defines the system-wide regression protection model, flow tiers, and deployment gate policies to ensure sovereign-grade stability.

## 🏗️ Criticality Tiers

All system flows are categorized into three tiers of importance. Deployment gates enforce protection based on these tiers.

### Tier A: Core & Critical (BLOCKING)
Failures in these flows **MUST** block the deployment pipeline.
- **Electricity Ingestion**: Full KPLC SMS parsing and data logging.
- **Gas Ingestion**: Manual refill entry and chronological sorting.
- **Projection Math**: Daily consumption rate and depletion date algorithms.
- **Deduplication**: Multi-entry protection within the same billing cycle.
- **DB Persistence**: Atomic writes to Supabase for all utility records.

### Tier B: Support & Visibility (NON-BLOCKING SIGNAL)
Failures should be addressed immediately but do not necessarily block emergency deploys.
- **Dashboards**: `/status`, `/electricity`, and `/gas` views.
- **Onboarding**: Registration and profile configuration.
- **Payments**: Subscription upgrades and renewal tracking.
- **Proactive Alerts**: Scheduled 7d/3d/1d depletion reminders.

### Tier C: Optional & Engagement (NON-BLOCKING)
These features are designed for "Safe Degradation."
- **AI Tips**: LLM-generated contextual engagement nudges.
- **Optional Enrichments**: Non-critical UI flourishes.

---

## 🛡️ Deployment Gate Policy (WWFD Standard)

1.  **Gate 1 (Static Analysis)**: Syntax and basic lint errors block deploy.
2.  **Gate 2 (Load Test)**: Import errors (broken dependencies) block deploy.
3.  **Gate 3 (Tier A Certification)**: Regression failures in Core Flows block deploy.
4.  **Silent Fail Protocol**: Optional features (Tier C) must be isolated in `try...except` blocks with strict timeouts. The absence of a Tier C feature **MUST NOT** be treated as a deployment failure.

---

## 🧪 Certification Harnesses

- **`test_estimator_regression.py`**: Validates mathematical invariants and parsing edge cases.
- **`certify_utility_ingestion_smoke.py`**: End-to-end simulation of user ingestion paths to verify handler integrity.

## 🚀 Post-Deploy Verification
After every production deploy to Fly.io, the operator should:
1.  Verify `/status` command returns correctly.
2.  Log a test Token or Gas entry (using a test account) to verify DB write-success.
