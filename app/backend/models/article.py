from datetime import date

from pydantic import BaseModel


class Article(BaseModel):
    """One article pulled from a news source (NRLA, Tenancy Deposit Scheme)."""

    source: str
    title: str
    url: str
    published_date: date | None = None
    summary: str | None = None
