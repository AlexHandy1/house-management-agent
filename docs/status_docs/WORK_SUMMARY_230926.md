# Work Summary — 23 September 2026

## What was built

Phase 1 MVP scaffolding, end to end, from empty repo to a real deployed app behind Google auth:

- **Backend** (`app/backend`) — FastAPI app. `routers/health.py` (`/health`), `routers/issue.py`
  (`POST /api/issue`: 2000-char/non-empty guardrail, per-IP rate limiting via `slowapi`, logs
  "Issue submitted" with no request content). `services/agent.py` — minimal ReAct loop, system
  prompt only, no tools, OpenRouter + `inception/mercury-2.5`, wrapped in a Langfuse `generation`
  observation. `services/rate_limiter.py`, `services/langfuse_config.py` (Secret-Manager-backed
  credential resolution, resolved once at startup — see Decisions), `services/iap_identity.py`
  (verifies `X-Goog-IAP-JWT-Assertion`, used only for logging). `main.py` wires a middleware that
  logs the verified IAP caller's email per request, plus static-file serving of the built
  frontend. 16 backend tests (pytest), one live-LLM eval (`tests/evals/`, `@pytest.mark.eval`,
  excluded from the default run via `pytest.ini`'s marker config).
- **Frontend** (`app/frontend`) — Vite/React/TS. One page: issue-text form (2000-char
  `maxLength`) → `POST /api/issue` → renders the response. Basic readable styling (replaced Vite
  template defaults). 3 tests (vitest + testing-library).
- **Infrastructure** (`infra/`) — Terraform: Cloud Run (native IAP, `iap_enabled = true`, `google-beta`
  provider), Artifact Registry, Secret Manager (`OPENROUTER_API_KEY`, `LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_SECRET_KEY` — imported from secrets the user created via Console, not
  Terraform-created), IAP Data Access audit logging, GitHub Actions Workload Identity Federation
  (repo+branch-scoped trust condition), GCS remote Terraform state. `infra/README.md` documents
  the two manual bootstrap steps. `infra/manual_deploy.sh` for when CI/CD is unavailable.
- **CI/CD** (`.github/workflows/ci-cd.yml`) — lint/typecheck → unit tests → Docker build → (push
  to `main` only) push image + `gcloud run deploy` + revision-readiness check.
- **Docs** — `ARCHITECTURE.md` populated (was a placeholder), `docs/decisions/ADR-001`
  (IaC/CI-CD topology), `ADR-002` (Cloud Run native IAP as auth strategy), `ADR-003`
  (Langfuse observability + secrets resolution patterns), `README.md` status updated.

**Deployed and verified working**: `https://house-management-agent-production-617555935510.europe-west1.run.app/`
— IAP sign-in confirmed functioning (authenticated as `alex.handy.research@gmail.com`), real app
deploy pending merge of branch `clean_up_production_scaffolding`.

## What was explored / learnt

- **Cloud Run native IAP** (`iap_enabled = true`, GA March 2026) needs no load balancer, unlike
  the older LB+Serverless-NEG pattern — confirmed via direct research before committing.
- **Native IAP's Terraform field is `google-beta`-only** (`launch_stage = "BETA"` required).
- **No-org project gap**: the IAP-auto-provisioned OAuth client only exists for projects inside a
  Google Cloud organization. A personal-account project (this one) needs a manually-created
  custom OAuth client + consent screen (Console), applied via `gcloud iap settings set` — cannot
  be done via Terraform for an External-type brand (`google_iap_client` is also deprecated/dead
  as of Jan 2026). Hit this live: first deploy attempt showed "Empty Google Account OAuth client
  ID(s)/secret(s)" until this was applied.
- **`iap_settings.yaml` gotcha**: first attempt included an invalid `url_redirect` field under
  `access_settings` (API rejected with `INVALID_ARGUMENT`) — that value belongs in the OAuth
  client's Console-configured redirect URI, not this settings file. Fixed by removing the field.
- **Langfuse's `get_client()` is a process-wide singleton keyed by public key** — confirmed via
  reading the SDK source and Langfuse's own docs. Per-request lazy credential resolution (the
  pattern used for OpenRouter) would silently misbehave: same key → arguments ignored, cached
  instance reused; different key → a new background batching thread/queue leaked per call.
  Resolved by calling `langfuse_config.configure()` once at `main.py` module load, before
  anything can call `get_client()`.
