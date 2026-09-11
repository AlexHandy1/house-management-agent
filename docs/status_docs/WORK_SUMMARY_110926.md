# Work Summary — 11 September 2026

Session goal: close out the state-management prototype's branch exploration by adding a
preferred/whitelist contractor flow — pre-seed HeatSave Services and DKM Plumbing and
Heating, and have the agent use them directly (skipping `find_contractors`) when they're a
good trade match for an issue, per next-step #4 from `WORK_SUMMARY_100926.md`.

Ran `/grill-me` first (per CLAUDE.md, new feature work) — conversationally, not via the
AskUserQuestion checklist UI (user asked for that explicitly; see Decisions).

## What was built

All changes in `prototypes/state_management_flow_prototype.py`:

- **Schema**: `contractors` is now a global table (dropped `issue_id`, added
  `preferred INTEGER NOT NULL DEFAULT 0`). New `issue_contractors(id, issue_id,
  contractor_id, created_at, UNIQUE(issue_id, contractor_id))` join table represents the
  many-to-many relationship (one contractor can serve many issues over time). New `meta(key,
  value)` table holds a per-DB-lifetime `run_id`.
- **`PREFERRED_CONTRACTORS`** — hardcoded list of the 2 seed contractors:
  - HeatSave Services, trade `plumbing/heating`, area `Levenshulme`, source
    `https://heatsaveservices.co.uk/`
  - DKM Plumbing and Heating, trade `plumbing/heating`, area `Stockport`, source
    `https://www.yell.com/biz/d-k-m-plumbing-and-heating-stockport-7379874/`
  - Both `contact: None` (only URLs were available).
- **`seed_preferred_contractors()`** — idempotent insert (skips if a `preferred` row with
  that name already exists); called from `init_db()`.
- **`init_db()`** — now also seeds the preferred contractors and prints a property.yaml
  confirmation line (`[init-db] property loaded: ...`). Property data itself is still not
  written to the DB — still read live from `property.yaml` every turn, unchanged.
- **`find_or_create_contractor()` + `link_contractor_to_issue()`** — replace the old
  `add_contractor()`. Find-or-create matches by exact `name`; linking is a no-op if the
  issue/contractor pair already exists in `issue_contractors`.
- **`record_contractor` tool** — signature unchanged; now does find-or-create-and-link under
  the hood instead of a plain insert, so it transparently handles both a freshly-found
  contractor and a preferred one already shown in STATE.
- **`rehydrate()`** — contractors block split into two labelled lists: "contractors already
  on this issue" (via the join) and "preferred contractors available (not yet used on this
  issue)" (preferred rows with no link to *this* issue; annotated `used on N other issue(s)`
  if linked elsewhere).
- **`cmd_show()`** — mirrors the same split (linked-to-this-issue vs.
  preferred-not-yet-used), tags preferred rows `[preferred]`.
- **System prompt** — step 2 (contractors) now reads: check preferred contractors in STATE
  first; if ≥2 match the issue's trade, use them via `record_contractor` and do **not** call
  `find_contractors`; only search if the preferred pool has fewer than 2 trade matches.
  Matching is on preferred-flag + trade only (not area/proximity) — explicit user
  instruction, single-property scope for now.
- **Trace / logging fix** (see Blockers-turned-fixed below): `Trace` now takes a `run_id`
  (from new `get_or_create_run_id()`, stored in `meta`) and writes to
  `logs/{run_id}/{issue_id}/turn_{n}.jsonl` instead of `logs/{issue_id}/turn_{n}.jsonl`.
  File opens in exclusive-create mode (`"x"`) instead of `"w"` as a second line of defence
  against silent overwrites.

## What was explored / learnt

### Domain model correction mid-design: contractors are many-to-many with issues

Initial instinct (mine) was to keep `contractors` issue-scoped and either duplicate a row per
issue or "claim" a preferred row for exactly one issue at a time. User caught this: "Our
domain model needs to be able to support one contractor to many issues" — a single-property
landlord can legitimately use the same contractor across many separate issues over time. Led
directly to the `issue_contractors` join-table design. Recorded as the right correction, not
scope creep — the original per-issue-only model would have silently broken the second time a
preferred contractor was needed on a second issue.

