import logging
import os

import google.auth
from google.cloud import secretmanager

logger = logging.getLogger(__name__)

PUBLIC_KEY_SECRET_ID = "LANGFUSE_PUBLIC_KEY"
SECRET_KEY_SECRET_ID = "LANGFUSE_SECRET_KEY"


def configure() -> None:
    """Populates LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY from Secret Manager when
    running on Cloud Run (K_SERVICE is set automatically there, never locally).
    Must run once at process startup, before anything calls langfuse.get_client() —
    that call is a singleton factory that reads these env vars on its first
    invocation and caches the result for the life of the process.

    A Secret Manager failure here must never crash app startup: Langfuse is an
    observability sidecar, not required for the app's core function. On failure,
    Langfuse's own client falls back to a disabled/no-op state (no keys set)."""
    if not os.environ.get("K_SERVICE"):
        return
    try:
        os.environ["LANGFUSE_PUBLIC_KEY"] = _fetch_secret(PUBLIC_KEY_SECRET_ID)
        os.environ["LANGFUSE_SECRET_KEY"] = _fetch_secret(SECRET_KEY_SECRET_ID)
    except Exception:
        logger.warning("Failed to load Langfuse credentials from Secret Manager; tracing disabled.", exc_info=True)


def _fetch_secret(secret_id: str) -> str:
    _, project_id = google.auth.default()
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
