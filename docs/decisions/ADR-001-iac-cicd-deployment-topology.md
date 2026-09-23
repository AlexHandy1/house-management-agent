# ADR-001: IaC, CI/CD, and deployment topology

## Status
Accepted

## Date
2026-09-23

## Context
Phase 1 MVP scope (`docs/prds/production-v1-prd-200926.md`) requires a deployed,
tested, observable web app with CI/CD, not another throwaway prototype. The
sibling project `nature-quest` already proved out a working GCP/Terraform/
GitHub Actions setup — reusing that shape lets this project move quickly
rather than re-deriving the same infrastructure decisions from scratch.

## Decision
- **IaC**: Terraform, with a GCS remote state backend (bucket created via a
  documented one-time manual `gcloud` command — Terraform can't create the
  bucket it will then use to store its own state). Applying changes is a
  manual, human-run step (`terraform apply`), never run from CI/CD.
- **CI/CD**: GitHub Actions, mirroring `nature-quest`'s job structure —
  lint/typecheck → unit tests → Docker build → (on push to `main` only)
  push image + `gcloud run deploy`. Deploy authenticates via Workload
  Identity Federation (no long-lived service account keys), scoped to this
  exact repo and the `main` branch by GCP's own trust condition — not just
  the workflow YAML's own `if` gating, so a modified workflow file in a
  fork PR still can't obtain deploy credentials.
- **Hosting**: Single Cloud Run service (Docker image bundles the built
  React frontend as static files served by the FastAPI backend, same
  single-container pattern as `nature-quest`).
- **Why Terraform never runs in CI/CD**: infrastructure changes (IAM,
  secrets, access control) have a much larger blast radius than an app
  code deploy, and this repo is public / intended to accept outside
  contributions eventually — an external PR auto-triggering `terraform
  apply` would mean unreviewed infrastructure changes running
  automatically. Keeping `apply` manual means every infra change is
  deliberately run by a human, regardless of what's in a merged PR.

## Alternatives Considered

### Running `terraform apply` in the CI/CD deploy job
- Pros: fully automated, no manual step between merge and infra changes
  taking effect.
- Cons: a merged PR (including, eventually, from an outside contributor)
  could alter IAM/access/secrets configuration unreviewed and
  automatically.
- Rejected because: infra changes need a human in the loop, given this
  project's open-source posture; app deploys don't carry the same risk and
  stay automated.

### A fresh infrastructure design instead of reusing nature-quest's
- Pros: could be tailored from scratch to this project's exact needs.
- Cons: nature-quest's setup was already proven working in production; the
  explicit goal for this slice was to move quickly by reusing it.
- Rejected because: no requirement here differs enough from nature-quest's
  foundation to justify re-deriving it (see ADR-002 for the one place this
  project's setup does diverge — authentication).

## Consequences
- A first-time deploy always starts from a placeholder Cloud Run image
  (`lifecycle.ignore_changes` on the image field means `terraform apply`
  never reverts a real deployed image back to the placeholder).
- Adding infrastructure changes always requires a human to run `terraform
  apply` locally — this is friction by design, not an oversight.
- `infra/manual_deploy.sh` reproduces CI's build+deploy steps locally, for
  when GitHub Actions itself is unavailable.
