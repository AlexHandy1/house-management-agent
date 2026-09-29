# Work Summary — 29 September 2026

Branch: `build_out_issue_agent_functionality`, 24 commits ahead of `main`, not yet pushed/merged.
Continues the 28 Sep slice (research-cost agent + issues DB); this session finished wiring it
end-to-end and deployed the supporting cloud infra.

## What was built

- **`run_agent` hardening** (`services/agent.py`) — catches `OpenAIError` and retries once on an
  empty-`choices` provider response (`_create_with_retry`, `ModelCallFailed`) before saving a
  `failed` outcome instead of raising. Tests in `tests/test_agent.py`.
- **API wired to the real agent** (`routers/issue.py`) — `POST /api/issue` now calls
  `run_agent(..., save=issues_db.save)` and returns the `AgentOutcome`; added `GET /api/issues`.
  Removed `respond_to_issue` and its tests/eval. `init_schema()` runs once on startup via a
  FastAPI `lifespan` handler (`main.py`) rather than at import time, so tests that import `main`
  without a DB configured still work.
- **Live evals grown to 6** (`tests/evals/test_agent_eval.py`) — 2 clear issues, 2 vague, 2
  adversarial (pure prompt injection; injection alongside a real issue, asserts no leaked
  content). All 6 pass. Run via `python -m pytest -m eval tests/evals/test_agent_eval.py -s`
  (must use `python -m pytest`, not bare `pytest` — bare `pytest` doesn't put `app/backend` on
  `sys.path` from this directory, causing `ModuleNotFoundError: No module named 'main'`).
- **Full research summary surfaced** (`models/agent_outcome.py`, `services/agent.py`,
  `services/issues_db.py`, frontend `App.tsx`) — `AgentOutcome.summary` carries the
  `research_cost` findings text (parts/labour breakdown, sources) — not the closing message
  content, which is often empty (see Dead ends below). Persisted as `issues.agent_summary`,
  rendered below the headline cost estimate in the frontend.
- **Frontend states** (`app/frontend/src/App.tsx`) — thinking (disabled button, "Researching
  costs…"), success (headline + full summary), needs-info (clarifying question), error (failed
  outcome or network failure) states; an issues table loading on mount and refreshing after each
  submit. `tests/setup.ts` gained a default `fetch` stub so the table's mount effect doesn't hit
  a real network call in every test.
- **Real-browser e2e test** (`tests/e2e/test_issue_flow_e2e.py`) — drives the running app via the
  `agent-browser` CLI (`--headed`) through a real submission: fills the form, waits for the
  result, asserts the `.agent-summary` text is substantial (regression guard for the summary bug
  below), asserts the issue appears in the `<table>`. New `e2e` pytest marker (excluded by
  default like `eval`). Run via `python -m pytest -m e2e tests/e2e/test_issue_flow_e2e.py -s`
  with Postgres/backend/frontend already running locally. Passing.
- **CI Postgres service** (`.github/workflows/ci-cd.yml`) — `unit-tests-backend` had no database,
  so `test_issues_db.py` and the `GET /api/issues` test would have failed there. Added a
  `postgres:15` service container.
- **Cloud DB infrastructure, applied live**:
  - `infra/network.tf` — dedicated custom VPC (`house-mgmt-vpc`, GLOBAL routing, no default
    rules), two subnets: `house-mgmt-run` (europe-west1, `10.10.0.0/24`, Cloud Run's Direct VPC
    egress) and `house-mgmt-db` (us-central1, `10.20.0.0/24`, `private_ip_google_access = true`).
  - `infra/database.tf` — `house-mgmt-db` VM (`e2-micro`, Debian 12, Postgres via apt), its own
    service account (`house-mgmt-agent-db`) with `secretAccessor` on `DATABASE_PASSWORD` only,
    firewall rules (`tcp:5432` from the run subnet only, `tcp:22` from the IAP range
    `35.235.240.0/20` only). External IP is **not permanent** — gated behind
    `var.db_vm_bootstrap_internet_access` (default `false`); attached only for the one-time
    `apt-get install postgresql`, then removed. Ongoing password refresh goes over free Private
    Google Access.
  - `infra/cloud_run.tf` — `vpc_access` (Direct VPC egress, `PRIVATE_RANGES_ONLY`), non-secret
    `DB_HOST`/`DB_NAME`/`DB_USER` env vars.
  - `infra/secret_manager.tf` — added `DATABASE_PASSWORD` to `backend_secret_names` (grants both
    Cloud Run's and the DB VM's service accounts `secretAccessor`).
  - `services/issues_db.py` — `get_database_url()` now mirrors `resolve_api_key()`'s `K_SERVICE`
    switch: assembles a DSN from Secret Manager + the three env vars on Cloud Run, reads
    `DATABASE_URL` directly locally. Unit test mocks `google.auth`/`secretmanager`.
  - `docs/decisions/ADR-004-issues-database-hosting.md` — full reasoning (self-managed VM vs.
    Cloud SQL, custom VPC vs. default network, PG15 vs. PGDG-repo PG16, snapshot backups
    deferred, credential resolution).
