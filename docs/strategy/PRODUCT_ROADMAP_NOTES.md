# Mazao AI — Product Roadmap Notes

## T8A: Governed Conversational Insight Layer (DEFERRED)

### Objective
Transition the bot from a "command-only" utility to a governed conversational assistant that can guide users through complex financial flows without violating regulatory boundaries.

### Architecture
The conversational layer will follow a strict 4-layer hierarchy:
1.  **Layer 1: Command Handlers (Canonical)** — The primary interface for all known financial operations (`/fuliza`, `/till`, `/statement`).
2.  **Layer 2: Deterministic System Intelligence** — Direct responses for account status and predefined insights.
3.  **Layer 3: Rule-Based Intent Router** — A deterministic router that maps natural language (e.g., "how do I use Fuliza?") to specific tutoring flows or commands.
4.  **Layer 4: Strictly Gated AI Fallback** — A large language model (LLM) used ONLY as a last resort for out-of-scope queries(Currently using DeepSeek V3 for financil analysis but as the elite faang engineer in this project, advise on whether we can use the free mistral model for the controlled AI layer or DeepSeek V3 is the best option?).

### Finance Boundary Policy
- **Educational Only**: The bot explains and guides based on application data scope.
- **No Regulated Advice**: The bot MUST NOT provide investment, loan, or tax planning recommendations that constitute regulated financial advice.
- **Scope Limitation**: The bot will not answer questions about medical, legal, political, or general internet topics.

### Interaction Examples
- **User says "hi"**: Bot greets and suggests relevant commands based on user status.
- **User asks "how do I use Fuliza?"**: Bot tutors the user toward the `/fuliza` command and explains the parsing requirements.
- **Out-of-Scope**: Bot politely redirects the user back to supported financial tools.

---

## Phase 18: Conversational Hardening (COMPLETE)
- **T8A-T8G**: Implemented deterministic intent routing, idempotent /start, and global command interrupts.
- **T8H**: Implemented soft recovery layer for guided conversational fallback.

## Phase 19: Daraja Production Readiness (COMPLETE)
- **T9A**: Audited and fixed Daraja callback route alignment.
- **T9B**: Implemented native STK push and certified live flows.
- **T9C**: Finalized payment UX with guidance and feedback messages.
- **T9D**: Prepared official Live Activation Runbook.

---

## Current System State: PRODUCTION_READY
- **Payment Layer**: Native Daraja STK push certified (awaiting `DARAJA_PASSKEY`).
- **Conversational Layer**: Hardened with deterministic routing and global interrupts.
- **Onboarding**: Idempotent and state-aware.
- **Runbook**: Official activation protocol prepared in `docs/runbooks/`.

## Next Phase: T9E Activation
- **Trigger**: Configuration of production secrets (`DARAJA_PASSKEY`).
- **Objective**: Full live deployment and activation of native payments.

---

## Deferred Features
- **M-Shwari Implementation**: Deferred to Phase 20+.
- **LLM-First Routing**: Explicitly forbidden to ensure deterministic reliability.
