import os

import google.auth
from google.cloud import secretmanager

DATABASE_PASSWORD_SECRET_ID = "DATABASE_PASSWORD"


def get_database_url() -> str:
    """Picks the connection source by environment: assembled from Secret
    Manager + non-secret env vars when deployed on Cloud Run — either a
    Service (K_SERVICE) or a Job (CLOUD_RUN_JOB; Jobs don't set K_SERVICE) —
    the local DATABASE_URL env var (.env) otherwise. Mirrors
    services.agent.resolve_api_key()."""
    if os.environ.get("K_SERVICE") or os.environ.get("CLOUD_RUN_JOB"):
        password = _fetch_database_password_from_secret_manager()
        host = os.environ["DB_HOST"]
        name = os.environ["DB_NAME"]
        user = os.environ["DB_USER"]
        return f"postgresql://{user}:{password}@{host}/{name}"
    return os.environ["DATABASE_URL"]


def _fetch_database_password_from_secret_manager() -> str:
    _, project_id = google.auth.default()
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{DATABASE_PASSWORD_SECRET_ID}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
