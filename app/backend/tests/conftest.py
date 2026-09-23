import pytest

from main import app  # noqa: F401  (import triggers main's load_dotenv() for all tests)


@pytest.fixture(autouse=True)
def fake_openrouter_api_key(request, monkeypatch):
    if "eval" in request.keywords:
        return
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
