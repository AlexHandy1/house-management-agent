import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.agent_outcome import AgentOutcome
from services import conversation_agent, issues_db


def tool_call_reply(name, arguments, content=None):
    call = SimpleNamespace(
        id="call_1",
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )
    message = SimpleNamespace(content=content, tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")])


def text_reply(content):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def llm_replying_with(*replies):
    llm = MagicMock()
    llm.chat.completions.create.side_effect = list(replies)
    return llm


def _issue_with_conversation(database_url):
    issue = issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))
    conversation = issues_db.create_conversation(issue["id"])
    return issue, conversation


def test_a_direct_reply_with_no_tool_call_is_persisted_and_returned(database_url):
    issue, conversation = _issue_with_conversation(database_url)
    llm = llm_replying_with(text_reply("It's a worn washer, same as before."))

    reply = conversation_agent.run_conversation_turn(
        conversation["id"], issue["id"], "Why did you say that?", llm
    )

    assert reply == "It's a worn washer, same as before."
    turns = issues_db.get_conversation_turns(conversation["id"])
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[0]["content"] == "Why did you say that?"
    assert turns[1]["content"] == "It's a worn washer, same as before."


def test_a_lookup_issue_tool_call_is_dispatched_persisted_and_fed_back_to_the_model(
    database_url,
):
    issue, conversation = _issue_with_conversation(database_url)
    llm = llm_replying_with(
        tool_call_reply("lookup_issue", {}),
        text_reply("Your estimate was based on typical costs for a worn washer."),
    )

    reply = conversation_agent.run_conversation_turn(
        conversation["id"], issue["id"], "Why that estimate?", llm
    )

    assert reply == "Your estimate was based on typical costs for a worn washer."
    turns = issues_db.get_conversation_turns(conversation["id"])
    assert [t["role"] for t in turns] == ["user", "assistant", "tool", "assistant"]
    assert turns[1]["tool_calls"][0]["function"]["name"] == "lookup_issue"
    tool_result = json.loads(turns[2]["content"])
    assert tool_result["issue"]["id"] == issue["id"]
    # the model actually received the tool result before its final reply
    second_call_messages = llm.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert second_call_messages[-1]["role"] == "tool"


def test_a_turn_at_the_cap_is_rejected_without_calling_the_model(database_url):
    issue, conversation = _issue_with_conversation(database_url)
    for i in range(10):
        issues_db.append_turn(conversation["id"], role="user", content=f"message {i}")
    llm = llm_replying_with(text_reply("should never be reached"))

    with pytest.raises(issues_db.ConversationCapReached):
        conversation_agent.run_conversation_turn(
            conversation["id"], issue["id"], "one too many", llm
        )

    llm.chat.completions.create.assert_not_called()
