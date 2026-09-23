from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.agent import build_client, respond_to_issue

router = APIRouter()


class IssueRequest(BaseModel):
    issue_text: str = Field(min_length=1, max_length=2000)


class IssueResponse(BaseModel):
    response: str


@router.post("/api/issue")
def submit_issue(issue: IssueRequest) -> IssueResponse:
    reply = respond_to_issue(issue.issue_text, build_client())
    return IssueResponse(response=reply)