- **Postgres aligned to 15 everywhere** — `docker-compose.yml`, CI, and the VM's distro-default
  apt package all now Postgres 15 (was 16 locally) — avoids adding a third-party apt repo on the
  VM purely to chase 16, and keeps all three environments identical.
- **Live apply verified**: VPC, both subnets, the DB VM, firewall rules, `DATABASE_PASSWORD`
  secret + both IAM bindings, Cloud Run's `vpc_access`/env vars all created and confirmed live.
  SSH via IAP tunnel confirmed working; `house_mgmt` DB and `house_mgmt_app` role confirmed to
  exist with correct grants (`\l`, marker file `/var/lib/house-mgmt-db-provisioned` present).
- **Docs updated** (`/documentation-and-adrs`): `ARCHITECTURE.md` — new agent/issues-DB
  components, updated request flow (`POST/GET /api/issue(s)`), a Mermaid network diagram
  (Cloud Run ↔ IAP ↔ VPC ↔ DB VM ↔ Secret Manager), deploy-flow note on `gcloud run deploy`
  vs. Terraform field ownership. `README.md` status section updated. `services/issues_db.py`
  gained an inline note on the `CREATE TABLE IF NOT EXISTS` migration limitation.

## What was explored / learnt

- **Real bug found while applying infra**: the DB VM's `metadata_startup_script` computed
  `PG_CONF_DIR=$(find /etc/postgresql ...)` *before* `apt-get install postgresql` — `/etc/postgresql`
  didn't exist yet, so `find` failed, and `set -euo pipefail` aborted the script immediately,
  before installing Postgres or creating the database/role at all. Fixed by moving the `find`
  inside the marker-guarded block, after the install line. Confirmed via
  `gcloud compute instances get-serial-port-output`. `metadata_startup_script` changes force a
  full instance replace (not an in-place update) in the `google_compute_instance` resource —
  confirmed via `terraform plan`; safe here since the broken VM never held any data.
- **`DATABASE_PASSWORD` secret conflict**: the user created the secret manually (container +
  value together) before this session's `terraform apply`; Terraform's own
  `google_secret_manager_secret.backend["DATABASE_PASSWORD"]` then failed with `409: already
  exists`. Fixed via `terraform import 'google_secret_manager_secret.backend["DATABASE_PASSWORD"]'
  projects/house-management-agent/secrets/DATABASE_PASSWORD`, then re-applied to pick up the two
  IAM bindings that had been skipped due to the failed dependency.
- **GCP external IPv4 pricing** (verified via web search, not assumed): $0.005/hr for *any*
  external IPv4 (ephemeral or static) while attached to a running standard VM — ≈$3.65/month,
  confirming the spec's original `[NEEDS INPUT]` estimate. This was almost accepted as an
  unavoidable permanent cost for the DB VM before realising the VM's only genuine need for
  internet (not just Google APIs) is its one-time package install — see the
  `db_vm_bootstrap_internet_access` toggle above. Cloud NAT was checked and rejected as an
  alternative: its own gateway charge (~$0.044/hr, ~$32/month) is meaningfully *more* expensive
  than just keeping the external IP.
- **`gcloud run deploy --image=...` is a partial update** — confirmed by reading the CI/CD
  workflow directly: it only touches the `image` field, never resets `vpc_access` or env vars
  Terraform manages, and Terraform's `lifecycle.ignore_changes` on the image means the two
  systems never fight over the same field. This meant the Terraform-then-deploy ordering
  (infra first) isn't a strict correctness requirement, just avoids a wasted crash-looping
  deploy if the new image reaches Cloud Run before `DB_HOST` etc. are set.
