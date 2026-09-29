import os

import psycopg
import pytest

from main import app
from services import issues_db

TEST_DATABASE_NAME = "house_mgmt_test"
LOCAL_POSTGRES_URL = "postgresql://postgres:postgres@localhost:5432"


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


@pytest.fixture
def database_url(monkeypatch):
    """A clean issues table in a dedicated test database on the local Postgres
    (`docker compose up -d`), exposed to the code under test via DATABASE_URL."""
    base_url = os.environ.get("TEST_DATABASE_BASE_URL", LOCAL_POSTGRES_URL)
    with psycopg.connect(f"{base_url}/postgres", autocommit=True) as admin:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DATABASE_NAME,)
        ).fetchone()
        if not exists:
            admin.execute(f"CREATE DATABASE {TEST_DATABASE_NAME}")
    url = f"{base_url}/{TEST_DATABASE_NAME}"
    monkeypatch.setenv("DATABASE_URL", url)
    issues_db.init_schema()
    with psycopg.connect(url) as conn:
        conn.execute("TRUNCATE issues RESTART IDENTITY")
    return url
