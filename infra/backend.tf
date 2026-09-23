terraform {
  backend "gcs" {
    bucket = "house-management-agent-tfstate"
    prefix = "terraform/state"
  }
}
