# Work Summary — 30 September 2026

Branch: `add_contractor_search`, off `main` (which now has the merged
`build_out_issue_agent_functionality` work from 29 Sep). This session added
`find_contractors` end-to-end: DB schema, agent loop, UI, evals, e2e, logging.
Preferred-contractors whitelist and multi-turn support explicitly deferred
to a later slice per the user's scoping.

## What was built

- **Contractors data model** (`app/backend/services/issues_db.py`,
  `models/agent_outcome.py`) — `contractors` (id, name, trade, source_url,
  email, phone_number, created_at) and `issue_contractors` (a many-to-many
  join table, `UNIQUE(issue_id, contractor_id)`). No `contractor_id` on
  `issues`. `save()` upserts a contractor by exact name match and links it;
  `list_issues()` exposes a computed `has_contractor` via `EXISTS`. New
  `ContractorResult` Pydantic model; `AgentOutcome.contractors` field added.
  Both tables created automatically via the existing `CREATE TABLE IF NOT
  EXISTS` / `init_schema()`-on-startup mechanism — purely additive, no
  `ALTER` needed, safe for both local Postgres and the production DB VM (not
  yet deployed there — happens on next merge-to-main + CI/CD deploy).
- **Agent loop restructured** (`services/agent.py`) — `save_cost_estimate`
  and `save_contractors` (new) no longer end the run immediately; they
  accumulate into local state (`cost`, `contractors`, `sources`,
  `findings_text`) and the loop continues. The run ends when the model
  stops calling tools or hits `MAX_ROUNDS`, at which point
  `_finalize_outcome()` builds one `AgentOutcome` from whatever
  accumulated. `save_clarifying_question` stays all-or-nothing (ends the
  run immediately, discards anything already accumulated). New
  `find_contractors()` tool mirrors `research_cost()` exactly — no
  caller-supplied trade/area; its sub-call infers the trade from the issue
  text and property location itself. System prompt rewritten so cost and
  contractors are independent capabilities the model chooses between based
  on what's actually being asked (defaulting to both if unclear), not a
  single "research then commit" path.
- **Fallback outcome status** — a run that ends with nothing accumulated
  (no cost, no contractors, no tool ever called usefully) now falls back to
  `needs_info` with a generic clarifying question, rather than `failed`.
  `failed` is reserved for actual provider/call errors (empty-choices
  retries exhausted, connection errors).
- **Injection handling tightened** — the prompt now requires refusing a
  request *as a whole* (no `research_cost`/`find_contractors`/`save_*`
  calls at all) when any part of it contains a redirect/extraction attempt,
  not just declining the malicious sub-request while still running the
  paid pipeline on the "legitimate-looking" part. A live eval caught the
  old (looser) prompt still running full cost + contractor research on an
  issue containing an injected instruction.
- **UI** (`app/frontend/src/App.tsx`) — result box lists contractors
  (name, trade, phone/email) alongside the cost estimate, and hides the
  cost line entirely when only contractors were produced. Issues table
  gained a Contractor Y/N column, keyed off `has_contractor`.
- **Live evals extended** (`tests/evals/test_agent_eval.py`,
  `prototypes/synthetic_issues.yaml`) — contractors-count (≥2) + contact-
  details-present eval on the default (both capabilities) path; two new
  fixtures (`cost_only_001`, `contractor_only_001`) proving
  `save_cost_estimate`/`save_contractors` genuinely run independently
  based on what's asked, not always together. All 10 live evals pass.
- **e2e test extended** (`tests/e2e/test_issue_flow_e2e.py`) — asserts
  `.agent-contractors` is populated after a real browser submission, not
  just the cost estimate. Passing against local Postgres/backend/frontend.
- **DB write logging added** (`services/issues_db.py`) — `save()` now logs
  `issue_id`/`status`/`contractor_count` (never issue text, matching the
  existing CON-004 rule), closing a gap where DB writes were completely
  silent — became more relevant with the new contractor upsert/join logic
  adding a second DB round-trip that could partially fail.
- **Docs**: `docs/decisions/ADR-005-contractors-data-model-and-agent-tool-
  independence.md` (full reasoning + alternatives considered);
  `ARCHITECTURE.md` and `README.md` updated to describe the five-tool
  agent, the contractors/issue_contractors tables, and the live UI.

## What was explored / learnt

- **Loop-restructuring broke several existing mocked-LLM tests** in a
  characteristic way: tests written for "first save ends the run" queued
  exactly enough mock replies for that old shape, so under the new
  "loop continues until no tool_calls" shape they hit `StopIteration` on
  the next model call. Fixed by adding a trailing `text_reply("Done.")` to
  each affected test — this is the correct fix, not a workaround, since it
  represents the model's genuine "nothing more to do" turn.
  `find_contractors`'s own internal sub-call (mirroring `research_cost`)
  also consumes an extra queued reply, which needed accounting for
  separately in the queue-length math.
- **Naive substring-based leak checks are fragile**: the existing
  `test_a_prompt_injection_alongside_a_real_issue_never_leaks_sensitive_
  content` eval asserts `"password" not in outcome_text` — this produced a
  false-positive failure when the model's own refusal text legitimately
  quoted back "admin passwords" while explaining it wouldn't share them.
  Pre-existing test fragility, not something this session introduced or
  fixed; noted for awareness.
