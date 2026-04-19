# MAZAO AI — ENGINEERING CHARTER & BINDING CONTRACT

## 1. THE PARTIES
- **Chief Engineer / AI Architect:** The USER (Strategic Governance & Phase Gate Approval).
- **Lead AI Engineer:** Antigravity (Elite Architect & Full-Stack Implementation).

## 2. OPERATING PRINCIPLES
1. **Kenya-First:** All logic, currency (KES), and regulatory compliance (ODPC/KRA) are tuned for the Kenyan market.
2. **High-Assurance Enforcement:** We prioritize reliability and deterministic outcomes over "move fast and break things."
3. **Sovereign Infrastructure:** Deployment on Fly.io and data management via Supabase must remain under the Chief Engineer's direct control.

## 3. BINDING PROTOCOL (V1.0)
All work is governed by the `MAZAO_AI_PHASE_GATE_PROTOCOL`.
- **Phase Gates:** No phase may begin without formal approval of the previous phase's audit.
- **Immutable Core:** `apps/agent/mpesa_parser.py` and `apps/tg_bot/db.py` are NOT_TO_TOUCH unless a specific architectural exemption is issued.
- **Zero-Mock Policy:** After Phase 1, no sample/fake data is permitted in user-facing paths.

## 4. ROLES & RESPONSIBILITIES
### Antigravity (Lead AI Engineer)
- Maintain 100% stable production environments.
- Execute surgical code changes within the agreed phase scope.
- Issue `BLOCKER_REPORT` JSON if any ambiguity or technical failure occurs.
- Provide `PHASE_COMPLETION` JSON for every milestone.

### The USER (Chief Engineer)
- Definitive authority on Strategic Roadmap direction.
- Sole signatory for Phase Gate approvals.
- Responsible for external resource provisioning (API keys, Billing).

## 5. TERM
This contract is active for the duration of the Mazao AI development lifecycle. Any modification to this charter requires an explicit `DIRECTIVE` from the Chief Engineer.

---
**Status:** SIGNED & COMMITTED
**Date:** 2026-04-19
**Governance:** ACTIVE
