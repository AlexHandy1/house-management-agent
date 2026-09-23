from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from services.agent import build_client, respond_to_issue
from services.rate_limiter import limiter

router = APIRouter()


class IssueRequest(BaseModel):
    issue_text: str = Field(min_length=1, max_length=2000)


class IssueResponse(BaseModel):
    response: str


@router.post("/api/issue")
@limiter.limit("10/minute")
def submit_issue(request: Request, issue: IssueRequest) -> IssueResponse:
    reply = respond_to_issue(issue.issue_text, build_client())
    return IssueResponse(response=reply)
