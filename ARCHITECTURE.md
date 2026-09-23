# Architecture

Whole-system map for the Phase 1 MVP scaffolding (`docs/prds/production-v1-prd-200926.md`).
Points to ADRs/specs for full reasoning rather than restating it.

## Components

- **`app/frontend`** — Vite/React/TypeScript single-page app. One form
  (issue text in, agent response out), styled minimally. `vitest` +
  `@testing-library/react` for tests.
- **`app/backend`** — FastAPI. Routers (`routers/`) handle HTTP; services
  (`services/`) hold the actual logic (agent loop, rate limiting, Langfuse
  config, IAP identity verification). `pytest` for tests, with an `eval`
  marker (see ADR-003) separating fast/free tests from real-LLM-calling
  ones. In production, also serves the frontend's built static files
  (`fastapi.staticfiles`) from a single Docker image/Cloud Run service —
  there is no separate frontend server in production.
- **`infra/`** — Terraform. Provisions Cloud Run, Artifact Registry, Secret
  Manager, IAP + its IAM bindings and audit logging, and GitHub Actions'
  Workload Identity Federation. See `infra/README.md` for the bootstrap
  sequence (including the one-time manual steps Terraform can't do) and
  ADR-001/ADR-002 for the reasoning.
- **`.github/workflows/ci-cd.yml`** — lint/typecheck → unit tests → Docker
  build → (on push to `main` only) deploy to Cloud Run. See ADR-001.
- **`prototypes/`** — throwaway prototyping, explicitly not production
  code (see `prototypes/README.md`). The production agent loop in
  `app/backend/services/agent.py` is a from-scratch minimal rewrite (no
  tools yet), not a port of prototype code.

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
   → rate-limited (per-IP), 2000-character-capped issue text → the agent
   loop (`services/agent.py`): a single system-prompt-only call to Mercury
   2.5 via OpenRouter, no tools yet, traced as a Langfuse `generation`.

## Deploy flow

Terraform provisions everything except the deployed app image itself
(`lifecycle.ignore_changes` on the Cloud Run image field). A push to `main`
triggers GitHub Actions: build the Docker image (bundles the frontend build
into the backend's static files, see `app/backend/Dockerfile`), push to
Artifact Registry, `gcloud run deploy` to update the image on the
Terraform-provisioned service, then check the new revision's readiness
condition. See ADR-001 for why `terraform apply` itself never runs in
CI/CD, and ADR-002 for why deploy doesn't run an authenticated HTTP smoke
test.

## What's live vs. deferred

**Live**: end-to-end scaffolding — minimal ReAct loop (no tools), web UX,
rate limiting + input-length guardrail, Langfuse observability, IAP auth +
identity logging, GCP infra, CI/CD.

**Deferred to later slices** (per the PRD's phasing): the real
`research_cost`/`find_contractors` tool-using agent behaviour (currently
prototyped only, not wired into production), issue history/persistence,
the news-watch workflow, and anything under "Future considerations" in the
PRD (config-driven self-hosting, tenant/contractor comms, compliance
scheduling, income/expense ledger).