- **Secret naming mismatch**: user created secrets via Console as `OPENROUTER_API_KEY`,
  `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` (uppercase); code/Terraform originally used
  lowercase-hyphenated names matching nature-quest's convention. Reconciled by renaming
  code/Terraform to match what was already created, then `terraform import`-ing the three
  existing secrets into state (avoided duplicate/orphaned secrets).
- **gcloud's `--format=value(...)` does not support JMESPath filters** like `[?type=Ready]` — it
  silently returns empty output rather than erroring. The post-deploy readiness check (both CI
  and `manual_deploy.sh`) always failed regardless of actual deploy success until switched to
  `--format=json | jq -r '...'`. Verified live: deploy's `Ready` condition was `"True"` the whole
  time; only the check script was broken.
- **IAP JWT risk analysis** (user-initiated): confirmed the app never logs the raw
  `X-Goog-IAP-JWT-Assertion` value, including in the failure/exception path (`id_token.verify_token`
  delegates to PyJWT, whose exceptions carry static messages, not the raw token). The JWT is
  minted fresh per forwarded request, audience-scoped to this exact Cloud Run service, and even
  if captured would only affect this app's own log content (not grant access) since access
  control is fully decided by IAP/Cloud Run's IAM before this code ever runs.

## Decisions and trade-offs

- **Decision:** Cloud Run native IAP for auth, not in-app OAuth, not LB+IAP. **Why:** simplest
  option once the no-org gap was worked around; keeps all access-control logic out of app code,
  enforced at the platform layer instead. **Trade-off:** one manual, not-fully-Terraform-able
  setup step (custom OAuth client) for a personal/no-org GCP project.
- **Decision:** No `allUsers` Cloud Run invoker binding — only IAP's own service agent gets
  `roles/run.invoker`. **Why:** the real bypass risk identified in this session — `allUsers`
  invoker access would let requests reach the app directly, skipping IAP's identity check
  entirely. **Trade-off:** none; this is strictly the correct posture.
- **Decision:** CI's post-deploy check verifies Cloud Run revision readiness, not an
  authenticated HTTP smoke test through IAP. **Why:** user's explicit call — granting the deploy
  identity IAP access to run a smoke test would widen an already-privileged credential's scope
  for marginal benefit (that identity can already alter what's running behind IAP anyway).
  **Trade-off:** doesn't automatically verify IAP's own configuration end-to-end; that's a
  one-time manual check after first real deploy, not an ongoing automated one.
- **Decision:** `terraform apply` never runs in CI/CD — always a manual, human-run step.
  **Why:** infra/IAM changes carry far more blast radius than an app deploy, and this repo is
  public/eventually-forkable — an external PR shouldn't be able to trigger unreviewed
  infrastructure changes automatically. **Trade-off:** every infra change needs a manual step;
  accepted as deliberate friction.
- **Decision:** Langfuse credentials resolved once at app startup; OpenRouter's resolved lazily
  per-call. **Why:** genuinely different SDK initialization semantics (see "What was explored"),
  not an inconsistency to "fix" later. **Trade-off:** two different-shaped credential-resolution
  code paths exist side by side — documented in ADR-003 specifically so this isn't
  "harmonized" incorrectly in future.
- **Decision:** Secret Manager secret IDs match what the user created via Console (uppercase),
  not nature-quest's lowercase-hyphenated convention. **Why:** avoid redoing manual console work
  already done; casing has no functional difference. **Trade-off:** diverges from nature-quest's
  naming convention.
- **Decision:** 2000-character max length on issue text, enforced both frontend (`maxLength`) and
  backend (pydantic `Field`). **Why:** user's chosen guardrail against oversized/abusive prompt
  input. **Trade-off:** none noted.

## Next steps

1. Push branch `clean_up_production_scaffolding`, open a PR, merge to `main` — this triggers the
   first real CI/CD deploy of the actual app (current deployed revision is still Terraform's
   placeholder `hello` image). Was in progress when the session's `/documentation-and-adrs` +
   `/summarise-session` request interrupted it.
2. After merge, verify the real app end-to-end through IAP sign-in at the deployed URL — confirm
   the "Issue submitted" log line and the IAP-identity log line both show up in Cloud Run logs
   (the whole point of this session's last app change).
3. Consider deleting `infra/iap_settings.yaml` locally now that its settings are applied (it's
   gitignored, but still holds the OAuth client secret in plaintext on disk) — left for the user
   to decide/handle directly rather than have it edited by the agent.
4. Resume the PRD's Phase 1 remaining scope: wire the real `research_cost`/`find_contractors`
   tool-using agent behaviour (currently prototyped only) into this production scaffolding, plus
   issue history/persistence.
