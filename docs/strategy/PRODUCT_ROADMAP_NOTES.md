# Mazao AI — Product Roadmap Notes

## T8A: Governed Conversational Insight Layer (DEFERRED)

### Objective
Transition the bot from a "command-only" utility to a governed conversational assistant that can guide users through complex financial flows without violating regulatory boundaries.

### Architecture
The conversational layer will follow a strict 4-layer hierarchy:
1.  **Layer 1: Command Handlers (Canonical)** — The primary interface for all known financial operations (`/fuliza`, `/till`, `/statement`).
2.  **Layer 2: Deterministic System Intelligence** — Direct responses for account status and predefined insights.
3.  **Layer 3: Rule-Based Intent Router** — A deterministic router that maps natural language (e.g., "how do I use Fuliza?") to specific tutoring flows or commands.
4.  **Layer 4: Strictly Gated AI Fallback** — A large language model (LLM) used ONLY as a last resort for out-of-scope queries(Currently using DeepSeek V3 for financila anlysis but as the elite faang engineer in this projec, advise on we wether we can use the free mistral model for the controlled AI layer).

### Finance Boundary Policy
- **Educational Only**: The bot explains and guides based on application data scope.
- **No Regulated Advice**: The bot MUST NOT provide investment, loan, or tax planning recommendations that constitute regulated financial advice.
- **Scope Limitation**: The bot will not answer questions about medical, legal, political, or general internet topics.

### Interaction Examples
- **User says "hi"**: Bot greets and suggests relevant commands based on user status.
- **User asks "how do I use Fuliza?"**: Bot tutors the user toward the `/fuliza` command and explains the parsing requirements.
- **Out-of-Scope**: Bot politely redirects the user back to supported financial tools.

---

## Deferred Features
- **M-Shwari Implementation**: Deferred to Phase 18+.
- **Daraja Full Integration**: Deferred to Phase 19+.
- **LLM-First Routing**: Explicitly forbidden to ensure deterministic reliability.