- **A pure prompt-injection attempt (no real maintenance content at all)
  is genuinely flaky at the model level** — regardless of how directively
  the system prompt instructs "always call a tool before stopping," the
  model sometimes just refuses in plain text with zero tool calls. The
  fallback-to-`needs_info` logic doesn't even catch this specific case
  reliably (a real API/empty-choices flake was observed causing a
  `failed` outcome on a rerun) — accepted as `failed`-or-`needs_info`
  for this one adversarial fixture; not chased further per explicit
  user direction (low priority given other guardrails, no multi-turn
  history to make it more urgent yet).
- **IAP TCP forwarding for the DB VM's SSH access** (the "Operator" node
  in `ARCHITECTURE.md`'s network diagram) is a separate IAP mechanism from
  the HTTP IAP gating the web app (ADR-002) — governed by
  `roles/iap.tunnelUser`, referenced only in a comment in
  `infra/database.tf`, with no Terraform-managed IAM binding found for it.
  Likely covered implicitly by the project Owner's broad IAM on this
  no-org personal GCP project. Not fixed this session — flagged as a
  documentation gap worth closing if it matters.

## Decisions and trade-offs

- **Decision:** many-to-many `contractors`/`issue_contractors` join table,
  no denormalized `contractor_id` anywhere. **Why:** the user corrected an
  initial inconsistent field list (contractors had both `issue_id` and a
  many-to-many requirement) — confirmed genuine many-to-many is wanted,
  since a contractor can legitimately serve more than one issue.
  **Trade-off:** `has_contractor` is a computed `EXISTS` subquery, not a
  stored column — accepted as cheap enough at this scale over keeping a
  denormalized column in sync.
- **Decision:** `save_cost_estimate` and `save_contractors` are
  independent tools; the loop ends when the model stops calling tools, not
  on the first save. **Why:** user explicitly rejected coupling
  contractors-saving to cost-estimate-saving as "too hard coded" — wants
  to support "just find me a cost estimate" or "only find me contractors"
  as distinct, real requests. **Trade-off:** resolves the 29-Sep-flagged
  "hardcoded if/elif chain, not a registry" note partially (tools are now
  decoupled in what they *do*, though dispatch is still an if/elif chain
  — a full registry abstraction was not built, deferred until it's
  actually needed).
- **Decision:** `find_contractors()` takes no arguments (mirrors
  `research_cost()`). **Why:** user directed the trade to be inferred from
  the issue itself, always grounded in issue text + property location,
  rather than trusting the calling model to pre-classify trade/area as
  tool arguments.
- **Decision:** keep the three-value `AgentOutcome.status` enum
  (`done`/`needs_info`/`failed`); no new `refused` status for declined/
  off-topic requests. **Why:** user weighed adding a distinct status
  against side effects, decided to defer — "we have other guardrails in
  place and no multi-turn history, so it's less important" — revisit when
  multi-turn support is built.
- **Decision:** DB write logging added for `issues_db.save()` only (issue
  ID, status, contractor count); no general unhandled-exception logging
  added. **Why:** the first gap was directly new surface from this
  slice's contractor upsert/join logic; the second is a pre-existing,
  broader gap (affects the whole app, not just contractors) that the user
  explicitly said not to prioritize now.
- **Decision:** contractors slice explicitly excludes the preferred-
  contractors whitelist path (always search the web, no skip-if-2-
  preferred-match logic) and multi-turn interactions (e.g. "do we already
  have a contractor for this issue"). **Why:** user scoped this out
  upfront as later slices.

## Next steps

1. **Key decision for next session: landlord news feed feature vs. more
   multi-turn thread support** (e.g. "is there already a contractor for
   this issue?", following up on a clarifying question already asked on
   an issue) — which to prioritize next. Not discussed in detail this
   session; needs a decision before starting either.
2. **Merge to `main` and deploy** — not done this session; DB migration
   for the two new tables only actually reaches the production DB VM once
   this branch merges and CI/CD deploys. Verify live afterward (SSH via
   IAP, confirm `contractors`/`issue_contractors` exist) same as the 29
   Sep verification for `issues`.
3. **Preferred-contractors whitelist** — explicitly deferred this session;
   next natural slice per the original scope.
4. **Multi-turn interactions** — e.g. "is there already a contractor for
   this issue" with DB read access, or following up on a clarifying
   question already asked — explicitly deferred; see item 1. Also the
   trigger for revisiting the `status` enum question (should a refused/
   off-topic request get its own status, distinguishable from a real
   provider failure).
5. **General unhandled-exception logging** — flagged, not prioritized.
   Currently a DB/provider failure surfaces as an unstructured 500 outside
   the app's `JsonLogFormatter`, with no request/IAP-identity correlation.
6. **`roles/iap.tunnelUser` IAM binding** — not found in Terraform for the
   DB VM's SSH access; confirm/document how it's actually granted if it
   matters (likely implicit via project Owner role today).
7. Carried from 29 Sep, still open: revisit the eval/DB boundary (evals
   use a capturing `save`, not `issues_db.save`); name Langfuse
   generations for readability; consider `roles/logging.logWriter` for the
   DB VM's service account to quiet serial-console permission-denied noise.
