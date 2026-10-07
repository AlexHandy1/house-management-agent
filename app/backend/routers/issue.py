import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from models.agent_outcome import AgentOutcome
from services.agent import build_client, run_agent
from services.issues_db import create_conversation, list_issues, save
from services.rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


class IssueRequest(BaseModel):
    issue_text: str = Field(min_length=1, max_length=2000)


class IssueResponse(AgentOutcome):
    conversation_id: int


@router.post("/api/issue", response_model=IssueResponse)
@limiter.limit("10/minute")
def submit_issue(request: Request, issue: IssueRequest) -> IssueResponse:
    logger.info("Issue submitted")
    saved_issue: dict[str, Any] = {}

    def save_and_capture(source_text: str, outcome: AgentOutcome) -> Any:
        row = save(source_text, outcome)
        saved_issue.update(row)
        return row

    outcome = run_agent(issue.issue_text, build_client(), save=save_and_capture)
    conversation = create_conversation(saved_issue["id"])
    return IssueResponse(**outcome.model_dump(), conversation_id=conversation["id"])


@router.get("/api/issues")
def get_issues() -> list[dict[str, Any]]:
    return list_issues()
