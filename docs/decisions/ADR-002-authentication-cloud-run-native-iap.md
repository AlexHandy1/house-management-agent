# ADR-002: Authentication via Cloud Run native IAP

## Status
Accepted

## Date
2026-09-23

## Context
This is a single-user personal deployment: only the owner should ever be
able to reach the app, submit issues, or run up LLM spend against it (see
PRD Story 5). The app's source is public (open source from day one), so the
access control mechanism itself must not depend on obscurity — it must hold
up even when an attacker can read the exact implementation.

## Decision
Use **Cloud Run's native Identity-Aware Proxy (IAP) integration**
(`iap_enabled = true` on the `google_cloud_run_v2_service` resource, a
`google-beta`-provider-only field) rather than writing any in-app
authentication code. IAP gates every path on the service at the platform
level, before a request ever reaches the container — no login/callback
routes, no session management, in the app itself.

Access is controlled by exactly one IAM binding
(`roles/iap.httpsResourceAccessor`, granted to the owner's email only) and
enforced by a second, independent layer: Cloud Run's own invoker IAM only
grants `roles/run.invoker` to IAP's own service agent — deliberately never
to `allUsers`. This means there is no direct path to the app that bypasses
IAP; Cloud Run itself refuses every other caller.

**Known gap this project's setup required working around**: the project has
no Google Cloud organization (a personal account), so the OAuth client IAP
would normally auto-provision isn't available. This required a one-time
manual step (creating a custom OAuth client + consent screen via Console,
applied via `gcloud iap settings set`) that Terraform cannot fully
automate for an External-type brand on a no-org project — documented in
`infra/README.md`.

**Consequence for CI/CD's post-deploy verification**: since IAP gates every
path, an unauthenticated HTTP smoke test from CI would only prove IAP
itself is reachable, not that the app underneath works. Deliberately chose
*not* to grant the CI deploy identity IAP access to run an authenticated
smoke test — that would widen an already-privileged credential's scope to
solve a verification problem, for marginal benefit (the deploy identity
already has enough access to alter what's running behind IAP). CI instead
checks Cloud Run's own revision-readiness condition; full end-to-end
verification (confirming the sign-in gate and app both work together) is a
one-time manual check after the first real deploy, not an automated one.

## Alternatives Considered

### In-app OAuth (login/callback routes, session cookies in FastAPI)
- Pros: works regardless of GCP organization status; no beta-provider
  dependency; full control over the session model.
- Cons: meaningfully more code to write, test, and keep secure long-term;
  the access-control logic lives in application code that could have bugs,
  rather than being enforced by a platform layer before the app runs at
  all.
- Rejected because: for a single-user app, IAP is strictly simpler once its
  one-time setup gap is worked around, and keeps "who can reach this app"
  out of application code entirely.

### IAP via an External HTTPS Load Balancer + Serverless NEG in front of Cloud Run
- Pros: the traditional/most-documented way to put IAP in front of Cloud
  Run; doesn't depend on the newer native integration.
- Cons: meaningfully more Terraform (load balancer, NEG, backend service)
  and an added ongoing cost, for no functional benefit over the native
  integration at this project's scale.
- Rejected because: Cloud Run's native IAP integration (GA since March
  2026) protects the `run.app` endpoint directly with no load balancer
  required — confirmed via direct research before committing to this
  approach.

### Granting the CI/CD deploy identity IAP access for an authenticated smoke test
- Pros: would verify the full IAP + app path automatically on every deploy.
- Cons: widens a privileged credential's scope; the deploy identity can
  already alter what's running behind IAP by deploying arbitrary code, so
  the marginal capability gained is real but small, while the principle of
  not widening credential scope to solve a testing problem still holds.
- Rejected because: explicit user judgment call — a narrower
  revision-readiness check plus a one-time manual verification was
  preferred over expanding what the deploy credential can do.

## Consequences
- No auth code exists in `app/backend` — access control is entirely a
  platform/IAM concern, configured in `infra/cloud_run.tf`.
- Adding a second authorized user later is a one-line IAM binding change in
  Terraform, not a code change.
- The app can still read the verified caller's identity (email) from the
  `X-Goog-IAP-JWT-Assertion` header for its own request-identity logging —
  this is for observability only, never for access control, since access
  control is already fully decided before the app runs.
- IAP Data Access audit logging is enabled (`infra/audit_logging.tf`) so
  denied/unauthorized attempts are visible too, not just successful ones —
  the app's own logs only ever see already-authorized requests.
