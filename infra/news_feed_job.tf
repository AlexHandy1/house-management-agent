locals {
  news_feed_job_name = "house-mgmt-news-feed-pull"
}

# Dedicated identity for the Job — separate from the Service's own runtime
# identity (google_service_account.run, cloud_run.tf) and the DB VM's
# (google_service_account.db_vm, database.tf), matching this project's
# existing one-SA-per-workload pattern. Only needs Secret Manager access
# (the binding below) — the Job authenticates to Postgres with the same
# house_mgmt_app role the Service uses (see the brief spec's accepted
# single-role trade-off: no per-table DB isolation yet).
resource "google_service_account" "news_feed_job" {
  project      = var.project_id
  account_id   = "house-mgmt-news-feed-job"
  display_name = "News feed pull Job runtime identity"
}

resource "google_secret_manager_secret_iam_member" "news_feed_job_password_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.backend["DATABASE_PASSWORD"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.news_feed_job.email}"
}

# CI/CD's deploy identity (wif.tf) needs to actAs this SA to run
# `gcloud run jobs update --image=...` — same requirement, same grant shape
# as deploy_can_run_as_runtime_sa in wif.tf for the Service's own runtime SA.
# Without this, the image-update step fails with PERMISSION_DENIED on
# iam.serviceaccounts.actAs.
resource "google_service_account_iam_member" "deploy_can_run_as_news_feed_job_sa" {
  service_account_id = google_service_account.news_feed_job.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_cloud_run_v2_job" "news_feed_pull" {
  name                = local.news_feed_job_name
  project             = var.project_id
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.news_feed_job.email
      max_retries     = 0

      # Same subnet the Service uses (cloud_run.tf) — reaches the issues-DB
      # VM the same way; the VPC's GLOBAL routing mode and the firewall
      # rule in database.tf (allow from the run subnet's CIDR) don't care
      # which Cloud Run resource the traffic comes from.
      vpc_access {
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        # Placeholder — CI/CD's deploy step points this at the Service's
        # just-built image on every push to main (ci-cd.yml). The Job
        # deliberately shares that image rather than a second Dockerfile —
        # see the brief spec's trade-off discussion — and only overrides
        # the container command below to run the Job's own entrypoint
        # instead of the Service's uvicorn command.
        image = "us-docker.pkg.dev/cloudrun/container/hello:latest"

        command = ["python"]
        args    = ["-m", "jobs.pull_news_feed"]

        # Non-secret connection details for services.db_connection
        # .get_database_url() — mirrors cloud_run.tf's Service env, built
        # from these plus the DATABASE_PASSWORD secret when CLOUD_RUN_JOB
        # is set (Cloud Run sets this automatically for every Job
        # execution; it doesn't set K_SERVICE, which is Service-only).
        env {
          name  = "DB_HOST"
          value = google_compute_instance.db.network_interface[0].network_ip
        }
        env {
          name  = "DB_NAME"
          value = local.db_name
        }
        env {
          name  = "DB_USER"
          value = local.db_user
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [google_project_service.required]
}

# Cloud Scheduler needs its own identity to call the Cloud Run Jobs API on
# a schedule — deliberately not the Job's own runtime identity above (that
# one only needs Secret Manager access, not run.invoker on itself).
resource "google_service_account" "news_feed_scheduler" {
  project      = var.project_id
  account_id   = "house-mgmt-news-feed-sched"
  display_name = "News feed pull Scheduler identity"
}

# The only invoker binding on this Job — scoped to just this one Job
# resource, same narrow-grant pattern as the Service's IAP invoker binding
# in cloud_run.tf.
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.news_feed_pull.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.news_feed_scheduler.email}"
}

# Every 2 days at 06:00 UTC — matches the brief spec's agreed cadence
# (docs/specs/news-feed-automation-brief-spec-011026.md). Calls the Cloud
# Run Jobs API's :run method directly over HTTP, authenticated as the
# scheduler service account above — there's no Terraform-native "trigger
# this Job on a schedule" resource, just an HTTP target against the API.
resource "google_cloud_scheduler_job" "news_feed_pull" {
  project   = var.project_id
  region    = var.region
  name      = local.news_feed_job_name
  schedule  = "0 6 */2 * *"
  time_zone = "UTC"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.news_feed_pull.name}:run"

    oauth_token {
      service_account_email = google_service_account.news_feed_scheduler.email
    }
  }

  depends_on = [google_project_service.required]
}
