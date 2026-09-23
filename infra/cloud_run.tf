data "google_project" "project" {
  project_id = var.project_id
}

locals {
  # A plain local, not google_cloud_run_v2_service.app.name — referencing the
  # resource's own attribute from inside its own env block would be a
  # self-reference cycle.
  service_name = "house-management-agent-${var.environment}"
}

resource "google_service_account" "run" {
  project      = var.project_id
  account_id   = "house-mgmt-agent-run"
  display_name = "House Management Agent Cloud Run runtime identity"
}

resource "google_cloud_run_v2_service" "app" {
  provider = google-beta

  name         = local.service_name
  project      = var.project_id
  location     = var.region
  ingress      = "INGRESS_TRAFFIC_ALL"
  launch_stage = "BETA"

  # Native Cloud Run IAP: the entire service is gated by Google sign-in +
  # IAM before any request reaches the app, for every path — no app-level
  # auth code. Requires the OAuth consent screen ("IAP brand") to already
  # exist for this project, a one-time manual Console step for an
  # External-type brand (see infra/README.md) — Terraform can't create
  # that resource for this account type.
  iap_enabled = true

  template {
    service_account = google_service_account.run.email

    # Cost-creep guardrail: caps worst-case Cloud Run cost for a
    # single-user personal deployment.
    scaling {
      max_instance_count = 2
    }

    containers {
      # Placeholder image - CI/CD's deploy step replaces this with the
      # real built image on every deploy (see lifecycle block below).
      image = "us-docker.pkg.dev/cloudrun/container/hello:latest"

      env {
        name  = "LANGFUSE_BASE_URL"
        value = "https://cloud.langfuse.com"
      }

      # Lets the app verify the X-Goog-IAP-JWT-Assertion header's signature
      # against the right audience, for its own request-identity logging
      # (access control itself is already fully enforced by IAP before the
      # request reaches this container — this is logging only).
      env {
        name  = "IAP_AUDIENCE"
        value = "/projects/${data.google_project.project.number}/locations/${var.region}/services/${local.service_name}"
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [google_project_service.required]
}

# IAP needs permission to invoke the underlying Cloud Run service on a
# caller's behalf. This is the ONLY invoker binding — deliberately not
# allUsers, which would let requests bypass IAP entirely by hitting the
# run.app URL directly.
resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  provider = google-beta

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-iap.iam.gserviceaccount.com"
}

# The only principal allowed through IAP's Google-sign-in gate.
resource "google_iap_web_cloud_run_service_iam_member" "owner" {
  provider = google-beta

  project                 = var.project_id
  location                = var.region
  cloud_run_service_name  = google_cloud_run_v2_service.app.name
  role                    = "roles/iap.httpsResourceAccessor"
  member                  = "user:${var.owner_email}"
}
