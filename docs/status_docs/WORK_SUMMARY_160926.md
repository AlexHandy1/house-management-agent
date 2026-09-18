# Work Summary — 16 September 2026

Session goal: no code changes. Strategic pivot discussion — reconsider the mobile/Telegram-first
direction from the 14 Sep session and agree the next actual build priority.

## What was built

Nothing in this codebase — planning/direction session only.

## What was explored / learnt

### Pivot away from mobile-channel-first

User proposed refocusing the first build around a web interface (accessible via mobile browser)
rather than a Telegram-type bot, and prioritising functionality that replaces what the user
currently does manually to support an estate agent:
- Generate a cost estimate for a reported issue, to compare against contractor quotes
  (extended: vet whether the issue needs more info / needs a contractor at all).
- Find appropriate contractors for a reported issue via web search, compared against an existing
  list (extended: vet contractors, e.g. online reviews — also applicable to agent-suggested
  contractors).
- Get a comparison quote from a real contractor vs. what the estate agent suggested — covers
  drafting a ready-to-send email to target contacts (extended: get mobile number, start SMS/
  mobile comms pathway).
- Building a year-end ledger of income vs. expenses (later slice).

Managing tenant↔contractor comms pathways (the rationale behind the mobile-chat-first idea from
14 Sep) is still seen as important for a full replacement system, but explicitly not what to
spend time on now.

### Reconciling with existing design work

On review, this pivot is smaller than it first appears: the ReAct loop design in
`docs/specs/maintenance-agent-slice1-full-prototype.md` is already channel-agnostic (artifacts +
`approve` CLI, no Telegram assumption). The new priority list maps closely onto tools already
specified there — `research_cost`, `find_contractors`, `propose_cost_estimate`,
`shortlist_contractor`, `draft_message` — so the pivot mainly resequences *which layer wraps the
loop* (web UI now, mobile channel later), not the loop design itself. The 14 Sep Telegram/Cloud
Run ingress research is deferred, not wasted.

Auth/login was raised as a reason web would be "quicker to extend" — clarified that auth is
**not** needed for the current single-user, landlord/estate-agent-facing scope, and should wait
until the system extends into invoicing/ledgers (multi-party, higher-stakes data).

## Decisions and trade-offs

- **Decision:** Defer the Telegram/mobile-ingress prototype planned on 14 Sep; do not build it
  next. **Why:** faster path to personal utility and to a demoable artifact, per priorities below.
  **Trade-off:** the ingress/webhook/Cloud Run research from 14 Sep sits unused for now — accepted
  as still valid when the mobile channel is picked back up later, not wasted work.
- **Decision:** Priority order is (1) personal utility tooling for the user's own manual
  estate-agent workflow, (2) a demoable version of the same (dashboard or a visual example of the
  agent completing a cost estimate — form not yet decided), (3) auth/login only once the system
  extends to invoicing/ledgers. **Why:** get immediate value from the user's own recurring manual
  work before investing in presentation or multi-user concerns. **Trade-off:** no shareable/
  demoable output until priority 2, which may matter if the user wants to show this to others
  sooner.
- **Decision:** The next prototyping focus is the evaluation and observability harness for the
  reported-issue → cost-estimate → find-contractors loop, built out from the plan already in
  `docs/specs/maintenance-agent-slice1-full-prototype.md` §9 (trace pretty-printer → error
  taxonomy → golden cases), rather than moving straight to a production web build. **Why:** user
  wants desired agent behaviour nailed down and made robust/observable before investing in a full
  production UI around it. **Trade-off:** delays any user-facing (even personal-utility) surface
  until the harness work is done — accepted since it de-risks the production build.
- **Decision (explicit scope note, not yet resolved):** all existing state-management work
  (`state_management_flow_prototype.py`, the SQLite schema in spec §7 — `issues`,
  `issue_artifacts`, `issue_turns`, `contractors`) stays in scope and must be carried into the
  harness/production work so updates and progress can be stored as the build continues. **Why:**
  user does not want to lose the state-persistence design already done. **Trade-off:** none
  identified — this was reconfirmed as still required, not re-litigated.

## Blockers

None. Planning/discussion session only.

## Next steps

1. **Scope the evaluation/observability harness** for the issue → cost estimate → find
   contractors loop. Two open questions raised but not yet answered:
   - **Path scope:** does the harness cover Paths C and D only (known-contractors / full-search,
     the paths that actually exercise contractor search), or all four paths (A triage-only, B
     needs-info, C, D) including path-selection correctness?
   - **Replay vs. live tools first:** start with real web-backed tool calls to observe genuine
     research quality and freeze good runs into fixtures, or hand-write golden cases first and
     develop against the replay suite from the start?
