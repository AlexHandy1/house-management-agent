# Infrastructure (Terraform)

Provisions House Management Agent's GCP infrastructure: Cloud Run (behind
native IAP), Artifact Registry, Secret Manager, IAP Data Access audit
logging, and Workload Identity Federation for GitHub Actions.

## One-time bootstrap (outside Terraform)

Two steps can't be done by Terraform itself and are run manually, once, per
project:

**1. Terraform's remote-state bucket.** Terraform can't create the bucket
it will then use to store its own state:

```bash
gcloud storage buckets create gs://house-management-agent-tfstate \
  --project=house-management-agent \
  --location=europe-west1 \
  --uniform-bucket-level-access \
  --public-access-prevention
```

The bucket name and project ID are not sensitive — GCS access is
IAM-controlled, not secrecy-controlled. What must never be public is the
state file's *contents* (see below), which is why the bucket itself stays
private/IAM-restricted and state is never committed to the repo.

**2. The IAP OAuth consent screen ("brand").** Cloud Run's native IAP
integration requires this to already exist. For an **External** user type
(a personal Google account, not a Google Workspace org — which is this
project's case), Terraform cannot create it; the underlying Google API
doesn't support it for this account type. Do this once via the GCP Console:

1. Go to "APIs & Services > OAuth consent screen" for the `house-management-agent`
   project.
2. Choose **External** user type.
3. Fill in the required app name/support email fields (any values — this
   consent screen is never actually shown publicly, since only your own
   IAM-authorized account can ever reach it).

Everything else — enabling IAP on the Cloud Run service itself, the IAM
binding restricting access to your account, audit logging — is managed by
Terraform from here on.

## What's in Terraform state, and why it's remote

State holds the fully resolved, real values of everything Terraform
manages — including `owner_email` (your Google account, used as the IAP
IAM member). Since this repo is public, state cannot be a local file or
committed to the repo: the GCS backend keeps it private and IAM-controlled
independent of the repo's visibility. Secret *values* (API keys) never
enter state — Terraform only creates the empty Secret Manager containers;
values are set out-of-band (see below).

## Applying changes

No `terraform apply` in CI/CD — this is a manual step:

```bash
cd infra
TF_VAR_owner_email="you@example.com" terraform apply
```

`owner_email` is deliberately undefaulted and never committed (it's PII in
a public repo) — supply it at apply time as above, or via a local
`.tfvars` file (gitignored, never committed).

## Setting secret values

Terraform creates the Secret Manager *containers* (`openrouter-api-key`,
`langfuse-public-key`, `langfuse-secret-key`) but never their values. Set
each one out-of-band, once:

```bash
echo -n "sk-..." | gcloud secrets versions add openrouter-api-key \
  --project=house-management-agent --data-file=-
```

## Manual deploy (CI/CD unavailable)

The normal path is merging to `main`, which deploys automatically via
GitHub Actions. If Actions itself is unavailable, `infra/manual_deploy.sh`
reproduces CI's build+deploy jobs from the local machine instead:

```bash
./infra/manual_deploy.sh
```

Requires local `gcloud`/`docker` auth already configured. Builds and
deploys the current git `HEAD`, tagged by its commit SHA (same scheme CI
uses). Terraform's `lifecycle.ignore_changes` on the Cloud Run image means
a later `terraform apply` won't revert this back to the placeholder image.

Note this script checks Cloud Run revision readiness, not an HTTP smoke
test — IAP gates every path on the service, so an unauthenticated curl
would only prove IAP itself is working, not the app underneath it. Verify
the app manually via the Cloud Run URL (behind IAP sign-in) after deploy.
