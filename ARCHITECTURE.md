# Architecture

Whole-system map for the Phase 1 MVP scaffolding (`docs/prds/production-v1-prd-200926.md`).
Points to ADRs/specs for full reasoning rather than restating it.

## Components

- **`app/frontend`** — Vite/React/TypeScript single-page app. A form
  submits an issue and shows a thinking/success/needs-info/error state per
  the agent's outcome (including its full research findings, not just the
  headline cost), plus a table of previously saved issues loaded on mount
  and refreshed after each submit. `vitest` + `@testing-library/react` for
  tests.
- **`app/backend`** — FastAPI. Routers (`routers/`) handle HTTP; services
  (`services/`) hold the actual logic — the agent loop (`services/agent.py`),
  the issues database layer (`services/issues_db.py`), rate limiting,
  Langfuse config, IAP identity verification. `pytest` for tests, with
  `eval` (real LLM calls, see ADR-003) and `e2e` (real browser + full
  stack, `tests/e2e/`) markers separating them from the default fast run.
  In production, also serves the frontend's built static files
  (`fastapi.staticfiles`) from a single Docker image/Cloud Run service —
  there is no separate frontend server in production.
- **The research-cost agent** (`app/backend/services/agent.py`) —
  `run_agent()`: a ReAct loop (OpenRouter, Mercury 2.5) with three tools —
  `research_cost` (web-search sub-call), `save_cost_estimate`, and
  `save_clarifying_question`. Exactly one of the two `save_*` tools ends
  the run and writes the result via an injected `save` function (production
  passes `issues_db.save`; evals pass a capturing function, so assertions
  run against the returned `AgentOutcome` before any DB write). A
  runtime-only `failed` write covers provider errors, empty responses, or
  the model stopping without saving. See
  `docs/specs/spec-architecture-research-cost-agent-and-issues-db-280926.md`
  for the full design and REQ-by-REQ status.
- **The issues database** — Postgres on a dedicated, free-tier Compute
  Engine VM, reachable only over a private VPC (see the network diagram
  below). `services/issues_db.py`: `init_schema()` (run once, on app
  startup, via a FastAPI lifespan handler), `save()`, `list_issues()`. See
  ADR-004 for the full hosting/network/credential-resolution reasoning.
- **`infra/`** — Terraform. Provisions Cloud Run, Artifact Registry, Secret
  Manager, IAP + its IAM bindings and audit logging, GitHub Actions'
  Workload Identity Federation, and (as of 29 Sep) the issues-DB VM and its
  dedicated VPC. See `infra/README.md` for the bootstrap sequence
  (including the one-time manual steps Terraform can't do, and the DB VM's
  two-apply bootstrap dance) and ADR-001/ADR-002/ADR-004 for the reasoning.
- **`.github/workflows/ci-cd.yml`** — lint/typecheck → unit tests (with a
  Postgres service container) → Docker build → (on push to `main` only)
  deploy to Cloud Run. See ADR-001.
- **`prototypes/`** — throwaway prototyping, explicitly not production
  code (see `prototypes/README.md`). `services/agent.py`'s real tools and
  system prompt were built from these prototypes' proven patterns
  (cost-research prompt, write-tool-ends-the-loop shape), not a direct
  port.

## Request flow (production)

1. Browser requests the Cloud Run URL.
2. **IAP** (Cloud Run native integration) intercepts the request before it
   reaches the container, for every path. Not authenticated yet → redirect
   to Google sign-in. Authenticated but not the authorized owner account →
   403, request never reaches the app. See ADR-002 for the full mechanism
   and why this holds even with the source fully public.
3. Authorized request reaches FastAPI. A middleware logs the verified
   caller identity (from the `X-Goog-IAP-JWT-Assertion` header) for
   observability — this is logging only, not an access-control decision;
   that decision was already made in step 2.
4. `GET /` (or any non-API path) → static frontend files. `POST /api/issue`
   → rate-limited (per-IP), 2000-character-capped issue text → `run_agent()`
   (`services/agent.py`), traced as a single Langfuse `run_agent` span
   nesting every model/tool call. The agent researches (or asks a
   clarifying question), writes exactly one row to the issues database via
   `issues_db.save()`, and the resulting outcome is returned as the
   response — the row is already saved by the time the HTTP response
   arrives, not written separately by the router. `GET /api/issues` lists
   all saved issues, newest first; the frontend calls this on mount and
   again after every submit.
5. Reaching the issues database: Cloud Run has Direct VPC egress into a
   dedicated private subnet: see the network diagram below.

## Network (Cloud Run ↔ issues database)

```mermaid
flowchart TB
    Browser(["Browser"]) -->|"HTTPS, Google sign-in"| IAP["Cloud IAP"]
    IAP -->|"authorized account only"| CloudRun

    subgraph VPC["house-mgmt-vpc — custom, GLOBAL routing, no default rules"]
        subgraph RunSubnet["house-mgmt-run — europe-west1 — 10.10.0.0/24"]
            CloudRun["Cloud Run service\n(Direct VPC egress)"]
        end
        subgraph DbSubnet["house-mgmt-db — us-central1 — 10.20.0.0/24\nPrivate Google Access: on"]
            DbVM["house-mgmt-db VM (e2-micro)\nPostgres 15 — no external IP"]
        end
        CloudRun -->|"tcp:5432\nfirewall: from run subnet only"| DbVM
    end

    DbVM -.->|"Secret Manager API\nvia Private Google Access\n(every boot: refresh DB password)"| SecretMgr[("Secret Manager\nDATABASE_PASSWORD")]
    CloudRun -.->|"Secret Manager API\n(build DATABASE_URL)"| SecretMgr
    Operator(["Operator"]) -.->|"IAP TCP forwarding\ntcp:22, firewall: from 35.235.240.0/20 only"| DbVM
```

The DB VM has **no permanent external IP** — external IPv4s cost money
while attached, and the only genuine need for one is the VM's one-time
`apt-get install postgresql` at first boot (Debian's package mirrors
aren't a Google API, so Private Google Access doesn't cover them). That
IP is attached only for a deliberate one-time bootstrap apply
(`var.db_vm_bootstrap_internet_access`, see `infra/README.md`), then
removed; everything the VM does afterward (the every-boot password
refresh) goes over free Private Google Access instead. See ADR-004 for
the full reasoning, including the alternatives considered (Cloud SQL, the
auto-created `default` network, Cloud NAT).

## Deploy flow

Terraform provisions everything except the deployed app image itself
(`lifecycle.ignore_changes` on the Cloud Run image field). A push to `main`
triggers GitHub Actions: build the Docker image (bundles the frontend build
into the backend's static files, see `app/backend/Dockerfile`), push to
Artifact Registry, `gcloud run deploy` to update the image on the
Terraform-provisioned service, then check the new revision's readiness
condition. `gcloud run deploy --image=...` only ever touches the `image`
field — it's a partial update, not a full service replace, so it never
reverts `vpc_access`/env vars/etc. that Terraform manages, and Terraform's
`ignore_changes` means a later `terraform apply` never reverts the image
CI/CD just deployed either; the two systems cleanly own different fields
of the same Cloud Run service. See ADR-001 for why `terraform apply`
itself never runs in CI/CD, and ADR-002 for why deploy doesn't run an
authenticated HTTP smoke test.