- **`pytest` vs `python -m pytest`**: bare `pytest` invoked from `app/backend` doesn't add that
  directory to `sys.path` (pytest's rootdir-insertion logic lands on `tests/`, not its parent),
  causing `ModuleNotFoundError: No module named 'main'` in `conftest.py`. `python -m pytest`
  works because it adds the invocation directory itself. User decided not to fix this via
  `pythonpath = .` in `pytest.ini` — just use `python -m pytest` going forward.
- **RTL `getByText` matches `<textarea>` content** — a controlled textarea's initial text node
  can still match `screen.getByText()`, causing "found multiple elements" failures when the
  submitted issue text also appears in a rendered table row. Fixed by scoping queries with
  `within(screen.getByRole('table'))` rather than a bare `findByText`.
- **Docker Postgres image swap**: recreating the local `docker-compose` Postgres container
  (16 → 15) requires dropping the named volume (`docker volume rm
  house-management-agent_pgdata`) for a clean re-init, and restarting any running `uvicorn`
  process afterward so its `lifespan` handler re-runs `init_schema()` against the fresh,
  empty database.

## Decisions and trade-offs

- **Decision:** dropped the REQ-006 cost-range validation (`0 ≤ low ≤ best ≤ high` bounce-back)
  entirely rather than building it. **Why:** never observed in prototyping or the 6 live evals;
  user explicitly rejected the added retry-loop complexity for a failure mode with no evidence.
  Spec marked `DEFERRED, 29 Sep`.
- **Decision:** `AgentOutcome.summary` is sourced from the `research_cost` tool's findings text
  (tracked across the loop as `findings_text`), not the model's closing message content.
  **Why:** the closing message accompanying `save_cost_estimate` is frequently empty/thin in
  practice (models tend to call the write tool with little prose once ready) — confirmed via a
  live browser test that initially showed nothing rendered. The rich narrative text the user
  expected matches `_research_cost()`'s own prompt/output shape exactly.
- **Decision:** self-managed Postgres VM (not Cloud SQL), dedicated custom VPC (not `default`
  network), Postgres 15 everywhere (not 16 via a PGDG repo), non-superuser `house_mgmt_app` role,
  snapshot backups deferred. **Why/trade-off:** see `docs/decisions/ADR-004-issues-database-hosting.md`
  in full — all driven by "simplest option first" at single-user personal-app scale.
- **Decision:** DB VM's external IP is bootstrap-only (`db_vm_bootstrap_internet_access` var,
  default `false`), not permanent. **Why:** the ongoing need (Secret Manager access for the
  every-boot password refresh) is free via Private Google Access; only the one-time package
  install needs general internet. **Trade-off:** VM recreation requires a manual two-apply
  bootstrap dance (documented in the session but not yet written into `infra/README.md` — see
  Next steps).
- **Decision:** when a `psycopg2`-style `CREATE TABLE IF NOT EXISTS` schema needs an actual
  column change, drop and recreate the local dev table by hand (done twice this session) rather
  than building migration tooling now. **Why:** no production data yet exists to protect.
  **Trade-off/future plan:** the moment production holds real data, switch to hand-rolled
  numbered SQL migration files + a `schema_migrations` tracking table (discussed in detail;
  rejected Alembic as unnecessary ORM-coupled machinery for this app's size). Noted inline in
  `services/issues_db.py` and as a general principle, not yet written up as its own ADR.
- **Decision:** `ARCHITECTURE.md` deliberately excludes forward-looking "what's deferred" status
  — user directed it to reflect only what's actually built and live; that kind of status
  belongs in work summaries/specs, not the architecture map.

## Blockers

None currently blocking. Open items below are next steps, not blockers.

## Next steps

1. **Merge to `main`** — branch is ready (24 commits, all tests passing, infra live and
   verified) but not yet pushed. Was mid-decision on push-and-PR vs. direct push when the
   session moved to documentation; needs a decision next session.
2. **Deploy the real image**: once merged, CI/CD's `deploy` job builds and pushes the actual
   agent code to the already-DB-wired Cloud Run service. Test the live app through the Cloud Run
   URL (behind IAP sign-in) — submit a real issue, confirm it researches, saves, and shows in
   the table against the production DB VM.
3. ~~Document the DB VM bootstrap dance in `infra/README.md`~~ — done this session, once proven
   working twice (initial bootstrap + the startup-script bugfix re-bootstrap).
4. **Revisit the eval/DB boundary** (evals use a capturing `save`, not `issues_db.save`) — still
   open from 28 Sep, explicitly deferred again this session ("stick with the current boundary...
   revisit once we have the full, implemented picture").
5. Review SQL startup fix (see `/security-reviewer` output).
6. **Review logging** to confirm it reflects this session's changes (new agent tool calls, DB
   operations, the issues API) — not otherwise checked this session beyond confirming issue text
   itself is never logged (CON-004).
7. Name Langfuse generations (`research_cost` vs. loop turns) for readability — low priority,
   carried from 28 Sep.
8. Consider `roles/logging.logWriter` for the DB VM's service account — its guest agent currently
   logs permission-denied noise to serial console (harmless, but clutters startup-script
   debugging).

## Known scalability questions/concerns

Not blockers, but worth deliberately revisiting before this grows much further:

- **Agent tool-call handling is a fixed conditional chain, not a registry.** `_run_loop`
  (`services/agent.py`) dispatches `research_cost`/`save_cost_estimate`/`save_clarifying_question`
  via a hardcoded `if name == ... elif name == ...` chain, and the two `save_*` branches each
  build a specific `AgentOutcome` shape and immediately end the loop. Adding a fourth tool (e.g.
  `find_contractors`, already in the PRD's future scope) means editing this chain directly,
  not registering a new handler — there's no abstraction separating "what tools exist" from
  "how the loop dispatches them." Fine at 2 write-tools; worth a rethink before it's 4+.
- **`issues_db` presumes one issue, one table, one purpose** — the module (and its schema) is
  built around a single `issues` table being the entire database's reason to exist, not one
  table among several in a shared application database. If a future slice adds
  tenants/contractors/leases/etc. as their own tables in the same Postgres instance, the current
  shape (one module = one table = all the schema/query logic) won't naturally extend — worth
  deciding now whether future tables get their own `services/<name>_db.py` modules following
  this same pattern, or whether this gets restructured around a shared connection/session
  layer with per-table modules underneath it, before the second table shows up.
