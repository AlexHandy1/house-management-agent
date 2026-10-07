"""Live evals for the conversation agent: real model, real DB, real tool calls, costs
money. Run explicitly: `pytest -m eval tests/evals/test_conversation_agent_eval.py -s`.

Each eval seeds an issue with a pre-saved outcome directly via issues_db.save() —
bypassing a real run_agent call, since the conversation agent is what's under test
here, not the one-shot triage agent (already covered by test_agent_eval.py). Fixtures
are taken from prototypes/synthetic_issues.yaml, same source as those evals."""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from langfuse import get_client

from models.agent_outcome import AgentOutcome, ContractorResult
from services import issues_db
from services.agent import build_client
from services.conversation_agent import run_conversation_turn

SYNTHETIC_ISSUES_YAML = (
    Path(__file__).resolve().parents[4] / "prototypes" / "synthetic_issues.yaml"
)


def _issue_text(issue_id: str) -> str:
    issues = yaml.safe_load(SYNTHETIC_ISSUES_YAML.read_text())["issues"]
    return next(issue["text"] for issue in issues if issue["id"] == issue_id)


def _seed_issue_with_estimate() -> dict:
    outcome = AgentOutcome(
        status="done",
        cost_best=Decimal(120),
        cost_low=Decimal(80),
        cost_high=Decimal(200),
        sources=["https://example.com/tap-washer-costs"],
        summary=(
            "A dripping tap is usually a worn washer or O-ring. Replacement washers "
            "cost £5-£20; a plumber's call-out and labour typically runs £80-£150 for "
            "straightforward jobs, UK average."
        ),
        contractors=[ContractorResult(name="Acme Plumbing", trade="plumbing")],
    )
    return issues_db.save(_issue_text("plumbing_001"), outcome)


def _ask(user_message: str) -> tuple[dict, dict, str]:
    issue = _seed_issue_with_estimate()
    conversation = issues_db.create_conversation(issue["id"])
    reply = run_conversation_turn(conversation["id"], issue["id"], user_message, build_client())
    get_client().flush()  # short-lived process: send the trace before pytest exits
    print(f"[eval] message={user_message!r}\n  reply={reply!r}")
    return issue, conversation, reply


def _tool_was_called(conversation_id: int, tool_name: str) -> bool:
    """Reads back the real steps run_conversation_turn persisted — no mocking, so this
    reflects what the live model actually chose to call, not a stubbed assumption."""
    for step in issues_db.get_conversation_steps(conversation_id):
        if step["role"] != "assistant" or not step["tool_calls"]:
            continue
        if any(call["function"]["name"] == tool_name for call in step["tool_calls"]):
            return True
    return False


@pytest.mark.eval
def test_explaining_the_estimate_references_the_saved_reasoning(database_url):
    issue, conversation, reply = _ask("Can you explain why you gave that cost estimate?")

    assert reply
    assert _tool_was_called(conversation["id"], "lookup_issue")
    reply_lower = reply.lower()
    assert "washer" in reply_lower or "£" in reply or "plumber" in reply_lower
    refetched = issues_db.get_issue(issue["id"])
    assert refetched["cost_best"] == Decimal(120)  # no cost-estimate revision tool exists


@pytest.mark.eval
def test_asking_for_the_previous_estimate_gets_the_right_figure_back(database_url):
    _issue, conversation, reply = _ask("How much was the previous cost estimate?")

    assert reply
    assert _tool_was_called(conversation["id"], "lookup_issue")
    assert "120" in reply  # the actual saved cost_best, not a guess or a different figure


@pytest.mark.eval
def test_comparing_a_quote_engages_with_the_difference_without_revising_the_estimate(
    database_url,
):
    issue, conversation, reply = _ask(
        "I've received a quote from a contractor for £350 to fix this. Why might it "
        "differ from your estimate?"
    )

    assert reply
    assert _tool_was_called(conversation["id"], "lookup_issue")
    assert len(reply) > 40  # a substantive answer, not a one-word non-answer
    refetched = issues_db.get_issue(issue["id"])
    assert refetched["cost_best"] == Decimal(120)


@pytest.mark.eval
def test_requesting_a_fresh_comparison_estimate_calls_research_cost_without_revising(
    database_url,
):
    issue, conversation, reply = _ask(
        "Can you get me another cost estimate for this issue to compare with the last one?"
    )

    assert reply
    assert _tool_was_called(conversation["id"], "lookup_issue")
    assert _tool_was_called(conversation["id"], "research_cost")
    refetched = issues_db.get_issue(issue["id"])
    assert refetched["cost_best"] == Decimal(120)  # research_cost informs, never revises


@pytest.mark.eval
def test_finding_more_contractors_adds_to_the_existing_shortlist(database_url):
    issue, conversation, reply = _ask("Can you find me some more contractors for this?")

    assert reply
    assert _tool_was_called(conversation["id"], "lookup_issue")
    assert _tool_was_called(conversation["id"], "find_contractors")
    contractors = issues_db.list_contractors_for_issue(issue["id"])
    names = {c["name"] for c in contractors}
    assert "Acme Plumbing" in names  # existing contractor preserved, not replaced
    assert len(contractors) >= 2  # at least one new one added