2. Once the harness scope is agreed, move to detailed prototyping of it (separate session/slice —
   user explicitly paused before going deeper here).
3. After the loop's behaviour is nailed down and the harness is robust, move that slice into a
   full production web build — carrying forward the existing state-management design.
4. Carried over, unchanged from 14 Sep: fake-tool-call gap with the `mercury` model; exact-name
   contractor matching risk in `find_or_create_contractor()`; deferred paths (triage-only,
   needs-info, landlord `reject` re-entry); real ingress classifier; whether to move the loop
   model to `claude-sonnet-5`; contractor-mutation tool design question; property-in-DB domain
   model (currently file-only); mobile approval shape; `ARCHITECTURE.md` still a placeholder now
   that there's also a prioritisation decision and an evaluation-harness plan to describe;
   `prototypes/README.md` update noting the preferred-contractor flow — still not done.

## Session 2 — Eval harness build (research_cost only)

Follows directly from the Session 1 decision above. Ran `/grill-me` first to scope the harness,
then built it.

### What was built

- `prototypes/cost_estimate_eval_harness.py` — new standalone script, single `research_cost`
  tool only (no contractors/state DB this slice). Reuses the `Trace` JSONL-logging pattern from
  `state_management_flow_prototype.py` but with no DB writes and no `pause()`/turn semantics.
  CLI: `single [--text "..."]` and `batch [--issues path.yaml] [--sample N]`.
- `prototypes/synthetic_issues.yaml` — 34 fixture issues: 28 realistic across trades (plumbing,
  electrical, heating, appliances, windows/doors, roofing/structural, damp/pest, flooring,
  drainage, general, plus the original gas-hob issue), 4 deliberately vague (clarify-path), 2
  adversarial/injection-style.
- System prompt rewritten to the more general, tool-agnostic style used in
  `state_management_flow_prototype.py` (goal → tools → rules), not a rigid two-branch script —
  intended to extend cleanly when `find_contractors` etc. are added later.
- Output format changed mid-build at user request: cost estimates require both an absolute
  **Best estimate: £N** and a **Range: £low-£high**, not a range alone.
- CSV output simplified twice at user request. Final schema (one row per issue run, written to
  `prototypes/logs/eval_results_<run_id>.csv`, gitignored): `id, issue_text, trace_pretty,
  cost_run_usd, latency_s, tool_calls_count, sources_found_count, sources_found,
  assert_sources_found_ge_2, assert_cost_estimate_present`. `trace_pretty` embeds a full
  human-readable transcript of the run directly in the row (via new `pretty_print_trace()`) so
  runs can be reviewed without opening the separate `.jsonl` file.
- `latency_s`: wall-clock seconds from the first model call to the final agent response (or to a
  forced `MAX_ROUNDS` stop), stored per row — added because latency review matters for this
  harness and wasn't being captured.
- CSV filename now includes the run's `run_id` (`eval_results_<run_id>.csv`) so a `single` run no
  longer silently overwrites a prior `batch` run's CSV (both wrote to the same fixed path
  originally).
- Live console printing restored (round-by-round model text, tool calls/results, per-call usage,
  run totals) — was dropped when adapting the loop from the reference scripts, then re-added
  after review was harder without it.

### What was explored / learnt

- **`research_cost` returning empty findings, 3x in a row → model fell back to a clarifying
  question.** Root cause found via trace review: `research_cost()`'s sub-call used
  `max_tokens=2000` (copied from `cost_estimate_agent_openrouter_prototype.py`), but
  `mercury-2.5` spends completion tokens on hidden reasoning *before* the visible answer — trace
  showed `completion == reasoning` with empty content, i.e. the budget was exhausted before any
  answer text was written. Fixed by raising to `max_tokens=6000`, matching the sub-call budget
  already used for this model in `state_management_flow_prototype.py`. Confirmed fixed — same
  issue re-run then returned real findings with real source URLs.
- **`COST_RANGE_RE` regex missed en-dash ranges.** Model wrote `£90–£160` (en-dash), regex only
  matched a plain hyphen. Fixed with a Unicode dash character class
  (`[-‐-―]`/`[-‐-―]`).
- **`assert_cost_estimate_present` flaky-looking false negatives (run `4465c3d4`, 3 of 5 rows).**
  Root cause: model formatted answers as Markdown bold (`**Best estimate:** £225`), and the
  regex only allowed whitespace between the label's colon and `£`, not `**`. Not flaky model
  behaviour — a parsing bug. Fixed by allowing `[\s*_]*` between colon and `£` in both
  `BEST_ESTIMATE_RE` and `COST_RANGE_RE`. Verified against the three failing strings directly.
