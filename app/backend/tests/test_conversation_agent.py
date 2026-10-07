import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.agent_outcome import AgentOutcome, ContractorResult
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
    steps = issues_db.get_conversation_steps(conversation["id"])
    assert [s["role"] for s in steps] == ["user", "assistant"]
    assert [s["turn_number"] for s in steps] == [1, 1]
    assert steps[0]["content"] == "Why did you say that?"
    assert steps[1]["content"] == "It's a worn washer, same as before."


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
    steps = issues_db.get_conversation_steps(conversation["id"])
    assert [s["role"] for s in steps] == ["user", "assistant", "tool", "assistant"]
    assert [s["turn_number"] for s in steps] == [1, 1, 1, 1]
    assert steps[1]["tool_calls"][0]["function"]["name"] == "lookup_issue"
    tool_result = json.loads(steps[2]["content"])
    assert tool_result["issue"]["id"] == issue["id"]
    # the model actually received the tool result before its final reply
    second_call_messages = llm.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert second_call_messages[-1]["role"] == "tool"


def test_a_research_cost_tool_call_dispatches_to_the_shared_sub_call(database_url, monkeypatch):
    issue, conversation = _issue_with_conversation(database_url)
    monkeypatch.setattr(
        "services.agent._property",
        lambda: {"name": "1 Test St", "locality": "Testville", "city": "Testland",
                 "country": "UK", "notes": ""},
    )
    llm = llm_replying_with(
        tool_call_reply("research_cost", {}),
        text_reply(
            "Washer replacement costs £5-£20, callout fees £60-£90: https://example.com/a"
        ),
        text_reply("Based on that research, £60-£90 is a typical callout fee."),
    )

    reply = conversation_agent.run_conversation_turn(
        conversation["id"], issue["id"], "How did you get that number?", llm
    )

    assert reply == "Based on that research, £60-£90 is a typical callout fee."
    steps = issues_db.get_conversation_steps(conversation["id"])
    assert [s["role"] for s in steps] == ["user", "assistant", "tool", "assistant"]
    assert steps[1]["tool_calls"][0]["function"]["name"] == "research_cost"
    assert "£5-£20" in steps[2]["content"]
    # the sub-call was given the issue's own text, not the follow-up message
    sub_call_messages = llm.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert "The kitchen tap is dripping" in sub_call_messages[0]["content"]


def test_a_find_contractors_tool_call_adds_contractors_without_replacing_existing_ones(
    database_url, monkeypatch
):
    issue = issues_db.save(
        "The boiler is leaking",
        AgentOutcome(status="done", contractors=[ContractorResult(name="Existing Plumbing Co")]),
    )
    conversation = issues_db.create_conversation(issue["id"])
    monkeypatch.setattr(
        "services.agent._property",
        lambda: {"name": "1 Test St", "locality": "Testville", "city": "Testland",
                 "country": "UK", "notes": ""},
    )
    llm = llm_replying_with(
        tool_call_reply("find_contractors", {}),
        text_reply("New Heating Ltd, 0000 000 0002, https://example.com/new-heating-ltd"),
        tool_call_reply(
            "save_contractors",
            {
                "contractors": [
                    {
                        "name": "New Heating Ltd",
                        "trade": "heating",
                        "source_url": "https://example.com/new-heating-ltd",
                        "phone_number": "0000 000 0002",
                    }
                ]
            },
        ),
        text_reply("I've added New Heating Ltd to your shortlist."),
    )

    reply = conversation_agent.run_conversation_turn(
        conversation["id"], issue["id"], "Find me more contractors", llm
    )

    assert reply == "I've added New Heating Ltd to your shortlist."
    contractors = issues_db.list_contractors_for_issue(issue["id"])
    assert {c["name"] for c in contractors} == {"Existing Plumbing Co", "New Heating Ltd"}


def test_a_turn_at_the_cap_is_rejected_without_calling_the_model(database_url):
    issue, conversation = _issue_with_conversation(database_url)
    for i in range(10):
        issues_db.append_step(conversation["id"], role="user", content=f"message {i}")
    llm = llm_replying_with(text_reply("should never be reached"))

    with pytest.raises(issues_db.ConversationCapReached):
        conversation_agent.run_conversation_turn(
            conversation["id"], issue["id"], "one too many", llm
        )

    llm.chat.completions.create.assert_not_called()
