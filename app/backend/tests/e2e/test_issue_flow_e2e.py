"""Real browser end-to-end test: submits an issue through the running frontend,
lets the real agent research and save it, and confirms the issue shows up in the
issues table. Costs money (real agent run) and needs Postgres, the backend and
the frontend already running locally (docker compose, uvicorn, vite).

Run explicitly: `pytest -m e2e tests/e2e/test_issue_flow_e2e.py -s`
"""

import subprocess

import httpx
import pytest

FRONTEND_URL = "http://localhost:5173/"
BACKEND_HEALTH_URL = "http://localhost:8000/health"

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
