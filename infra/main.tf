terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloud Run's native IAP integration (cloud_run.tf) is still a beta-only
# field (iap_enabled), not yet in the stable google provider.
provider "google-beta" {
  project = var.project_id
  region  = var.region
}
