# A dedicated custom-mode VPC, not the auto-created `default` network — a
# custom VPC has no default firewall rules, so the only rules that exist
# are the ones this project defines explicitly (database.tf). GLOBAL
# routing is set explicitly even though this VPC has no dynamic/BGP routes
# today, so subnet-to-subnet routes are never accidentally regional-only.
resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                    = "house-mgmt-vpc"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"

  depends_on = [google_project_service.required]
}

# Cloud Run's Direct VPC egress attaches here (cloud_run.tf). Ranges are
# chosen up front, non-overlapping with the db subnet below — a subnet's
# range can only be expanded later, not shrunk or renumbered.
resource "google_compute_subnetwork" "run" {
  project       = var.project_id
  name          = "house-mgmt-run"
  network       = google_compute_network.vpc.id
  region        = var.region
  ip_cidr_range = "10.10.0.0/24"
}

# The issues-database VM (database.tf) lives here, in us-central1 — chosen
# for free-tier e2-micro eligibility, not proximity to the Cloud Run
# service in europe-west1 (see the ADR on DB hosting for the cross-region
# trade-off).
resource "google_compute_subnetwork" "db" {
  project       = var.project_id
  name          = "house-mgmt-db"
  network       = google_compute_network.vpc.id
  region        = "us-central1"
  ip_cidr_range = "10.20.0.0/24"
}
