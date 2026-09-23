import pytest

from main import app


@pytest.fixture(autouse=True)
def fake_openrouter_api_key(request, monkeypatch):
    if "eval" in request.keywords:
        return
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def fake_langfuse_keys(request, monkeypatch):
    """Keeps unit tests from ever sending real trace data to the production
    Langfuse project: conftest's `from main import app` above already loads the
    real keys from .env for every test via load_dotenv(). Only the eval tests
    (which deliberately hit real external services) should see the real keys."""
    if "eval" in request.keywords:
        return
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-public-key")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret-key")


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    app.state.limiter.reset()
    yield
