import logging

from fastapi.testclient import TestClient

import routers.issue as issue_router
from main import app

client = TestClient(app)


def test_submitting_an_issue_returns_the_agents_response(monkeypatch):
    monkeypatch.setattr(
        issue_router,
        "respond_to_issue",
        lambda issue_text, client: f"Got it: {issue_text}",
    )

    response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})

    assert response.status_code == 200
    assert response.json() == {"response": "Got it: The boiler is leaking"}


def test_submitting_an_issue_logs_that_the_route_was_triggered(monkeypatch, caplog):
    monkeypatch.setattr(
        issue_router, "respond_to_issue", lambda issue_text, client: "some reply"
    )

    with caplog.at_level(logging.INFO):
        client.post("/api/issue", json={"issue_text": "The boiler is leaking"})

    logged_messages = [record.message for record in caplog.records]
    assert "Issue submitted" in logged_messages
    assert not any("boiler" in message.lower() for message in logged_messages)


def test_rejects_issue_text_over_2000_characters_without_calling_the_agent(monkeypatch):
    calls = []
    monkeypatch.setattr(
        issue_router,
        "respond_to_issue",
        lambda issue_text, client: calls.append(issue_text),
    )

    response = client.post("/api/issue", json={"issue_text": "x" * 2001})

    assert response.status_code == 422
    assert calls == []


def test_rejects_empty_issue_text():
    response = client.post("/api/issue", json={"issue_text": ""})

    assert response.status_code == 422
