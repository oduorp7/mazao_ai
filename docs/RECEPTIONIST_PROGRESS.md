# Receptionist Progress — Mazao AI

## Phase 18: Conversational Hardening
- [x] T8A: Rules-based intent router design.
- [x] T8B: Deterministic routing core implementation.
- [x] T8C: Post-session unknown intent routing.
- [x] T8D: Deployment of routing layer.
- [x] T8E: Global command interrupt fix.
- [x] T8F: Session escape certification.
- [x] T8G: Idempotent /start command.
- [x] T8H: Soft recovery and guided fallback.

## Phase 19: Daraja Production Readiness
- [x] T9A: Callback route alignment and audit.
- [x] T9B: Native STK push implementation and certification.
- [x] T9C: Payment UX finalization and guidance.
- [x] T9D: Live Activation Runbook Preparation.
- [x] T9G: Referral Logic Hardening & Signature Alignment.
- [x] T9G1: Referral Runtime Verification & About Command.
- [x] T8I: About Command Conversion Optimization.
- [x] T8J: Telegram Command Ordering (Conversion-First).
- [x] T8K: Command Surface Audit & VAT Trust Fix.
- [x] T8M: Statutory Obligations Labeling & Trust Fix.
- [x] T9I: /report vs /statement UI Separation Fix.
    - Record: Separated no-data empty states for /report and /statement.
    - Result: /report now explains dependency on M-Pesa statement, while /statement remains upload-oriented.
    - Scope: Copy/UI only (No Phase 20 logic change).
- [x] T9T: CTA Copy Alignment & /status Annual Income Tax Label Clarification.
    - Record: Updated /statement CTA to "Tap Upload Statement below", /report CTA reads "👉 Upload your M-Pesa statement using /statement".
    - Record: Clarified /status "Annual Return" label to "Annual Income Tax Return (30 Jun)" — distinct from monthly VAT/PAYE obligations.
    - Audit: Annual Income Tax Return (30 Jun) is a SEPARATE statutory obligation from VAT (20th monthly) and PAYE (9th monthly). No discrepancy — different obligation types.
    - Statutory logic changed: NO.
    - Scope: Copy/UI only. Phase 20 lock intact.
- [ ] T9H: Live Activation Execution (Pending `DARAJA_PASSKEY`).
    
## Phase 20: Multi-Number Wallets (Roadmap)
> [!IMPORTANT]
> **GOVERNANCE LOCK**: Phase 20 audit remediation is strictly **FROZEN** until T9H live payment validation completes. See [SYSTEM_AUDIT_REMEDIATION_FREEZE.md](governance/SYSTEM_AUDIT_REMEDIATION_FREEZE.md).

- [x] T10A: Architecture & Design Documentation.
- [ ] T20A: Audit Triage & Remediation Freeze. [FROZEN]
- [ ] T20B: KRA/VAT Data Completeness Guard Design. [LOCKED]
- [ ] T20C: Discriminatory Error Handling Design. [LOCKED]
- [ ] T20D: Handler Modularization Design. [LOCKED]
- [ ] T20E: Notification Registry Design. [LOCKED]
- [ ] T20F: Webhook Backpressure Design. [LOCKED]
- [ ] T20G: Wallet/Profile Scoping Design. [LOCKED]
- [ ] T20H: Obligation Formatting Unification. [LOCKED]
    - Objective: Standardize all statutory obligation blocks (VAT, PAYE, NSSF, SHA)
    - Output format:
    - • {Name} — Due {Date}
    - Rule: {short rule}
    - Penalty: {if applicable}
    - Days left: {n}
    - Constraints:
    - - Maintain mobile-first compact layout
    - - No paragraph expansion
    - - Preserve trust-safe wording
- [ ] T20I: User-Type Personalization Layer. [LOCKED]
    - Objective: Differentiate obligations for Employer, Self-employed, Individual
    - Requirements:
    - - No hallucinated assumptions
    - - Explicit user-state detection
    - - Graceful fallback to generic view
- [ ] T20J: Compliance Engine Abstraction. [LOCKED]
    - Objective: Centralize all statutory rules into single engine
    - Requirements:
    - - Single source of truth for deadlines
    - - Remove duplicated constants
    - - Pluggable rule system (VAT, PAYE, NSSF, SHA)
    - Constraint:
    - - No breaking changes to existing handlers
- [ ] T10C: Wallet Context Middleware Implementation. [LOCKED]
- [ ] T10D: Multi-Number Command Surface (/wallets). [LOCKED]
- [ ] T10E: Transaction Scoping & RLS Verification. [LOCKED]

> [!NOTE]
> **GOVERNANCE ENFORCEMENT**: All T20H–T20J tasks are registered for architectural planning only. Do not implement before Phase 19 completion. Reference [SYSTEM_AUDIT_REMEDIATION_FREEZE.md](governance/SYSTEM_AUDIT_REMEDIATION_FREEZE.md).

## System Readiness
- **Business Logic**: Stable.
- **Payment Layer**: Hardened & Certified.
- **Conversational Layer**: Hardened & Certified.
- **Referral System**: Hardened & Functional.
- **Overall Status**: **PRODUCTION READY**
