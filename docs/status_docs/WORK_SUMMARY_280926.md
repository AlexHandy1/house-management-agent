# Work Summary — 28 September 2026

Branch: `build_out_issue_agent_functionality` (not pushed; PR planned only after the deployment
steps below). Slice: research-cost agent + issues DB + minimal UX. Full design in
`docs/specs/spec-architecture-research-cost-agent-and-issues-db-280926.md`.

## What was built

Backend agent + DB layer, proven live locally. **Not yet wired into the API or frontend, and
nothing deployed** — `routers/issue.py` still calls the old `respond_to_issue`.

- **Spec** — `docs/specs/spec-architecture-research-cost-agent-and-issues-db-280926.md` (via
  `/create-technical-spec`, after `/grill-me`). Revised through the session: custom VPC,
  agent-driven writes, `save_*` tool names, prod DB password never in repo.
- **Local Postgres** — `docker-compose.yml` (throwaway local-only credentials), `DATABASE_URL` in
  `app/backend/.env.example`, `psycopg[binary]` + `pyyaml` in `requirements.txt`, `types-PyYAML`
  in `requirements-dev.txt`. `tests/conftest.py` gained a `database_url` fixture (creates
  `house_mgmt_test`, truncates `issues` at the start of each test).
- **`models/agent_outcome.py`** — `AgentOutcome` pydantic model (`models/` package, as in
  nature-quest).
- **`services/issues_db.py`** — Postgres layer: `init_schema()`, `save(source_text, outcome)`,
  `list_issues()` (newest first), `get_database_url()` (env only so far). `issues` table:
  `id, source_text, status (done|needs_info|failed), cost_best/low/high, supporting_web_sources
  jsonb, clarifying_question, created_at, updated_at`. Tests: `tests/test_issues_db.py` (3).
- **`services/agent.py`** — `run_agent(issue_text, client, save)`: ReAct loop (`MAX_ROUNDS=10`)
  with tools `research_cost` (web-plugin sub-call, `max_tokens=6000`), `save_cost_estimate`,
  `save_clarifying_question`. The two `save_*` tools write via the injected `save` and end the
  run; if the model stops without saving, the runtime saves a `failed` outcome. Sources are
  collected by the runtime from `research_cost` results (never model-supplied), deduped, sorted.
  Real system prompt (`AGENT_SYSTEM_PROMPT_TEMPLATE`) with property grounding from
  `config/property.yaml` (copied from `prototypes/property.yaml`). Tests: `tests/test_agent.py` (4).
- **Langfuse tracing** — `build_client()` now returns `langfuse.openai.OpenAI` (traces every model
  call incl. the sub-call); `run_agent` wraps the loop in a parent `run_agent` span so a run is
  one trace. Test in `tests/test_agent_observability.py`.
- **First live evals** — `tests/evals/test_agent_eval.py` (`-m eval`, real model + web search).
  Currently run with a capturing `save` (no DB). Result, 28 Sep: both pass in 17.6s. Clear issue
  (dripping tap) → `done`, best £95, range £60–£150, 5 real sources (incl. a Levenshulme one);
  vague issue → `needs_info` with a specific clarifying question. Traces confirmed in Langfuse:
  2 traces, root `run_agent` span, nested generations (3 for the clear issue, 1 for the vague).
- 25 backend tests pass; `ruff check` and `mypy` clean. Commits `6953a34`…`b21ef30`.

## What was explored / learnt

- **Compute Engine API is not enabled** on the GCP project (checked with gcloud), so whether a
  default VPC exists is unverified; enabling it auto-creates a `default` network with SSH/RDP open.
- **Local env:** Docker daemon was down at first; Homebrew `postgresql@14` is broken (missing
  `icu4c` dylib). Used Docker Postgres 16 instead.
- **Nothing from the evals is in Postgres** (checked after the eval run): the dev DB `house_mgmt`
  has no `issues` table (`init_schema()` isn't called anywhere in the app yet); `house_mgmt_test`
  holds 3 leftover `failed` rows from `test_issues_are_listed_newest_first` (the fixture truncates
  at test start, not end).
- **Langfuse legacy traces API is unavailable for new orgs** (`GET /api/public/traces` → 410
  `LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`). Use `lf.api.observations.get_many(from_start_time=…,
  to_start_time=…, fields="core,basic")` instead. Also `load_dotenv()` with no path fails when the
  script comes from stdin — pass `".env"`.
- **Langfuse drop-in client alone gives one trace per model call**; a parent span is what groups a
  run into a single trace. Generations are all named `OpenAI-generation` (tool steps not
  distinctly named) — improvable via a `name=` kwarg.
- **mypy vs OpenAI SDK:** tool calls are a union (function | custom) — narrow with
  `if call.type != "function": continue`; test doubles must set `type="function"`. Use the SDK
  param types (`ChatCompletionFunctionToolParam`, `ChatCompletionMessageParam`, …).
- ruff `FURB157`: `Decimal(225)` not `Decimal("225")`. `ruff format --check` would reformat 11
  existing files; CI only runs `ruff check`, so left alone.
- **Reviewer claim assessed:** "cross-region private traffic needs GLOBAL routing mode on default
  VPCs" — my read is that subnet routes within a VPC are global regardless of routing mode (mode
  affects dynamic/BGP routes). Unverified until the Compute API is enabled; the custom VPC sets
  GLOBAL explicitly anyway.
