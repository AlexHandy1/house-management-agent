import logging
from decimal import Decimal

from fastapi.testclient import TestClient

import routers.issue as issue_router
from main import app
from models.agent_outcome import AgentOutcome
from services import issues_db

client = TestClient(app)


def test_submitting_an_issue_returns_the_agents_outcome(monkeypatch):
    outcome = AgentOutcome(
        status="done",
        cost_best=Decimal(225),
        cost_low=Decimal(150),
        cost_high=Decimal(300),
        sources=["https://example.com/a"],
        summary="Full breakdown of typical costs for a dripping tap...",
    )
    monkeypatch.setattr(
        issue_router, "run_agent", lambda issue_text, client, save: outcome
    )

    response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "done",
        "cost_best": "225",
        "cost_low": "150",
        "cost_high": "300",
        "sources": ["https://example.com/a"],
        "clarifying_question": None,
        "summary": "Full breakdown of typical costs for a dripping tap...",
    }


def test_submitting_an_issue_logs_that_the_route_was_triggered(monkeypatch, caplog):
    monkeypatch.setattr(
        issue_router,
        "run_agent",
        lambda issue_text, client, save: AgentOutcome(status="failed"),
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
        "run_agent",
        lambda issue_text, client, save: calls.append(issue_text),
    )

    response = client.post("/api/issue", json={"issue_text": "x" * 2001})

    assert response.status_code == 422
    assert calls == []


def test_rejects_empty_issue_text():
    response = client.post("/api/issue", json={"issue_text": ""})

    assert response.status_code == 422


def test_getting_issues_returns_previously_saved_issues_newest_first(database_url):
    issues_db.save("first issue", AgentOutcome(status="failed"))
    issues_db.save("second issue", AgentOutcome(status="failed"))

    response = client.get("/api/issues")

    assert response.status_code == 200
    assert [issue["source_text"] for issue in response.json()] == [
        "second issue",
        "first issue",
    ]