### Trace log overwrite bug — found and fixed during validation

While validating with fresh CLI runs, deleting `state_management_flow.db` and re-running
fixture issues reused issue ids 1/2, and `Trace` opened its file in `"w"` mode at
`logs/{issue_id}/turn_{turn_no}.jsonl` — silently overwriting yesterday's `logs/1/turn_1.jsonl`
etc. That file was cited as evidence in `WORK_SUMMARY_100926.md` ("Traces preserved at
`prototypes/logs/1/`") and is now unrecoverable. Root cause: turn/issue numbering is DB-local
and resets to 1 whenever the DB file is recreated, but the trace path only ever depended on
those DB-local numbers. Fixed with a per-DB-lifetime `run_id` (new `meta` table) nested into
the log path, plus exclusive-create file mode so any future path collision raises instead of
silently clobbering. Verified by deleting the DB and reporting a new "issue 1" — new trace
landed at `logs/416a39a3/1/turn_1.jsonl`, all three prior generations of logs
(`logs/1/`, `logs/2/`, `logs/96a856be/`) left untouched.

### Model-faithfulness gap: fake tool-call-shaped text instead of a real tool call

On the third test issue (a distinct shower/hot-water fixture, deliberately plumbing/heating
to test cross-issue contractor reuse), mercury's round-1 response was plain text containing a
literal `<tool_code>...</tool_code>` block listing `research_cost()` and two
`record_contractor(...)` calls — not real `tool_calls` on the API response. The loop correctly
detected `msg.tool_calls` was empty and nudged it; round 2 the model went straight to
`write_artifact`/`pause` without ever making the real tool calls. Result: `show 3` confirmed
zero rows in `issue_contractors` for that issue, even though the draft messages happened to
reference the correct contractor ids (`recipient_ref: "1"`/`"2"`) inferred from the STATE
dump. Functionally the mock send would still reach the right contractors, but the join table
—the actual provenance record—would be wrong. Same family of issue as the previously-logged
"blind parallel tool call" mercury behaviour. Not consistent: the very next fresh-DB run
(kitchen sink leak, issue 1) used real `record_contractor` tool calls correctly. Logged as an
open issue, not fixed this session (see Next steps).

### Validation runs (manual CLI, no automated tests — consistent with this file's existing
convention)

1. `init-db` — seeded correctly, idempotent on re-run (confirmed via direct SQL: still 2
   rows after a second `init-db`).
2. Hob issue (reconstructed text from the 10 Sep trace, reused per user request) — hit the
   preferred-contractor path as expected, no `find_contractors` call, both HeatSave and DKM
   linked and drafted for.
3. Electrics issue (no preferred match by design) — fell through to `find_contractors`
   correctly.
4. `approve 1` (first run) — sent to both preferred contractors, paused
   `AWAITING_CONTRACTOR_QUOTES`, as expected.
5. `approve 1` (re-run, to verify the trace fix) — correctly no-op'd back to
   `AWAITING_CONTRACTOR_QUOTES` (no new contractor reply to act on); new trace file created
   under a new `run_id` folder rather than overwriting the earlier one.
6. New shower/hot-water issue (issue 3, same DB) — surfaced the fake-tool-call gap above.
7. Fresh DB + new "issue 1" (kitchen sink leak) — confirmed the trace fix under the exact
   scenario that broke it (DB reset + reused issue id); also used real `record_contractor`
   calls correctly this time.

## Decisions and trade-offs

- **Decision:** `contractors` becomes a global table; add an `issue_contractors` join table
  for the many-to-many relationship, rather than a `preferred_contractors`-only table or an
  issue-scoped "claim" model. **Why:** contractors are one entity regardless of how they were
  sourced (found vs. preferred); a real domain model needs one contractor usable across many
  issues over time. **Trade-off:** touches more of the existing code (`rehydrate()`,
  `cmd_show()`, the insert path) than a simpler bolt-on table would have.
- **Decision:** `record_contractor` tool signature is unchanged; find-or-create-and-link logic
  moved entirely into the backend. **Why:** the agent already sees preferred contractors' exact
  names in STATE, so no new parameter is needed — keeps the tool surface stable.
  **Trade-off:** matching is by exact name string; a paraphrased name (e.g. "HeatSave" vs.
  "HeatSave Services") would create a duplicate row instead of reusing one. Accepted as a
  known risk for this prototype, not solved.
