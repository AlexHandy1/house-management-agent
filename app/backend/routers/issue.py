import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from models.agent_outcome import AgentOutcome
from services.agent import build_client, run_agent
from services.issues_db import list_issues, save
from services.rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


class IssueRequest(BaseModel):
    issue_text: str = Field(min_length=1, max_length=2000)


@router.post("/api/issue", response_model=AgentOutcome)
@limiter.limit("10/minute")
def submit_issue(request: Request, issue: IssueRequest) -> AgentOutcome:
    logger.info("Issue submitted")
    return run_agent(issue.issue_text, build_client(), save=save)


@router.get("/api/issues")
def get_issues() -> list[dict[str, Any]]:
    return list_issues()
