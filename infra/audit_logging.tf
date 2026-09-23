# IAP Data Access audit logs — off by default in GCP. Enabling these is the
# only way to see denied/unauthorized sign-in attempts, since IAP rejects
# them before the request ever reaches the app (so app-level logs never see
# them). Negligible cost at this project's traffic scale (first 50 GiB/month
# of ingestion is free).
resource "google_project_iam_audit_config" "iap" {
  project = var.project_id
  service = "iap.googleapis.com"

  audit_log_config {
    log_type = "ADMIN_READ"
  }
  audit_log_config {
    log_type = "DATA_READ"
  }
  audit_log_config {
    log_type = "DATA_WRITE"
  }
}
