from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ContractorResult(BaseModel):
    """One contractor the agent found (or reused) for the issue."""

    name: str
    trade: str | None = None
    source_url: str | None = None
    email: str | None = None
    phone_number: str | None = None


class AgentOutcome(BaseModel):
    """What one agent run concluded with, before anything is written to the DB —
    the boundary the evals assert on."""

    status: Literal["done", "needs_info", "failed"]
    cost_best: Decimal | None = None
    cost_low: Decimal | None = None
    cost_high: Decimal | None = None
    sources: list[str] = []
    clarifying_question: str | None = None
    summary: str | None = None
    contractors: list[ContractorResult] = []
