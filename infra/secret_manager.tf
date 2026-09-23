variable "backend_secret_names" {
  description = "Names of runtime secrets Cloud Run reads from Secret Manager at startup. Add a name here when a real secret exists; its value is set out-of-band, never in Terraform config."
  type        = list(string)
  default     = ["OPENROUTER_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]
}

resource "google_secret_manager_secret" "backend" {
  for_each = toset(var.backend_secret_names)

  project   = var.project_id
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "backend_access" {
  for_each = google_secret_manager_secret.backend

  project   = var.project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run.email}"
}
