import logging

from fastapi.testclient import TestClient

import main
from services import iap_identity


def test_logs_the_verified_iap_identity_on_a_request(monkeypatch, caplog):
    monkeypatch.setattr(iap_identity, "verify_iap_identity", lambda jwt: "alex@example.com")
    client = TestClient(main.app)

    with caplog.at_level(logging.INFO):
        response = client.get("/health", headers={"X-Goog-IAP-JWT-Assertion": "some-jwt"})

    assert response.status_code == 200
    assert any(
        getattr(record, "iap_email", None) == "alex@example.com" for record in caplog.records
    )


def test_does_not_attempt_verification_when_no_iap_header_present(monkeypatch):
    calls = []
    monkeypatch.setattr(iap_identity, "verify_iap_identity", lambda jwt: calls.append(jwt))
    client = TestClient(main.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert calls == []
