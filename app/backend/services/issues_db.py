import logging
import os
from typing import Any

import google.auth
import psycopg
from google.cloud import secretmanager
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from models.agent_outcome import AgentOutcome, ContractorResult

logger = logging.getLogger(__name__)

DATABASE_PASSWORD_SECRET_ID = "DATABASE_PASSWORD"

# CREATE TABLE IF NOT EXISTS only ever creates — it never alters an
# existing table, so changing a column here does nothing on a database
# that's already been initialized (a fresh environment gets the new
# column; an existing one silently doesn't, and later inserts fail).
# Fine while nothing holds real data; once production has real rows,
# switch to numbered SQL migration files + a schema_migrations tracking
# table instead of continuing to edit this string in place.
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
);
CREATE TABLE IF NOT EXISTS contractors (
  id            bigserial PRIMARY KEY,
  name          text        NOT NULL,
  trade         text,
  source_url    text,
  email         text,
  phone_number  text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS issue_contractors (
  id             bigserial PRIMARY KEY,
  issue_id       bigint      NOT NULL REFERENCES issues(id),
  contractor_id  bigint      NOT NULL REFERENCES contractors(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (issue_id, contractor_id)
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
        for contractor in outcome.contractors:
            contractor_id = _find_or_create_contractor(conn, contractor)
            conn.execute(
                """
                INSERT INTO issue_contractors (issue_id, contractor_id)
                VALUES (%s, %s)
                ON CONFLICT (issue_id, contractor_id) DO NOTHING
                """,
                (row["id"], contractor_id),
            )
    logger.info(
        "Issue saved",
        extra={
            "issue_id": row["id"],
            "status": outcome.status,
            "contractor_count": len(outcome.contractors),
        },
    )
    return row


def _find_or_create_contractor(conn: psycopg.Connection, contractor: ContractorResult) -> int:
    """Reuse a contractor row by exact name match (a contractor found for one issue can be
    linked to another); otherwise insert a new row."""
    existing = conn.execute(
        "SELECT id FROM contractors WHERE name = %s", (contractor.name,)
    ).fetchone()
    if existing:
        return existing["id"]
    created = conn.execute(
        """
        INSERT INTO contractors (name, trade, source_url, email, phone_number)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            contractor.name,
            contractor.trade,
            contractor.source_url,
            contractor.email,
            contractor.phone_number,
        ),
    ).fetchone()
    assert created is not None
    return created["id"]


def list_issues() -> list[dict[str, Any]]:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        return conn.execute(
            """
            SELECT issues.*, EXISTS (
                SELECT 1 FROM issue_contractors WHERE issue_contractors.issue_id = issues.id
            ) AS has_contractor
            FROM issues
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
