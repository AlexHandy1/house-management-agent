from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class AgentOutcome(BaseModel):
    """What one agent run concluded with, before anything is written to the DB —
    the boundary the evals assert on."""

    status: Literal["done", "needs_info", "failed"]
    cost_best: Decimal | None = None
    cost_low: Decimal | None = None
    cost_high: Decimal | None = None
    sources: list[str] = []
    clarifying_question: str | None = None
