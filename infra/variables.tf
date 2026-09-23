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
