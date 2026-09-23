#!/usr/bin/env bash
# Manual deploy path for when GitHub Actions is unavailable (e.g. a GitHub
# platform incident, see githubstatus.com) — mirrors exactly what
# .github/workflows/ci-cd.yml's build+deploy jobs do, run from the local
# machine instead. Safe to re-run; each run is tagged with the current git
# SHA, same as CI, so it doesn't collide with or overwrite prior deploys.
#
# Run from the repo root: ./infra/manual_deploy.sh

set -euo pipefail

PROJECT_ID="house-management-agent"
REGION="europe-west1"
SERVICE="house-management-agent-production"
IMAGE="europe-west1-docker.pkg.dev/house-management-agent/house-management-agent/app"
SHA="$(git rev-parse HEAD)"

echo "==> Configuring docker auth for Artifact Registry (idempotent)"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --project="$PROJECT_ID" --quiet

echo "==> Building image ${IMAGE}:${SHA}"
docker build -f app/backend/Dockerfile -t "${IMAGE}:${SHA}" .

echo "==> Pushing ${IMAGE}:${SHA}"
docker push "${IMAGE}:${SHA}"

echo "==> Deploying to Cloud Run service ${SERVICE}"
gcloud run deploy "$SERVICE" \
  --image="${IMAGE}:${SHA}" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --quiet

echo "==> Checking the new revision is Ready"
# Not an HTTP smoke test: IAP gates every path on this service, so an
# unauthenticated curl from CI/this script would only prove IAP is working,
# not the app underneath it. Checking Cloud Run's own readiness condition
# instead confirms the container started and passed its startup probe,
# without granting this deploy identity any access through IAP.
READY="$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT_ID" \
  --format='value(status.conditions[?type=Ready].status)')"
if [ "$READY" != "True" ]; then
  echo "Deploy of ${SHA} did not become Ready." >&2
  exit 1
fi

echo "==> Deploy of ${SHA} to service ${SERVICE} succeeded and is Ready."
echo "    Verify manually via the Cloud Run console URL (behind IAP sign-in)."
