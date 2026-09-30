# ADR-005: Contractors data model and independent agent tools

## Status
Accepted

## Date
2026-09-30

## Context
Adding `find_contractors` raised two open questions flagged as scalability
concerns in the 29 Sep session notes:

1. **Data model**: `issues_db` presumed one issue, one table. A second
   entity (contractors) needed a relationship to issues — a contractor can
   be relevant to more than one issue, and vice versa.
2. **Agent loop dispatch**: `_run_loop` (`services/agent.py`) ended the run
   the instant either `save_*` tool was called, via a hardcoded
   if/elif chain. Adding a fourth tool meant deciding whether tools stay
   mutually exclusive and run-ending, or become independent.

## Decision
- **Many-to-many via a join table**: `contractors` (id, name, trade,
  source_url, email, phone_number, created_at) and `issue_contractors`
  (issue_id, contractor_id, UNIQUE pair) — no `contractor_id` column on
  `issues`, no `issue_id` column on `contractors`. `issues_db.save()`
  upserts a contractor by exact name match and links it via the join
  table; `list_issues()` exposes a computed `has_contractor` via an
  `EXISTS` subquery rather than a stored column.
- **Kept a single `issues_db.py` module** rather than splitting into
  per-table service modules — contractors' read/write logic is small
  enough that a split would be premature; revisit if a third table
  arrives.
- **Agent tools became independent, not run-ending**: `save_cost_estimate`
  and `save_contractors` now accumulate into local state and let the loop
  continue; the run ends when the model stops calling tools (or hits
  `MAX_ROUNDS`), and `_finalize_outcome` builds one `AgentOutcome` from
  whatever was accumulated. `save_clarifying_question` is the one
  exception — it stays all-or-nothing, ending the run immediately and
  discarding anything already accumulated that run.
- **`find_contractors()` takes no arguments**, mirroring `research_cost()`
  — the sub-call infers the trade from the issue text and property
  location itself, rather than relying on the calling model to pre-classify
  the trade as a tool argument.
- **Fallback outcome status**: if a run ends with nothing accumulated (no
  cost, no contractors), the outcome is `needs_info` with a generic
  clarifying question, not `failed`. `failed` is now reserved for actual
  provider/call errors (empty-choices retries exhausted, connection
  errors) — not "the model didn't produce anything," which was previously
  conflated. A pure prompt-injection attempt with no real content
  sometimes gets blocked at the model level with no tool call at all;
  this is currently accepted as a `failed` outcome rather than forced into
  `needs_info`, since there's no multi-turn conversation yet to recover
  the context in a later turn — revisit alongside multi-turn support.

## Alternatives Considered

### One-to-many (`contractor_id` on `issues`, or `issue_id` on `contractors`)
- Pros: simpler schema, no join table.
- Cons: cannot express a contractor genuinely serving multiple issues,
  which is a real case (a landlord's known plumber recurring across
  properties/issues).
- Rejected because: the actual relationship is many-to-many.

### Denormalized "primary contractor" column on `issues`
- Pros: cheap `has_contractor`/primary-contractor display without a join.
- Cons: a second source of truth alongside the join table; the join table
  is already the correct source of truth once it exists.
- Rejected because: the `EXISTS` subquery is cheap enough at this scale
  and avoids write-path complexity of keeping two things in sync.

### Explicit `finish()` tool to end the agent run
- Pros: unambiguous run-end signal, doesn't rely on inferring "no more
  tool calls" as "done."
- Cons: one more tool for the model to learn and remember to call; one
  more failure mode (model saves everything but forgets to call
  `finish()`, which would then hit `MAX_ROUNDS` instead of ending
  cleanly).
- Rejected because: "stop calling tools" is the natural signal a
  tool-calling model already produces; no new tool needed.

## Consequences
- Every prompt-following tool call by the model now costs one extra model
  round-trip before the run can end (the model must explicitly stop
  calling tools), compared to the old immediate-return-on-save shape.
  Acceptable trade-off for decoupled tools.
- The system prompt must be explicit that every run has to end with
  either a `save_*` call or `save_clarifying_question` — live evals showed
  a looser prompt let the model decline in plain text with no tool call at
  all on some adversarial inputs, which the fallback-to-`needs_info` logic
  now catches regardless, but the prompt was tightened anyway to keep
  behavior primarily prompt-driven rather than relying on the fallback.
- A request containing a prompt-injection attempt alongside real content
  must now be refused as a whole (no tool calls at all) rather than
  partially completing the legitimate-looking part — an earlier version of
  the tightened prompt still ran the full paid research pipeline on such
  input before this was caught by a live eval.
