import os
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from models.agent_outcome import AgentOutcome

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
    return os.environ["DATABASE_URL"]


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
