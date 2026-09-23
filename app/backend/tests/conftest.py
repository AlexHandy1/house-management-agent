import pytest

from main import app


@pytest.fixture(autouse=True)
def fake_openrouter_api_key(request, monkeypatch):
    if "eval" in request.keywords:
        return
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    app.state.limiter.reset()
    yield
