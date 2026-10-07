import logging
import os
from decimal import Decimal

import psycopg
from fastapi.testclient import TestClient

import routers.issue as issue_router
from main import app
from models.agent_outcome import AgentOutcome, ContractorResult
from services import issues_db

client = TestClient(app)


def test_submitting_an_issue_returns_the_agents_outcome(database_url, monkeypatch):
    outcome = AgentOutcome(
        status="done",
        cost_best=Decimal(225),
        cost_low=Decimal(150),
        cost_high=Decimal(300),
        sources=["https://example.com/a"],
        summary="Full breakdown of typical costs for a dripping tap...",
    )

    def fake_run_agent(issue_text, client, save):
        save(issue_text, outcome)
        return outcome

    monkeypatch.setattr(issue_router, "run_agent", fake_run_agent)

    response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})

    assert response.status_code == 200
    body = response.json()
    assert body.pop("conversation_id") is not None
    assert body == {
        "status": "done",
        "cost_best": "225",
        "cost_low": "150",
        "cost_high": "300",
        "sources": ["https://example.com/a"],
        "clarifying_question": None,
        "summary": "Full breakdown of typical costs for a dripping tap...",
        "contractors": [],
    }


def test_submitting_an_issue_creates_a_conversation_linked_to_the_saved_issue(
    database_url, monkeypatch
):
    outcome = AgentOutcome(status="done")

    def fake_run_agent(issue_text, client, save):
        save(issue_text, outcome)
        return outcome

    monkeypatch.setattr(issue_router, "run_agent", fake_run_agent)

    response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})

    conversation_id = response.json()["conversation_id"]
    [issue] = issues_db.list_issues()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        [(linked_issue_id,)] = conn.execute(
            "SELECT issue_id FROM conversations WHERE id = %s", (conversation_id,)
        ).fetchall()
    assert linked_issue_id == issue["id"]


def test_submitting_an_issue_returns_the_agents_contractor_picks(database_url, monkeypatch):
    outcome = AgentOutcome(
        status="done",
        contractors=[
            ContractorResult(
                name="Test Plumbing Co",
                trade="plumbing/heating",
                source_url="https://example.com/test-plumbing-co",
                phone_number="0000 000 0001",
            )
        ],
    )

    def fake_run_agent(issue_text, client, save):
        save(issue_text, outcome)
        return outcome

    monkeypatch.setattr(issue_router, "run_agent", fake_run_agent)

    response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})

    assert response.status_code == 200
    assert response.json()["contractors"] == [
        {
            "name": "Test Plumbing Co",
            "trade": "plumbing/heating",
            "source_url": "https://example.com/test-plumbing-co",
            "email": None,
            "phone_number": "0000 000 0001",
        }
    ]


def test_submitting_an_issue_logs_that_the_route_was_triggered(database_url, monkeypatch, caplog):
    def fake_run_agent(issue_text, client, save):
        outcome = AgentOutcome(status="failed")
        save(issue_text, outcome)
        return outcome

    monkeypatch.setattr(issue_router, "run_agent", fake_run_agent)

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


def test_getting_issues_shows_whether_each_issue_has_a_linked_contractor(database_url):
    issues_db.save(
        "The boiler is leaking",
        AgentOutcome(
            status="done",
            contractors=[ContractorResult(name="Test Plumbing Co")],
        ),
    )
    issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))

    response = client.get("/api/issues")

    by_text = {issue["source_text"]: issue["has_contractor"] for issue in response.json()}
    assert by_text == {
        "The boiler is leaking": True,
        "The kitchen tap is dripping": False,
    }
