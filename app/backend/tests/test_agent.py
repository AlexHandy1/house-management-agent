import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import agent


@pytest.fixture(autouse=True)
def no_langfuse(monkeypatch):
    monkeypatch.setattr(agent, "get_client", lambda: MagicMock())


def tool_call_reply(name, arguments):
    call = SimpleNamespace(
        id="call_1",
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )
    message = SimpleNamespace(content=None, tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")])


def text_reply(content):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def llm_replying_with(*replies):
    llm = MagicMock()
    llm.chat.completions.create.side_effect = list(replies)
    return llm


def test_the_agent_saves_the_cost_estimate_it_commits_to():
    llm = llm_replying_with(
        tool_call_reply("save_cost_estimate", {"best": 225, "low": 150, "high": 300})
    )
    saved = []

    outcome = agent.run_agent(
        "The kitchen tap is dripping", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("The kitchen tap is dripping", outcome)]
    assert outcome.status == "done"
    assert (outcome.cost_best, outcome.cost_low, outcome.cost_high) == (
        Decimal(225),
        Decimal(150),
        Decimal(300),
    )


def test_the_sources_saved_with_an_estimate_are_the_urls_the_cost_research_found():
    llm = llm_replying_with(
        tool_call_reply("research_cost", {}),
        text_reply(
            "Replacement tap washers cost £5-£20 (https://example.com/a), plumbers charge "
            "£60-£90 per hour: https://example.com/b, see also https://example.com/a."
        ),
        tool_call_reply("save_cost_estimate", {"best": 120, "low": 80, "high": 200}),
    )
    saved = []

    outcome = agent.run_agent(
        "The kitchen tap is dripping", llm, save=lambda text, o: saved.append((text, o))
    )

    assert outcome.sources == ["https://example.com/a", "https://example.com/b"]
    assert saved == [("The kitchen tap is dripping", outcome)]


def test_the_agent_saves_a_clarifying_question_when_the_issue_is_too_vague():
    llm = llm_replying_with(
        tool_call_reply("save_clarifying_question", {"question": "Which room is affected?"})
    )
    saved = []

    outcome = agent.run_agent(
        "Something is broken", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("Something is broken", outcome)]
    assert outcome.status == "needs_info"
    assert outcome.clarifying_question == "Which room is affected?"
    assert outcome.cost_best is None


def test_a_failed_outcome_is_saved_when_the_agent_stops_without_saving_a_result():
    llm = llm_replying_with(text_reply("It's probably a washer."))
    saved = []

    outcome = agent.run_agent(
        "The tap drips", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("The tap drips", outcome)]
    assert outcome.status == "failed"
