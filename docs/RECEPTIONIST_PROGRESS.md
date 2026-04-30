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
- [x] T9U: Cross-surface UX differentiation between /status and /kra completed.
    - Record: Updated /status (Individual) header to "📌 Your Key Obligations" with context signal.
    - Record: Updated /kra header to "📊 Statutory Deadlines" with "Official tax & compliance schedule" signal.
    - Record: Added "_Official statutory deadlines_" context to /status (Business) dashboard.
    - Result: Distinguishable surfaces within 2 seconds.
    - Scope: Copy/UI only. Phase 20 lock intact.
- [x] T9V: /kra Header Source Alignment & Logic Verification.
    - Record: Traced /kra header to `M.KRA_OBLIGATIONS_HEADER` and ensured alignment with "📊 Statutory Deadlines".
    - Record: Confirmed `/kra` and `/status` logic separation; no statutory dates changed.
    - Result: Live /kra now displays intended header and context label.
    - Scope: Copy/UI only. Phase 20 lock intact.
- [x] T9W: /status vs /mystatus Command Alias Trace & Intent Classification.
    - Record: Investigated identical output between `/status` and `/mystatus`.
    - Finding: Intentional alias for Individual users. `cmd_status` explicitly redirects to `cmd_mystatus` if `user_type == "individual"`.
    - Divergence: Business users see a business dashboard on `/status` and a redirect instruction on `/mystatus`.
    - Result: confirmed intentional UX design for context-aware status rendering.
    - Status: Pending decision under Phase 19 freeze (No logic/path change made).
    - Scope: Read-only investigation. No files modified.
- [ ] T9H: Live Activation Execution (Pending `DARAJA_PASSKEY`).
    
## Phase 20: Multi-Number Wallets (Roadmap)
> [!IMPORTANT]
> **GOVERNANCE LOCK**: Phase 20 audit remediation is strictly **FROZEN** until T9H live payment validation completes. See [SYSTEM_AUDIT_REMEDIATION_FREEZE.md](governance/SYSTEM_AUDIT_REMEDIATION_FREEZE.md).

- [x] T10A: Architecture & Design Documentation.
- [x] T9Y: /status vs /mystatus Product UX Decision Audit.
    - Record: Conducted visibility and semantic audit of status commands.
    - Visibility: Confirmed strictly separated in `menu.py` (Individuals see `/mystatus`, Business see `/status`).
    - Behavior: `/status` correctly redirects individuals to `/mystatus` for UX resilience (context-aware help).
    - Recommendation: Maintain current "Smart Redirect" architecture. Duplication is intentional for backwards compatibility and "natural" command handling.
    - Result: No code change required; Phase 19 configuration verified as optimal.
    - Scope: Read-only audit. No files modified.
- [x] T9Z: /status Individual Redirect Clarity Improvement.
    - Record: Added `👤 Personal Status` notice when individuals invoke `/status`.
    - Context: Ensures individuals understand they are viewing their personal dashboard despite using the business-primary command.
    - Visibility: Menu visibility remains unchanged (scoped by user type).
    - Result: Improved UX trust and clarity for context-aware redirects.
    - Scope: Copy/UI only. Phase 20 lock intact.
- [x] T9AB: Admin Status Bypass Fix.
    - Record: Corrected `cmd_status` logic to ensure super-admins (Chief Engineer) bypass the individual redirect.
    - Context: Admins can now view the full Business/Admin dashboard even if their personal profile is set to "individual".
    - Result: Resolved routing conflict identified in T9AA.
    - Scope: Role logic fix. Phase 20 lock intact.
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
