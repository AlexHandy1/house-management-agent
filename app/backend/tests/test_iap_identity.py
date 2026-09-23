from services import iap_identity


def test_extracts_the_email_from_a_valid_iap_jwt(monkeypatch):
    monkeypatch.setenv(iap_identity.AUDIENCE_ENV_VAR, "/projects/123/locations/europe-west1/services/app")
    monkeypatch.setattr(
        iap_identity.id_token,
        "verify_token",
        lambda *args, **kwargs: {"sub": "accounts.google.com:123", "email": "alex@example.com"},
    )

    email = iap_identity.verify_iap_identity("some-jwt")

    assert email == "alex@example.com"


def test_returns_none_without_raising_when_verification_fails(monkeypatch):
    monkeypatch.setenv(iap_identity.AUDIENCE_ENV_VAR, "/projects/123/locations/europe-west1/services/app")

    def raise_verification_error(*args, **kwargs):
        raise ValueError("bad signature")

    monkeypatch.setattr(iap_identity.id_token, "verify_token", raise_verification_error)

    email = iap_identity.verify_iap_identity("some-jwt")

    assert email is None


def test_returns_none_without_verifying_when_audience_is_not_configured(monkeypatch):
    monkeypatch.delenv(iap_identity.AUDIENCE_ENV_VAR, raising=False)
    calls = []
    monkeypatch.setattr(
        iap_identity.id_token, "verify_token", lambda *a, **k: calls.append(1)
    )

    email = iap_identity.verify_iap_identity("some-jwt")

    assert email is None
    assert calls == []
