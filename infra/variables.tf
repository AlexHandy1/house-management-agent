variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "house-management-agent"
}

variable "region" {
  description = "GCP region for all regional resources"
  type        = string
  default     = "europe-west1"
}

variable "environment" {
  description = "Deployment environment name (a variable, not hardcoded, so a second environment can be added later)"
  type        = string
  default     = "production"
}

variable "owner_email" {
  description = "The sole Google account allowed through IAP to use this deployment. Deliberately undefaulted and never committed — supply at apply time (TF_VAR_owner_email or a local .tfvars file, gitignored). This is PII and this repo is public (see ADR on open source from day one)."
  type        = string
}

variable "db_vm_bootstrap_internet_access" {
  description = "Attaches a temporary external IP to the issues-DB VM so its first-boot startup script can apt-get install postgresql (Debian's package mirrors aren't reachable via Private Google Access). Every external IPv4 costs ~$0.005/hr while attached — set true for exactly one apply to bootstrap the VM, confirm it finished (see infra/README.md), then apply again with this left false (the default) to remove it. Ongoing operation (the every-boot password refresh from Secret Manager) needs no external IP at all — see private_ip_google_access on the db subnet in network.tf."
  type        = bool
  default     = false
}
