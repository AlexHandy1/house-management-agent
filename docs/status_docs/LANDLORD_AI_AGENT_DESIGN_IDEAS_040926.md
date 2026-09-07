# Landlord AI Agent — Design Ideas

**Status:** Exploration / architecture-level design (not a build spec). Purpose is dual: a real tool to replace a managing agent, and a system-design practice exercise.

## Problem

Currently paying ~10% of rental income to a managing agent that doesn't reduce time spent managing the property or improve outcomes (cost, speed, confidence in regulatory compliance). Maintenance/repairs management is the sharpest pain point.

## Functional requirements (priority order)

1. Generate a cost estimate for a reported issue, to compare against contractor quotes
2. Find appropriate contractors (existing list and/or web search)
3. Get quotes from contractors (optional extension: negotiate)
4. Collect a reported issue from a tenant (text + maybe photos) — lower priority; managing agent currently does this, so can start by manually feeding issue text in
5. Manage tenant/contractor communications to arrange visits and confirm work status — landlord stays in the loop, signs off on sends
6. Collect invoices from contractors (optional extension: pay them)
7. Notify/schedule regular regulatory maintenance (e.g. UK annual gas safety certificate)
8. Add calendar invites when work is scheduled
9. Build an income vs. expenses ledger to support annual tax filing

## Non-functional requirements

- Scale: single user (me), low volume, sequential/time-gapped actions — but designed with an eye toward open-sourcing for other landlords later
- Security/privacy: PII handling for tenant/contractor contact and payment details
- Observability: comprehensive tracing across all agent activity, from the start — not bolted on later
- UX: mobile-first control (WhatsApp/Telegram/SMS-style), landlord notified at each step and asked to sign off on key actions

## Architecture decisions reached so far

### Component map (5 components)

1. **Channel adapter** — pure plumbing, no reasoning. Inbound: normalizes WhatsApp/Telegram/CLI messages into Events. Outbound: formats structured results into messages. Swapping channels later shouldn't touch agent logic.
2. **Domain state store** — durable source of truth (Issue, Contractor, Quote, Message, ComplianceObligation, LedgerEntry). Needed because: (a) ledger/compliance are reporting needs over structured data, not conversational; (b) a stateless/event-driven system needs somewhere authoritative to read/write between invocations; (c) source of truth must be independent of any one channel.
3. **Agent reasoning** — the only place an LLM runs; see execution model below.
4. **Approval gate + action executor** — merged. Deterministic. Gates proposed write-actions on policy (auto vs. needs landlord sign-off), executes idempotently.
5. **Observability** — cross-cutting trace over every LLM call, tool call, and state transition, tagged by issue ID.

### Execution model: reactive/stateless, not durable-orchestration

Each external event (new issue, contractor reply, landlord approval) triggers a short-lived handler that loads current state from the DB, reasons, writes state back, and exits — no long-lived orchestration engine (e.g. Temporal). Justified by low concurrency/volume; a full durable-execution engine is heavyweight machinery for a problem this size, and this pattern gets most of the benefit (resumability, auditability, HITL pauses) with far less operational complexity.

**Idempotency is required, not optional**, because side effects here are real-world and costly to duplicate (double-sent contractor messages, double calendar invites, double-counted ledger entries):
- Every inbound Event gets a stable idempotency key (provider message ID, or a derived hash); already-processed events are skipped.
- "Decide" and "execute" are separate steps — the decision (e.g. a drafted message) is durably recorded first; the side effect (actually sending it) is a separately idempotent step gated on "has this been sent already," so a crash-and-retry replays harmlessly instead of double-acting.

### Agent pattern: Single-Agent + ReAct loop + Human-in-the-Loop, wrapped in deterministic Custom Logic

Confirmed against two external references (Google Cloud's agentic design pattern guide, Kimi's agentic architectures overview) — both converge on Single-Agent as correct for a bounded task at this stage.

- **Not a fixed pipeline.** Rejected a hardcoded `estimate → find_contractors → draft_quotes` sequence in favor of giving the agent a toolset and letting it decide order/branches — needed because real issues don't fit one shape (e.g. some need no contractor at all; some need a clarifying question back to the tenant before an estimate is possible).
- **Status field redefined**: not "which pipeline step" but "what/who are we waiting on" — `OPEN`, `AWAITING_TENANT_INFO`, `AWAITING_LANDLORD_APPROVAL`, `AWAITING_CONTRACTOR_REPLY`, `RESOLVED_NO_ACTION_NEEDED`, `CLOSED`. Any issue can visit these in any order.
- **Agent memory = append-only event/decision log** per issue (event-sourcing-lite), not fixed schema fields — because there's no guaranteed step order, the agent needs full history, not "stage N implies fields A/B exist."
- **Tool set**: read tools (no side effects: search contractors, look up cost reference, query past similar issues) called freely by the agent during reasoning; propose tools (write structured artifacts, e.g. `propose_cost_estimate`, `shortlist_contractor`, `draft_message`, `mark_no_action_needed`) that never directly cause external side effects.
- **Forced termination**: a turn can only end by calling `pause(reason)` — required, not optional — bounded by a max-iteration cap that itself pauses with `needs_human_review` if hit. This keeps the outer reactive/event-driven system well-defined (always knows what wakes an issue up next) even though the path within a turn is agent-decided.
- **Safety boundary is orthogonal to agency**: however free the agent is to plan, it only ever *proposes* actions via tool calls (e.g. `draft_message`, never `send_message`); a separate deterministic layer executes anything irreversible, gated by approval policy. More agentic planning freedom does not mean less safety — the two axes are independent.

