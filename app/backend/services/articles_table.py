import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row

from models.article import Article
from services.db_connection import get_database_url

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
  id             bigserial PRIMARY KEY,
  source         text        NOT NULL,
  title          text        NOT NULL,
  url            text        NOT NULL UNIQUE,
  published_date date,
  summary        text,
  created_at     timestamptz NOT NULL DEFAULT now()
)
"""


def init_schema() -> None:
    with psycopg.connect(get_database_url()) as conn:
        conn.execute(SCHEMA)


def save_articles(articles: list[Article]) -> int:
    """Upserts by url (first-seen wins on a collision). Returns the number of
    articles actually inserted this call, not the number passed in."""
    inserted = 0
    with psycopg.connect(get_database_url()) as conn:
        for article in articles:
            row = conn.execute(
                """
                INSERT INTO articles (source, title, url, published_date, summary)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                RETURNING id
                """,
                (
                    article.source,
                    article.title,
                    article.url,
                    article.published_date,
                    article.summary,
                ),
            ).fetchone()
            if row is not None:
                inserted += 1
    return inserted


def list_recent_articles(limit: int = 10) -> list[dict[str, Any]]:
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        return conn.execute(
            """
            SELECT * FROM articles
            ORDER BY published_date DESC NULLS LAST, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
