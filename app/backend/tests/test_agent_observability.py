import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from services import agent


class FakeCompletionResponse:
    def __init__(self, content: str):
        self.choices = [MagicMock(message=MagicMock(content=content))]


def test_respond_to_issue_records_a_langfuse_generation(monkeypatch):
    fake_llm_client = MagicMock()
    fake_llm_client.chat.completions.create.return_value = FakeCompletionResponse(
        "Contact a plumber."
    )

    fake_generation = MagicMock()
    fake_langfuse_client = MagicMock()
    fake_langfuse_client.start_as_current_observation.return_value.__enter__.return_value = (
        fake_generation
    )
    monkeypatch.setattr(agent, "get_client", lambda: fake_langfuse_client)

    reply = agent.respond_to_issue("The boiler is leaking", fake_llm_client)

    assert reply == "Contact a plumber."
    fake_langfuse_client.start_as_current_observation.assert_called_once_with(
        as_type="generation",
        name="respond_to_issue",
        model=agent.MODEL,
        input="The boiler is leaking",
    )
    fake_generation.update.assert_called_once_with(output="Contact a plumber.")


def test_run_agent_records_the_whole_run_as_one_langfuse_span(monkeypatch):
    save_call = SimpleNamespace(
        id="call_1",
        type="function",
        function=SimpleNamespace(
            name="save_cost_estimate",
            arguments=json.dumps({"best": 225, "low": 150, "high": 300}),
        ),
    )
    reply = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[save_call]))]
    )
    fake_llm_client = MagicMock()
    fake_llm_client.chat.completions.create.return_value = reply

    fake_span = MagicMock()
    fake_langfuse_client = MagicMock()
    fake_langfuse_client.start_as_current_observation.return_value.__enter__.return_value = (
        fake_span
    )
    monkeypatch.setattr(agent, "get_client", lambda: fake_langfuse_client)

    outcome = agent.run_agent("The boiler is leaking", fake_llm_client, save=lambda text, o: None)

    fake_langfuse_client.start_as_current_observation.assert_called_once_with(
        as_type="span", name="run_agent", input="The boiler is leaking"
    )
    fake_span.update.assert_called_once_with(output=outcome.model_dump(mode="json"))