### Scope boundary to avoid single-agent overload (open item, not yet built)

Both external references warn the same failure mode: single-agent performance/context degrades as tool count and task diversity grow. Since the full functional requirement list spans genuinely distinct domains, the plan is to **not** grow one agent's toolset to cover everything, but split by domain:
- **Maintenance Issue Agent** — the ReAct-loop design above; genuinely ambiguous, worth the agentic flexibility.
- **Compliance Scheduler** (gas safety cert etc.) — mostly deterministic date-triggered logic; LLM used narrowly if at all (e.g. checking regulation changes). Not a candidate for the ReAct loop.
- **Ledger/Bookkeeping** — largely deterministic double-entry logic; LLM assists only at the edges (e.g. categorizing an ambiguous expense).

Routing between these domains likely doesn't need to be an AI decision either — event source/type usually determines domain deterministically (plain code, not a Coordinator agent).

**Contractor negotiation** (listed as an optional extension) is a better fit for a **Generator-Critic** pattern (one pass drafts a counter-offer, a second pass evaluates against criteria like market rate/tone before it's shown to the landlord) than as an ad hoc tool inside the general reasoning loop — to design when that extension is picked up.

### Explicitly rejected (for now) and why

- **Durable orchestration engine** (Temporal-style) — unjustified operational complexity at this volume/concurrency.
- **Multi-agent Parallel/Hierarchical/Swarm/Coordinator patterns** — real added cost (more model calls, harder debugging, synthesis/conflict overhead per both external references) not justified yet; revisit only if a single domain's agent genuinely needs internal specialization.

## Data model sketch (illustrative, not final)

```
Issue(id, source_text, photos[], status, category, created_at)
CostEstimate(issue_id, low, high, currency, basis)      -- agent's own reference estimate
Contractor(id, name, trade, contact_info, source, verified)
IssueContractorShortlist(issue_id, contractor_id, rank, reason)
DraftMessage(id, issue_id, contractor_id, text, created_at)
Quote(id, issue_id, contractor_id, amount, currency, notes, received_at)  -- distinct from CostEstimate;
                                                                            -- per-contractor, populated once
                                                                            -- quote collection is in scope
```
`CostEstimate` (single reference figure per issue) is deliberately separate from `Quote` (per-contractor, actual) so comparing contractor quotes against the estimate is a simple query, not a redesign.

SQLite is sufficient at this scale — no need for a hosted DB yet.

## Worked example trace (illustrating the agent pattern)

- **Vague report, needs more info:** agent reads "tap's making a noise," finds no comparable past issue, description too vague to estimate → drafts a clarifying message to the tenant → `pause(AWAITING_TENANT_INFO)`. Weeks later tenant replies → new Event → new turn, history now includes the answer → agent proceeds to estimate.
- **No contractor needed:** agent reads "porch light bulb needs replacing," recognizes a trivial self-fix → `mark_no_action_needed(...)` → `pause(RESOLVED_NO_ACTION_NEEDED)`. No estimate or contractor search ever invoked.

## Open questions / not yet resolved

- Thread-to-issue matching for inbound contractor/tenant replies (dedicated channel per issue vs. reference-code convention vs. LLM classification vs. landlord-as-manual-relay initially) — deferred as a leaf-level decision within the ingestion component, to revisit once the broader shape is settled.
- Approval gate policy specifics — which proposed action types auto-proceed vs. require landlord sign-off.
- What "comprehensive observability" needs to capture concretely for a ReAct loop (full prompts/tool I/O vs. structured decision summaries; retention; how it's queried/reviewed).
- PII handling approach for tenant/contractor data (storage, redaction in logs/traces, access boundaries) — not yet discussed in depth.
- Phase/slice sequencing — deliberately deferred per user direction; architecture exploration was prioritized first since it will inform slicing.

## Next steps

Continue grilling: Approval gate policy design, and/or observability requirements for the ReAct loop, and/or PII/privacy handling — user to pick focus for next session.
