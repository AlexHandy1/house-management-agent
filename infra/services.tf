locals {
  required_services = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    # For the issues database VM (database.tf). Enabling this auto-creates a
    # `default` network with permissive SSH/RDP-open-to-the-world firewall
    # rules — this project doesn't use that network (see network.tf, a
    # dedicated custom VPC with no default rules), so those rules apply to
    # nothing. Known residual: a future VM created without an explicit
    # --network would land on the `default` network; deleting it is an
    # optional later step outside this slice.
    "compute.googleapis.com",
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.required_services)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
