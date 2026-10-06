# Brief spec: multi-turn conversation (issue-bound advice/deepen slice)

**Date**: 2026-10-02
**Status**: Discussion only — not yet built, not yet grilled. Captures a planning
conversation; several open questions below are genuinely unresolved, not pending
confirmation of an already-decided answer.
**Format note**: deliberately brief, not the full `/create-technical-spec` template —
a starting point for the next session to pick up and go deeper on (via `/grill-me` or
direct build planning), not a spec for an autonomous agent to build unsupervised from.

## Goal

Let the landlord have a bounded back-and-forth (capped at 10 rounds) with the agent
about an issue, instead of the current one-shot "submit issue → get outcome" flow.
Motivating examples: "go deeper on this cost estimate," "I got a quote, is it
reasonable," "check this against another contractor." This is the first slice of a
larger direction (see "Where this is heading") but is scoped narrowly on purpose.

## Why this shape, not the bigger thing

The fuller ambition discussed is a general-purpose maintenance agent that could
eventually support the whole issue lifecycle (report → estimate → deepen/revise/
compare → confirm resolved, with actual cost and duration) and a wider, less
structured set of questions than today's fixed issue-in/cost-and-contractors-out
workflow. Two things made that too much to build in one slice:

- **Open-ended write discretion** (the agent deciding *if*, *what*, and *where* to
  write to the DB for an arbitrary follow-up) is hard to bound and hard to test — it
  turns a closed, unit-testable outcome contract (today's `AgentOutcome`) into a
  behavioral-eval problem. Binding every conversation to a single existing `issue_id`
  sidesteps this for now: there's no "is this a new issue or not" judgment call to get
  wrong, because the subject is structurally fixed for the whole conversation.
- **Lifecycle status (resolved/actual cost/duration) is a real schema and UX change**
  in its own right, and most of it (confirming an issue resolved, recording actual
  cost) probably doesn't need the agent at all — it's structured data entry. Bundling
  it into this slice would couple genuinely agent-shaped work (open-ended advice) with
  work that may not need an LLM in the loop.

## Agreed shape (from discussion — not yet stress-tested)

- **Conversation is bound to one `issue_id`** for its entire lifetime — either the
  issue just created in round 1, or an existing one the landlord picks to follow up
  on. No mid-conversation creation of a *different* issue.
- **Persisted conversation history**, not in-memory — leaning toward a new table in
  the existing Postgres DB (same VM/VPC pattern as `issues`/`articles`), even though
  this slice alone could arguably survive on in-memory state for a single continuous
  sitting. Reasoning: lifecycle support (later) will need persistence regardless, and
  building session handling once rather than rebuilding it was judged worth the
  slightly bigger scope now.
- **10-round cap**, enforced per conversation (i.e. per issue-follow-up session), not
  cumulatively across an issue's whole future lifecycle.
- **New read-only tools**, scoped to the bound issue: something like
  `lookup_issue(issue_id)` to pull the existing estimate/contractors back into
  context, reuse of the existing `research_cost`/`find_contractors` tools for "go
  deeper"/"compare," and access to the `articles` table where relevant.
- Single landlord, IAP-gated — no multi-tenant session isolation needed; a
  conversation ID carried by the frontend is enough, no new auth plumbing.

## Open questions — genuinely unresolved, pick up next session

1. **Does this slice write anything back, or is it advice-only?** E.g. if the agent
   revises a cost estimate after being told a quote came in lower/higher, does that
   update the issue row? If yes, keep-original-vs-overwrite is itself an audit-trail
   decision (you likely want both the original estimate and any revision visible, not
   silently overwritten) — but keeping this slice read-only-advice-only first is the
   simpler, lower-risk option and was flagged as worth deciding explicitly before
   scoping the build.
2. **Conversation storage schema**: what a stored "turn" looks like (role, content,
   tool calls/results, round number), and how it's linked to `issue_id`.
3. **How does the landlord pick which issue to follow up on?** A real UI/API surface
   question, not just backend — today's frontend has no "resume/continue" affordance.
4. **Context growth across rounds**: replay full history each round vs. trim/
   summarize. Not urgent at round 2-3, becomes real by round 8-10. No decision made
   yet either way.
5. **Tracing shape**: one parent Langfuse trace per conversation with each round's
   agent loop nested underneath, vs. today's one `run_agent` span per request. Leaning
   toward nesting but not confirmed.
6. **Cap-hit UX**: hard stop with an error at round 10, or some other graceful close
   (e.g. a final round that still answers but blocks further replies)? Undecided.

## Explicitly not in this slice

- Lifecycle status fields (`status`, `actual_cost`, `resolved_at`/duration) and the
  "confirm resolved" step — deferred to a later slice; likely doesn't need the agent
  at all (structured data entry), separate from this slice's agent-shaped work.
- Open-ended write discretion for follow-ups unrelated to the bound issue (i.e. the
  agent deciding a new issue should be created mid-conversation) — deliberately
  deferred, not rejected; see "Why this shape" above.
- Any change to the existing single-shot `POST /api/issue` flow or its `AgentOutcome`
  contract — this slice is additive, not a replacement.

## References

- `ARCHITECTURE.md` — current agent loop (`services/agent.py`), issues database, and
  request flow this slice builds on top of.
- `docs/decisions/ADR-005-contractors-data-model-and-agent-tool-independence.md` — the
  existing agent-loop/outcome design this slice must stay compatible with (or
  consciously extend) for the single-shot flow.
- `docs/status_docs/WORK_SUMMARY_300926.md`, `WORK_SUMMARY_021026.md` — multi-turn
  interactions noted as a deprioritized next step across two prior sessions before this
  discussion.
