# Mazao AI System Roadmap

## Phase 19: Daraja & AI Resilience (Completed)
- **T14–T16**: Fixed `httpx` imports, restored `/report` parser-save-launch flow, and synchronized production dependencies (`requirements.txt`).
- **T17–T18**: Identified and mitigated **Live Transaction Schema Drift** (`tenant_id` missing in Supabase). Implemented "DEGRADED MODE" with surgical `try-except` guards.
- **T19–T21**: Fixed unreachable report fallbacks and implemented tiered data source routing (Custom Tx -> Live Tx -> Cached AI -> Statement Summary).
- **T22–T24**: Verified OpenRouter AI pipeline, implemented statement freshness recomputation logic, and added failure-reason reporting in LLM nodes.

## Phase 20: Multi-Number Wallets & Compliance (Active/Locked)
> [!IMPORTANT]
> **GOVERNANCE LOCK**: Implementation is FROZEN until T9H live payment validation completes.
- **T20A–G**: Audit triage, remediation freeze, and modularization design.
- **T20H–J**: Statutory obligation formatting unification and Compliance Engine abstraction (VAT, PAYE, NSSF, SHA).
- **T20K–N**: Electricity availability-adjusted depletion forecasting and power context surfacing.

## Future Roadmap
- **Stability**: Full Supabase schema reconciliation (Live Tx `tenant_id`).
- **AI**: DeepSeek integration as secondary LLM provider.
- **Monetization**: Tiered pricing (Core vs Pro) billing automation.
- **Observability**: Centralized telemetry for LLM tokens and node performance.