- **A `batch --sample 2` run hung** on `mercury-2.5` after the model swap conversation started.
  Not reproduced/diagnosed further this session — discussed general reasons OpenRouter calls can
  be slow/hang (extra proxy hop, provider load-balancing/failover, no prompt caching on
  pass-through, the web-search sub-call's own latency, reasoning-heavy models burning tokens
  before answering, low-traffic/new model slugs). User confirmed it's been worse than previous
  sessions generally, not model-specific. Was about to add a client-side request timeout
  (`REQUEST_TIMEOUT_S`) when the session ended for `/summarise-session` — **not yet applied**.
- Model was swapped mid-session from `inception/mercury-2.5` to
  `deepseek/deepseek-v4.1-flash-20260910` (both via OpenRouter) to test whether the hang was
  model-specific; not yet re-tested after the swap.

### Decisions and trade-offs

- **Decision:** Reuse the `Trace` JSONL-logging class from `state_management_flow_prototype.py`,
  but skip SQLite/state persistence for this slice. **Why:** logging is needed either way and
  reusing it satisfies the "state-management work must carry forward" decision from Session 1
  without pulling in DB/turn/pause complexity this slice doesn't need. **Trade-off:** none of
  this run's data lives in the issues/issue_artifacts schema yet — deferred to a later slice.
  (Resolved via `/grill-me`.)
- **Decision:** Model may signal "need more info" only as plain text (`Clarifying question:
  ...`), no dedicated tool, for this first slice. **Why:** keeps the tool set to one
  (`research_cost`) as requested. **Trade-off:** clarify-vs-estimate detection relies on text
  parsing rather than an unambiguous tool call — a `request_more_info` tool was explicitly noted
  as a possible follow-up, not built. (Resolved via `/grill-me`.)
- **Decision:** Automated assertions kept to structural checks only
  (`assert_sources_found_ge_2`, `assert_cost_estimate_present`); the other behaviour-spec checks
  (uncertainty quality, no extra narrative, adversarial relevance) were originally planned as
  blank manual-review CSV columns, then **dropped entirely** in the later CSV simplification
  request rather than kept as empty columns. **Why:** user judged the extra columns/assertions
  "don't seem to work as expected" and asked for a minimal, trustworthy set. **Trade-off:** the
  manual-review signal for judge-design (uncertainty quality, narrative bloat, adversarial
  relevance) is no longer captured anywhere in the CSV — would need to be re-added if wanted for
  the next review pass.
- **Decision:** `sample --N` added to `batch` for running a random subset instead of the full
  fixture file. **Why:** user wants to start small (tested with N=5, N=2) before a full run of
  34. **Trade-off:** none — straightforward addition.

## Blockers

- **`batch --sample 2` hung on `mercury-2.5`**, cause not diagnosed. Model was swapped to
  `deepseek/deepseek-v4.1-flash-20260910` to test around it, but the swap has not yet been
  re-tested — session ended before a successful run post-swap.
- No commits were made this session — `prototypes/cost_estimate_eval_harness.py`,
  `prototypes/synthetic_issues.yaml`, and `prototypes/prototype_agent_behaviour_spec.md` (the
  last pre-existing but untracked) are all currently untracked in git. CLAUDE.md calls for
  committing after each logical change; that didn't happen this session and should be caught up
  before further work, ideally split into a few logical commits (harness skeleton, prompt/output
  fixes, CSV simplification, synthetic fixtures) rather than one large one.

## Next steps

1. Add the client-side request timeout that was in progress when this session ended, so a stuck
   OpenRouter call fails fast instead of hanging.
2. Re-try a full run of all ~34 synthetic issues on `mercury-2.5` (confirm the model swap to
   `deepseek-v4.1-flash-20260910` was just for hang-diagnosis, or decide to keep it) → review
   `sources_found`/`assert_sources_found_ge_2` results in particular, decide whether the harness
   needs any changes or new evals at this stage.
3. Add the `find_contractors` tool and its loop; assess how/whether that extends the eval
   harness — likely needs more focus on path validity (research_cost → estimate vs.
   find_contractors → shortlist) than this single-tool slice did.
4. Trial one of the more sophisticated eval frameworks (deepeval, Braintrust, or LangSmith — free
   / open-source tiers only) as a quick comparison against the hand-rolled harness, once the
   above is stable.
5. Catch up git commits for this session's untracked files (see Blockers) before continuing.
6. Still carried over from Session 1 (item 4 above) — unchanged.
