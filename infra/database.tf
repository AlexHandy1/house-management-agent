locals {
  db_name = "house_mgmt"
  db_user = "house_mgmt_app"
}

# The VM's own identity — deliberately separate from the Cloud Run runtime
# identity (google_service_account.run in cloud_run.tf), with access to
# exactly one secret (see the IAM binding below).
resource "google_service_account" "db_vm" {
  project      = var.project_id
  account_id   = "house-mgmt-agent-db"
  display_name = "House Management Agent issues-DB VM runtime identity"
}

resource "google_secret_manager_secret_iam_member" "db_vm_password_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.backend["DATABASE_PASSWORD"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.db_vm.email}"
}

# The only rules in this VPC (network.tf has no default rules, unlike the
# auto-created `default` network).
resource "google_compute_firewall" "allow_postgres_from_run" {
  project = var.project_id
  name    = "allow-postgres-from-run-subnet"
  network = google_compute_network.vpc.id

  direction     = "INGRESS"
  source_ranges = [google_compute_subnetwork.run.ip_cidr_range]
  target_tags   = ["postgres"]

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }
}

# IAP TCP forwarding tunnels SSH without exposing port 22 to the public
# internet — 35.235.240.0/20 is Google's fixed range for IAP's own
# connection proxy, not a client IP. Requires roles/iap.tunnelUser on the
# connecting account (the project owner already has this).
resource "google_compute_firewall" "allow_ssh_from_iap" {
  project = var.project_id
  name    = "allow-ssh-from-iap"
  network = google_compute_network.vpc.id

  direction     = "INGRESS"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["postgres"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# Free-tier-eligible size/region. Postgres via the distro's own apt package
# (Debian 12 ships 15), pinned to match docker-compose.yml and CI exactly —
# no third-party apt repo just to chase a newer version.
resource "google_compute_instance" "db" {
  project      = var.project_id
  name         = "house-mgmt-db"
  zone         = "us-central1-a"
  machine_type = "e2-micro"
  tags         = ["postgres"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.db.id
    # Ephemeral public IP for `apt-get install` only — this project sets no
    # Cloud NAT and relies on outbound-by-default egress. The VM is only
    # ever *reached* over the private IP (see the firewall rules above);
    # nothing depends on this address once package install has run.
    access_config {}
  }

  service_account {
    email  = google_service_account.db_vm.email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = <<-EOT
    #!/bin/bash
    set -euo pipefail

    PROVISIONED_MARKER=/var/lib/house-mgmt-db-provisioned
    PG_CONF_DIR=$(find /etc/postgresql -mindepth 1 -maxdepth 1 -type d | head -n1)/main

    if [ ! -f "$PROVISIONED_MARKER" ]; then
      apt-get update
      apt-get install -y postgresql

      sed -i "s/^#listen_addresses.*/listen_addresses = '*'/" "$PG_CONF_DIR/postgresql.conf"
      echo "host ${local.db_name} ${local.db_user} ${google_compute_subnetwork.run.ip_cidr_range} scram-sha-256" \
        >> "$PG_CONF_DIR/pg_hba.conf"

      sudo -u postgres createdb "${local.db_name}"
      sudo -u postgres psql -c "CREATE ROLE ${local.db_user} WITH LOGIN;"
      sudo -u postgres psql -d "${local.db_name}" -c "GRANT ALL PRIVILEGES ON DATABASE ${local.db_name} TO ${local.db_user};"
      sudo -u postgres psql -d "${local.db_name}" -c "GRANT ALL ON SCHEMA public TO ${local.db_user};"

      systemctl restart postgresql
      touch "$PROVISIONED_MARKER"
    fi

    # Runs every boot (idempotent, unlike the block above): keeps the role's
    # password in sync with whatever's currently in Secret Manager. No
    # restart needed — ALTER ROLE ... PASSWORD applies immediately.
    DB_PASSWORD=$(gcloud secrets versions access latest --secret=DATABASE_PASSWORD)
    sudo -u postgres psql -c "ALTER ROLE ${local.db_user} WITH PASSWORD '$${DB_PASSWORD}';"
  EOT

  depends_on = [google_project_service.required]
}
