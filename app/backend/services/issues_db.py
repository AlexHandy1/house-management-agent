import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from models.agent_outcome import AgentOutcome, ContractorResult
from services.db_connection import get_database_url

logger = logging.getLogger(__name__)

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
);
CREATE TABLE IF NOT EXISTS conversations (
  id          bigserial PRIMARY KEY,
  issue_id    bigint      NOT NULL REFERENCES issues(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conversation_steps (
  id               bigserial PRIMARY KEY,
  conversation_id  bigint      NOT NULL REFERENCES conversations(id),
  turn_number      integer     NOT NULL,
  role             text        NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
  content          text,
  tool_calls       jsonb,
  tool_call_id     text,
  created_at       timestamptz NOT NULL DEFAULT now()
)
"""


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
        _link_contractors(conn, row["id"], outcome.contractors)
    logger.info(
        "Issue saved",
        extra={
            "issue_id": row["id"],
            "status": outcome.status,
            "contractor_count": len(outcome.contractors),
        },
    )
    return row


def add_contractors_to_issue(issue_id: int, contractors: list[ContractorResult]) -> None:
    """Adds contractors to an already-saved issue — upsert by name, link via
    issue_contractors, same as save() does for a brand-new issue. Never touches the
    issues row itself and never removes an existing link; purely additive."""
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        _link_contractors(conn, issue_id, contractors)


def _link_contractors(
    conn: psycopg.Connection[dict[str, Any]], issue_id: int, contractors: list[ContractorResult]
) -> None:
    for contractor in contractors:
        contractor_id = _find_or_create_contractor(conn, contractor)
        conn.execute(
            """
            INSERT INTO issue_contractors (issue_id, contractor_id)
            VALUES (%s, %s)
            ON CONFLICT (issue_id, contractor_id) DO NOTHING
            """,
            (issue_id, contractor_id),
        )


def _find_or_create_contractor(
    conn: psycopg.Connection[dict[str, Any]], contractor: ContractorResult
) -> int:
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


MAX_USER_TURNS_PER_CONVERSATION = 10


class ConversationCapReached(Exception):
    """Raised when a conversation already has MAX_USER_TURNS_PER_CONVERSATION user turns."""


def create_conversation(issue_id: int) -> dict[str, Any]:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        row = conn.execute(
            "INSERT INTO conversations (issue_id) VALUES (%s) RETURNING *", (issue_id,)
        ).fetchone()
        assert row is not None
        return row


def get_conversation(conversation_id: int) -> dict[str, Any] | None:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT * FROM conversations WHERE id = %s", (conversation_id,)
        ).fetchone()


def append_step(
    conversation_id: int,
    role: str,
    content: str | None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
) -> dict[str, Any]:
    """Appends one step (a user message, an assistant message/tool-call, or a tool
    result) to a conversation. A step is one move within processing a turn; a turn is
    one user message plus everything the agent does in response to it. turn_number is
    derived here, not passed in: it's the count of user steps so far, incremented when
    this step is itself a user step — the single source of truth the cap also reads.

    KNOWN GAP (security review, 7 Oct): the cap check below is check-then-insert with no
    row lock, so two concurrent requests to the same conversation_id near the boundary
    can both pass the count check before either commits, landing slightly over the cap.
    Accepted for now given the single-owner usage pattern; add a row lock (or a DB-level
    constraint) if this ever needs to be airtight under concurrency."""
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM conversation_steps "
            "WHERE conversation_id = %s AND role = 'user'",
            (conversation_id,),
        ).fetchone()
        assert count_row is not None
        user_turns_so_far = count_row["count"]
        if role == "user":
            if user_turns_so_far >= MAX_USER_TURNS_PER_CONVERSATION:
                raise ConversationCapReached(
                    f"Conversation {conversation_id} already has "
                    f"{MAX_USER_TURNS_PER_CONVERSATION} user turns"
                )
            turn_number = user_turns_so_far + 1
        else:
            turn_number = user_turns_so_far
        row = conn.execute(
            """
            INSERT INTO conversation_steps
                (conversation_id, turn_number, role, content, tool_calls, tool_call_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                conversation_id,
                turn_number,
                role,
                content,
                Jsonb(tool_calls) if tool_calls is not None else None,
                tool_call_id,
            ),
        ).fetchone()
        assert row is not None
        return row


def get_conversation_steps(conversation_id: int) -> list[dict[str, Any]]:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        return conn.execute(
            """
            SELECT * FROM conversation_steps
            WHERE conversation_id = %s
            ORDER BY created_at, id
            """,
            (conversation_id,),
        ).fetchall()


def get_issue(issue_id: int) -> dict[str, Any] | None:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        return conn.execute("SELECT * FROM issues WHERE id = %s", (issue_id,)).fetchone()


def lookup_issue(issue_id: int) -> dict[str, Any]:
    """Everything a conversation agent needs about an issue: the issue row, its
    linked contractors, and the full step history of every prior conversation on it."""
    return {
        "issue": get_issue(issue_id),
        "contractors": list_contractors_for_issue(issue_id),
        "conversations": list_conversations_for_issue(issue_id),
    }


def list_conversations_for_issue(issue_id: int) -> list[dict[str, Any]]:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        conversations = conn.execute(
            "SELECT * FROM conversations WHERE issue_id = %s ORDER BY created_at, id",
            (issue_id,),
        ).fetchall()
    for conversation in conversations:
        conversation["steps"] = get_conversation_steps(conversation["id"])
    return conversations


def list_contractors_for_issue(issue_id: int) -> list[dict[str, Any]]:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        return conn.execute(
            """
            SELECT contractors.*
            FROM contractors
            JOIN issue_contractors ON issue_contractors.contractor_id = contractors.id
            WHERE issue_contractors.issue_id = %s
            """,
            (issue_id,),
        ).fetchall()


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