- **Dead ends / set aside:** runtime-only writes with the prototype's regex extraction
  (simpler, but agent can't drive state changes); `conclude_estimate`/`request_info` names (hid
  the DB write); using the auto-created `default` VPC (would need import-and-destroy of its open
  SSH/RDP rules); an `agent_outcome` module under `services/` (moved to `models/`).

## Decisions and trade-offs

- **Decision:** Postgres on a free-tier `e2-micro` in `us-central1`, private IP, Cloud Run
  reaching it via Direct VPC egress. **Why:** data isn't sensitive; ~100ms/query is negligible
  against tens-of-seconds agent runs. **Trade-off:** cross-region egress charge (pennies) and a
  ~$3–4/month external IPv4 charge the free tier is believed not to cover (`[NEEDS INPUT]` in spec).
- **Decision:** dedicated custom VPC (GLOBAL routing, subnets in europe-west1 + us-central1), not
  the `default` network. **Why:** no permissive default rules to import/destroy; only our two
  firewall rules exist. **Trade-off:** plan non-overlapping IP ranges up front; slow subnet
  release on teardown; the unused `default` network still exists (footgun for future VMs).
- **Decision:** production DB password never in the repo/tfvars/Terraform state/VM metadata;
  VM's own service account fetches it from Secret Manager at boot. **Why:** repo is open source.
- **Decision:** `issues` holds concluded work only — `done | needs_info | failed`, written once;
  no `running`, `agent_reply`, `error`, `cost_basis`. Kept `clarifying_question`. **Why:** it's the
  agent's scratchpad and the landlord's list, not observability (Langfuse covers that).
- **Decision:** the agent drives the DB write via explicit tools (`save_cost_estimate`,
  `save_clarifying_question`, descriptions say they write to the issues database); write+end
  coupled. Runtime writes only `failed`, guaranteeing exactly one row per run. **Why:** stress-test
  that the architecture supports agent-in-the-loop state changes from a simple base, as in
  `state_management_flow_prototype.py`. **Trade-off:** one tool handler per outcome; the handler
  is still runtime code the agent invokes.
- **Decision (OPEN — to be revisited next session):** `save` is injected into `run_agent`
  (`Save = Callable[[str, AgentOutcome], Any]`) so evals could stop before the DB write. **User's
  view at end of session:** evals should ultimately write to the test DB — otherwise the
  save step isn't really tested, and the injection adds complexity just to treat evals differently
  from production. This reverses the earlier "evals stop before the DB write" requirement (spec
  REQ-009 and section 1 still describe the capturing-`save` design and need updating if adopted).
  If evals use the real `issues_db.save`, the injected `Save` param may be unnecessary (unit tests
  could still fake it, or point at the test DB instead).
- **Decision:** unit tests for the agent are deliberately minimal (scripted `MagicMock`, no
  helper module) — only paths live evals can't cover. **Why:** user asked for the simplest set.
- **Decision:** synchronous `POST /api/issue` (no polling/async) for this slice.
- **Decision:** naming — `issues_db` (not `issues_repo`), `models/agent_outcome.py`.

## Blockers

None blocking. Open: `[NEEDS INPUT]` on the external-IPv4 charge in the spec; Compute API not yet
enabled and nothing applied (Terraform not yet written).

## Next steps

1. **Decide the eval/DB boundary** (see the open decision above): likely point the evals at the
   test DB using the real `issues_db.save`, then simplify or drop the injected `Save`, and update
   spec REQ-009/section 1. Also make the test fixture clean up after each test, not just before.
2. **REQ-004/REQ-006 gaps in `run_agent`:** provider errors and empty `choices` currently
   propagate as exceptions instead of saving `failed`; and the estimate isn't validated at all —
   an inverted range (`low > best`) would be saved as `done`. Add validation with tool-error
   bounce/retry, plus the empty-choices retry from the prototype (`_create_with_retry`).
3. **Wire the API:** `POST /api/issue` → `run_agent(..., save=issues_db.save)` returning the
   outcome; `GET /api/issues`; `init_schema()` at startup; `DATABASE_URL` from Secret Manager when
   `K_SERVICE` is set. Remove `respond_to_issue` and its tests once unused.
4. **Grow the evals** to 5–6 issues from `prototypes/synthetic_issues.yaml` (incl. adversarial).
5. **Frontend:** thinking state, success/needs-info/failed states, issues table.
6. **Local end-to-end** with `/agent-browser` against local Postgres.
7. **Infra + docs:** Terraform (`network.tf`, `database.tf`, Cloud Run `vpc_access`, secret,
   `compute.googleapis.com`), ADR-004, `ARCHITECTURE.md`/README updates (not yet changed — the
   agent isn't live), and a **Postgres service in CI** (the backend job currently has none, so
   `test_issues_db.py` would fail there).
8. **Live testing on the deployment** after a manual `terraform apply`; fold findings back into
   tests. Check Langfuse delivery on Cloud Run (CPU throttling after response may drop batched
   traces; fix is an explicit flush).
9. Name the Langfuse generations (`research_cost` vs loop turns) for a more readable trace.
10. Housekeeping: `docs/status_docs/WORK_SUMMARY_230926.md` has uncommitted edits from before this
    session; the earlier logging-fix step (PR/merge, re-check Cloud Logging) from that summary is
    still outstanding. Run `/simplify` before closing the slice.
