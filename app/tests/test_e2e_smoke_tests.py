"""Real browser end-to-end tests against the full running stack (Postgres, the
backend, the frontend) — genuine e2e, as opposed to the backend's own
tests/e2e/ which only drove the backend through a browser against a test
database. Costs money (real agent run) and hits real external sites (the news
feed job). Needs Postgres, the backend and the frontend already running
locally (docker compose, uvicorn, vite).

Run explicitly: `pytest -m e2e app/tests -s`
"""

import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import psycopg
import pytest

FRONTEND_URL = "http://localhost:5173/"
BACKEND_URL = "http://localhost:8000"
BACKEND_HEALTH_URL = f"{BACKEND_URL}/health"

# Matches the local Postgres docker-compose.yml brings up, and the default
# DATABASE_URL app/backend/.env points at.
LOCAL_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/house_mgmt"

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
BACKEND_PYTHON = BACKEND_DIR / "venv" / "bin" / "python"

# Matches jobs.pull_news_feed.DEFAULT_LOOKBACK_DAYS — passed explicitly rather
# than relying on the Job's own default, so this test doesn't silently drift
# if that default ever changes.
NEWS_FEED_LOOKBACK_DAYS = 2

# Matches prototypes/synthetic_issues.yaml plumbing_001 — known from the live
# evals (tests/evals/test_agent_eval.py) to reliably produce a `done` outcome.
ISSUE_TEXT = (
    "The kitchen tap is dripping constantly, even when fully turned off. It's been "
    "getting worse over the last week and there's now a small pool of water forming "
    "under the sink each morning."
)


def run_agent_browser(*args: str) -> str:
    result = subprocess.run(
        ["agent-browser", *args], capture_output=True, text=True, timeout=70, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"agent-browser {' '.join(args)} failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout


def require_running(name: str, url: str) -> None:
    try:
        response = httpx.get(url, timeout=5)
    except httpx.HTTPError as exc:
        pytest.fail(f"{name} is not reachable at {url}: {exc}")
    if response.status_code != 200:
        pytest.fail(f"{name} at {url} returned {response.status_code}, expected 200")


def reset_articles_table() -> None:
    with psycopg.connect(LOCAL_DATABASE_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE articles RESTART IDENTITY")


def run_news_feed_job() -> None:
    result = subprocess.run(
        [
            str(BACKEND_PYTHON),
            "-m",
            "jobs.pull_news_feed",
            "--lookback-days",
            str(NEWS_FEED_LOOKBACK_DAYS),
        ],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"news feed job failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


@pytest.mark.e2e
def test_submitting_an_issue_through_the_browser_saves_it_and_shows_it_in_the_table():
    require_running("backend", BACKEND_HEALTH_URL)
    require_running("frontend", FRONTEND_URL)

    try:
        run_agent_browser("open", FRONTEND_URL, "--headed")
        run_agent_browser("find", "label", "Describe the issue", "fill", ISSUE_TEXT)
        run_agent_browser("find", "role", "button", "click", "--name", "Submit")

        # The real agent run (web search + reasoning) takes roughly 15-20s.
        run_agent_browser("wait", "--text", "Estimated cost", "--timeout", "60000")

        # The research findings should be shown in full, not just the headline
        # numbers (regression: this was previously wired to the wrong field and
        # silently rendered nothing).
        summary_text = run_agent_browser("get", "text", ".agent-summary")
        assert len(summary_text.strip()) > 50, (
            f"expected a substantial research summary, got: {summary_text!r}"
        )

        # plumbing_001 reliably produces contractors too (live evals) — confirms the
        # find_contractors/save_contractors wiring end-to-end, not just cost estimation.
        contractors_text = run_agent_browser("get", "text", ".agent-contractors")
        assert len(contractors_text.strip()) > 0, (
            f"expected at least one contractor shown, got: {contractors_text!r}"
        )

        # The issues table only appears after the post-submit refetch, which
        # happens slightly after the outcome text renders.
        run_agent_browser("wait", "table", "--timeout", "10000")

        table_text = run_agent_browser("get", "text", "table")
        assert ISSUE_TEXT[:60] in table_text
    finally:
        run_agent_browser("close")


@pytest.mark.e2e
def test_running_the_news_feed_job_shows_the_pulled_articles_in_the_frontend():
    require_running("backend", BACKEND_HEALTH_URL)
    require_running("frontend", FRONTEND_URL)

    reset_articles_table()
    run_news_feed_job()

    response = httpx.get(f"{BACKEND_URL}/api/news-feed", timeout=10)
    response.raise_for_status()
    articles = response.json()
    assert len(articles) > 0, "expected the job to pull at least one article"

    cutoff = datetime.now(UTC).date() - timedelta(days=NEWS_FEED_LOOKBACK_DAYS)
    published_dates = [date.fromisoformat(article["published_date"]) for article in articles]
    assert all(published >= cutoff for published in published_dates), (
        f"expected every article within the last {NEWS_FEED_LOOKBACK_DAYS} days, "
        f"got {published_dates}"
    )
    assert published_dates == sorted(published_dates, reverse=True), (
        "expected articles newest-first"
    )

    try:
        run_agent_browser("open", FRONTEND_URL, "--headed")
        run_agent_browser("wait", ".article-card", "--timeout", "10000")

        first_card_title = run_agent_browser("get", "text", ".article-card:first-of-type h3")
        assert articles[0]["title"].lower() in first_card_title.lower()

        card_count = int(run_agent_browser("get", "count", ".article-card").strip())
        assert card_count == len(articles)
        assert card_count <= 10, (
            f"expected no more than 10 articles shown (GET /api/news-feed's own cap), "
            f"got {card_count}"
        )
    finally:
        run_agent_browser("close")
