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
