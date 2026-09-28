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
