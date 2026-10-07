from fastapi.testclient import TestClient

import routers.conversations as conversations_router
from main import app
from models.agent_outcome import AgentOutcome
from services import issues_db

client = TestClient(app)


def _issue_with_conversation():
    issue = issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))
    conversation = issues_db.create_conversation(issue["id"])
    return issue, conversation


def test_listing_an_issues_conversations_returns_them_with_their_steps(database_url):
    issue, conversation = _issue_with_conversation()
    issues_db.append_step(conversation["id"], role="user", content="Why that estimate?")

    response = client.get(f"/api/issues/{issue['id']}/conversations")

    assert response.status_code == 200
    [body] = response.json()
    assert body["id"] == conversation["id"]
    assert body["steps"][0]["content"] == "Why that estimate?"


def test_reading_a_conversation_returns_its_steps(database_url):
    _issue, conversation = _issue_with_conversation()
    issues_db.append_step(conversation["id"], role="user", content="Why that estimate?")

    response = client.get(f"/api/conversations/{conversation['id']}")

    assert response.status_code == 200
    assert response.json()["steps"][0]["content"] == "Why that estimate?"


def test_reading_an_unknown_conversation_returns_404(database_url):
    response = client.get("/api/conversations/999")

    assert response.status_code == 404


def test_posting_a_message_runs_the_conversation_agent_and_returns_the_reply(
    database_url, monkeypatch
):
    issue, conversation = _issue_with_conversation()

    def fake_run_conversation_turn(conversation_id, issue_id, user_message, client):
        assert conversation_id == conversation["id"]
        assert issue_id == issue["id"]
        assert user_message == "Why that estimate?"
        issues_db.append_step(conversation_id, role="user", content=user_message)
        issues_db.append_step(conversation_id, role="assistant", content="Because X.")
        return "Because X."

    monkeypatch.setattr(
        conversations_router, "run_conversation_turn", fake_run_conversation_turn
    )

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"message": "Why that estimate?"},
    )

    assert response.status_code == 200
    assert response.json() == {"reply": "Because X.", "turn_number": 1}


def test_posting_a_message_to_an_unknown_conversation_returns_404(database_url, monkeypatch):
    monkeypatch.setattr(
        conversations_router,
        "run_conversation_turn",
        lambda conversation_id, issue_id, user_message, client: "unreachable",
    )

    response = client.post("/api/conversations/999/messages", json={"message": "hello"})

    assert response.status_code == 404


def test_posting_a_message_is_rate_limited_per_ip(database_url, monkeypatch):
    _issue, conversation = _issue_with_conversation()

    def fake_run_conversation_turn(conversation_id, issue_id, user_message, client):
        issues_db.append_step(conversation_id, role="user", content=user_message)
        issues_db.append_step(conversation_id, role="assistant", content="Because X.")
        return "Because X."

    monkeypatch.setattr(
        conversations_router, "run_conversation_turn", fake_run_conversation_turn
    )

    for _ in range(10):
        response = client.post(
            f"/api/conversations/{conversation['id']}/messages", json={"message": "again"}
        )
        assert response.status_code != 429

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages", json={"message": "one more"}
    )

    assert response.status_code == 429


def test_posting_a_message_past_the_cap_returns_409(database_url, monkeypatch):
    _issue, conversation = _issue_with_conversation()

    def raise_cap_reached(conversation_id, issue_id, user_message, client):
        raise issues_db.ConversationCapReached("cap reached")

    monkeypatch.setattr(conversations_router, "run_conversation_turn", raise_cap_reached)

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"message": "one too many"},
    )

    assert response.status_code == 409
