# Infrastructure (Terraform)

Provisions House Management Agent's GCP infrastructure: Cloud Run (behind
native IAP), the news feed Cloud Run Job and its Cloud Scheduler trigger,
Artifact Registry, Secret Manager, IAP Data Access audit logging, and
Workload Identity Federation for GitHub Actions.

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

### Bootstrapping the issues-DB VM (two applies)

The DB VM (`infra/database.tf`) has no external IP by default — external
IPv4s cost ~$0.005/hr for as long as they're attached, and the VM's only
genuine need for one is its first-boot `apt-get install postgresql`
(everything after that, including the every-boot password refresh from
Secret Manager, goes over free Private Google Access instead — see
`ARCHITECTURE.md`'s network diagram and ADR-004). The first time this VM
is created — or any time it's recreated from scratch, e.g. after a
`metadata_startup_script` change, which forces a full replace, not an
in-place update — attach the IP for exactly one apply, then remove it:

```bash
# 1. Set DATABASE_PASSWORD first (see below) if this is a fresh project —
#    the VM's startup script needs it to exist on its first boot.

# 2. Create/recreate the VM with a temporary external IP and let it boot.
TF_VAR_owner_email="you@example.com" TF_VAR_db_vm_bootstrap_internet_access=true \
  terraform apply

# 3. Confirm the startup script finished — look for "Finished running
#    startup scripts" and an "ALTER ROLE" line with no error before it:
gcloud compute instances get-serial-port-output house-mgmt-db \
  --project=house-management-agent --zone=us-central1-a | tail -50

# 4. Remove the external IP — everything from here on needs no public IP.
TF_VAR_owner_email="you@example.com" terraform apply
```

Every later `terraform apply` (without the bootstrap variable) leaves the
VM as-is — Terraform only touches it when this variable's value changes,
or when something else forces a replace.

**If `DATABASE_PASSWORD` already exists outside Terraform** (e.g. you set
it via Console/`gcloud secrets create` before ever running `apply`), step
2 above will fail with `Error 409: Secret [...] already exists` — Terraform
doesn't know about a secret it didn't create. Bring it under management
once, then re-run apply:

```bash
TF_VAR_owner_email="you@example.com" terraform import \
  'google_secret_manager_secret.backend["DATABASE_PASSWORD"]' \
  projects/house-management-agent/secrets/DATABASE_PASSWORD
```

## Setting secret values

Terraform creates the Secret Manager *containers* (`OPENROUTER_API_KEY`,
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `DATABASE_PASSWORD` — see
`secret_manager.tf`'s `backend_secret_names`) but never their values. Set
each one out-of-band, once:

```bash
echo -n "sk-..." | gcloud secrets versions add OPENROUTER_API_KEY \
  --project=house-management-agent --data-file=-
```

For `DATABASE_PASSWORD`, generate a random value rather than picking one —
both the DB VM's startup script and Cloud Run itself read this same secret
(see `infra/database.tf`, `infra/cloud_run.tf`):

```bash
openssl rand -base64 24 | tr -d '\n' | gcloud secrets versions add DATABASE_PASSWORD \
  --project=house-management-agent --data-file=-
```

The VM only picks this up on its *next* boot (its startup script re-runs
`ALTER ROLE ... PASSWORD` every boot, not continuously) — after setting or
rotating it, reset the VM: `gcloud compute instances reset house-mgmt-db
--project=house-management-agent --zone=us-central1-a`.

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
