import os
from typing import Any

import google.auth
import psycopg
from google.cloud import secretmanager
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from models.agent_outcome import AgentOutcome

DATABASE_PASSWORD_SECRET_ID = "DATABASE_PASSWORD"

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
  id                     bigserial PRIMARY KEY,
  source_text            text        NOT NULL,
  status                 text        NOT NULL CHECK (status IN ('done', 'needs_info', 'failed')),
  cost_best              numeric,
  cost_low               numeric,
  cost_high              numeric,
  supporting_web_sources jsonb       NOT NULL DEFAULT '[]',
  clarifying_question    text,
  agent_summary          text,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now()
)
"""


def get_database_url() -> str:
    """Picks the connection source by environment: assembled from Secret
    Manager + non-secret env vars when deployed on Cloud Run (K_SERVICE is
    set automatically there, never locally), the local DATABASE_URL env
    var (.env) otherwise — mirrors services.agent.resolve_api_key()."""
    if os.environ.get("K_SERVICE"):
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


def init_schema() -> None:
    with psycopg.connect(get_database_url()) as conn:
        conn.execute(SCHEMA)


def save(source_text: str, outcome: AgentOutcome) -> dict[str, Any]:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        row = conn.execute(
            """
            INSERT INTO issues (source_text, status, cost_best, cost_low, cost_high,
                                supporting_web_sources, clarifying_question, agent_summary)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                source_text,
                outcome.status,
                outcome.cost_best,
                outcome.cost_low,
                outcome.cost_high,
                Jsonb(outcome.sources),
                outcome.clarifying_question,
                outcome.summary,
            ),
        ).fetchone()
    assert row is not None
    return row


def list_issues() -> list[dict[str, Any]]:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        return conn.execute("SELECT * FROM issues ORDER BY created_at DESC, id DESC").fetchall()
