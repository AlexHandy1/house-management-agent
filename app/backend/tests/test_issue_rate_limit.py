from fastapi.testclient import TestClient

import routers.issue as issue_router
from main import app
from models.agent_outcome import AgentOutcome

client = TestClient(app)


def _fake_run_agent(issue_text, client, save):
    outcome = AgentOutcome(status="failed")
    save(issue_text, outcome)
    return outcome


def test_requests_within_the_per_ip_rate_limit_are_not_blocked(database_url, monkeypatch):
    monkeypatch.setattr(issue_router, "run_agent", _fake_run_agent)

    for _ in range(10):
        response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})
        assert response.status_code == 200


def test_exceeding_the_per_ip_rate_limit_returns_429(database_url, monkeypatch):
    monkeypatch.setattr(issue_router, "run_agent", _fake_run_agent)

    for _ in range(10):
        response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})
        assert response.status_code != 429

    response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})

    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"