- **Decision:** Matching a preferred contractor to an issue is preferred-flag + trade only —
  explicitly **not** area/proximity. **Why:** user is not planning for (and isn't building for)
  multi-property landlords yet; a preferred contractor for the one managed property is
  preferred regardless of their registered address. **Trade-off:** `area` is stored but
  currently just descriptive metadata, not used in matching logic or the prompt's routing
  rule — worth revisiting if/when multi-property support is ever built.
- **Decision:** Preload step folded into the existing `init_db()` rather than a separate
  `seed-preferred` CLI command. **Why:** user explicitly wants `init-db` to model a future
  production "onboarding" step (schema + static reference data) in one place.
  **Trade-off:** `init_db()` now does two conceptually different things (schema DDL +
  reference-data seeding); acceptable for a throwaway prototype, worth splitting if this
  pattern moves toward production.
- **Decision:** Property data stays file-based (`property.yaml`, read live every turn), not
  moved into the DB as part of this "onboarding step" framing. **Why:** user's explicit call —
  storing property in the DB is its own future domain-model piece, out of scope here.
  **Trade-off:** `init_db()`'s property "loaded" confirmation is cosmetic (just checks the
  file exists and prints a line) rather than a real onboarding action.
- **Decision:** Validate by manual CLI run + trace/`show` inspection, no pytest suite.
  **Why:** consistent with how this file has been tested throughout (see 10 Sep session);
  explicit "quick spike" framing from the user. **Trade-off:** none of today's fixture runs
  are repeatable as regression tests — if this logic breaks later it won't be caught
  automatically.
- **Decision (process, not code):** run `/grill-me` conversationally rather than via the
  AskUserQuestion multiple-choice tool. **Why:** user explicitly asked to "chat through and
  discuss the options rather than going into that checklist mode" after the first two
  questions were posed as a checklist. **Trade-off:** none — just a format preference for this
  and future grill-me sessions on this project.

## Blockers

None currently blocking. Two open issues carried to Next steps (trace overwrite is fixed;
fake-tool-call gap is not).

## Next steps

1. Decide whether to harden against the fake-tool-call gap (mercury emitting a
   `<tool_code>` text block instead of a real tool call) — e.g. an explicit system-prompt
   rule ("you MUST invoke tools via the tool-calling mechanism, never as text"), or leave as
   a known model-faithfulness risk alongside the already-logged blind-parallel-tool-call
   behaviour. Not attempted this session (user chose to close instead).
2. Exact-name matching risk in `find_or_create_contractor()` — no safeguard against a
   paraphrased contractor name creating a duplicate row. Worth a fuzzy-match or normalized-key
   approach if this moves beyond spike stage.
3. Test the remaining deferred paths noted on 10 Sep with no code change: triage-only,
   needs-info (`AWAITING_TENANT_INFO`), landlord `reject` re-entry.
4. Prototype the real ingress classifier (inbound text → typed `events` row) as its own
   small piece.
5. Decide if/when to move the loop model to `claude-sonnet-5` — mercury's blind-parallel-tool
   -call and fake-tool-call behaviours are both recurring friction with this model choice.
6. Future domain-model question raised but deliberately deferred: whether `record_contractor`
   /contractor-mutation logic should stay as individual predicted tools (e.g. a future
   `update_contractor`) or whether the agent should get more autonomy to navigate the DB with
   its own generated code, so every update path/case doesn't need to be hand-predicted. Not a
   decision for this prototype stage.
7. Property-in-DB domain model (currently file-only) — explicitly deferred, not urgent.
8. Still open from earlier sessions: mobile approval shape; eval + observability harness;
   OpenRouter `web` plugin inconsistency; real project `README.md`; update `ARCHITECTURE.md`
   (still a placeholder — now overdue given there's a real state model, deployment decision,
   and domain model to describe).
9. `prototypes/README.md` needs a short update noting the preferred-contractor flow addition
   to `state_management_flow_prototype.py` (not done this session).
