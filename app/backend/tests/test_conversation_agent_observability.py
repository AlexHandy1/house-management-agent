from types import SimpleNamespace
from unittest.mock import MagicMock

from models.agent_outcome import AgentOutcome
from services import conversation_agent, issues_db


def _issue_with_conversation():
    issue = issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))
    conversation = issues_db.create_conversation(issue["id"])
    return issue, conversation


def _text_reply(content):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_run_conversation_turn_records_the_turn_as_one_langfuse_span(database_url, monkeypatch):
    issue, conversation = _issue_with_conversation()
    fake_llm_client = MagicMock()
    fake_llm_client.chat.completions.create.return_value = _text_reply("Because of a worn washer.")

    fake_span = MagicMock()
    fake_langfuse_client = MagicMock()
    fake_langfuse_client.start_as_current_observation.return_value.__enter__.return_value = (
        fake_span
    )
    monkeypatch.setattr(conversation_agent, "get_client", lambda: fake_langfuse_client)
    fake_propagate = MagicMock()
    fake_propagate.return_value.__enter__.return_value = None
    monkeypatch.setattr(conversation_agent, "propagate_attributes", fake_propagate)

    reply = conversation_agent.run_conversation_turn(
        conversation["id"], issue["id"], "Why that estimate?", fake_llm_client
    )

    fake_propagate.assert_called_once_with(session_id=str(conversation["id"]))
    fake_langfuse_client.start_as_current_observation.assert_called_once_with(
        as_type="span",
        name="run_conversation_turn",
        input="Why that estimate?",
        metadata={"conversation_id": conversation["id"], "turn_number": 1},
    )
    fake_span.update.assert_called_once_with(output=reply)
