import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.agent import build_client
from services.conversation_agent import run_conversation_turn
from services.issues_db import (
    ConversationCapReached,
    get_conversation,
    get_conversation_steps,
    list_conversations_for_issue,
)
from services.rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    reply: str
    turn_number: int


@router.get("/api/issues/{issue_id}/conversations")
def list_conversations(issue_id: int) -> list[dict[str, Any]]:
    return list_conversations_for_issue(issue_id)


@router.get("/api/conversations/{conversation_id}")
def read_conversation(conversation_id: int) -> dict[str, Any]:
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation["steps"] = get_conversation_steps(conversation_id)
    return conversation


@router.post("/api/conversations/{conversation_id}/messages", response_model=MessageResponse)
@limiter.limit("10/minute")
def post_message(
    request: Request, conversation_id: int, message: MessageRequest
) -> MessageResponse:
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        reply = run_conversation_turn(
            conversation_id, conversation["issue_id"], message.message, build_client()
        )
    except ConversationCapReached as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    [last_step] = get_conversation_steps(conversation_id)[-1:]
    return MessageResponse(reply=reply, turn_number=last_step["turn_number"])
