from fastapi.testclient import TestClient

import routers.issue as issue_router
from main import app

client = TestClient(app)


def test_requests_within_the_per_ip_rate_limit_are_not_blocked(monkeypatch):
    monkeypatch.setattr(
        issue_router, "respond_to_issue", lambda issue_text, client: "ok"
    )

    for _ in range(10):
        response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})
        assert response.status_code == 200


def test_exceeding_the_per_ip_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr(
        issue_router, "respond_to_issue", lambda issue_text, client: "ok"
    )

    for _ in range(10):
        response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})
        assert response.status_code != 429

    response = client.post("/api/issue", json={"issue_text": "The boiler is leaking"})

    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"
