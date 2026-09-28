"""Live evals for the research-cost agent: real model, real web search, costs money.
Run explicitly: `pytest -m eval tests/evals/test_agent_eval.py -s`.

Each run uses the real loop with a capturing `save` in place of the database, so the
assertions are on the AgentOutcome the agent concluded with — before any DB write.
Fixtures are taken from prototypes/synthetic_issues.yaml."""

import pytest
from langfuse import get_client

from models.agent_outcome import AgentOutcome
from services.agent import build_client, run_agent

CLEAR_ISSUE = (
    "The kitchen tap is dripping constantly, even when fully turned off. It's been "
    "getting worse over the last week and there's now a small pool of water forming "
    "under the sink each morning."
)
VAGUE_ISSUE = "Something's wrong in the kitchen, can you sort it out?"


def run_capturing_the_saved_outcome(issue_text: str) -> AgentOutcome:
    saved: list[AgentOutcome] = []
    outcome = run_agent(issue_text, build_client(), save=lambda _text, o: saved.append(o))
    get_client().flush()  # short-lived process: send the trace before pytest exits
    print(f"[eval] issue={issue_text[:50]!r}\n  outcome={outcome.model_dump_json(indent=2)}")
    assert saved == [outcome], "expected exactly one save per run"
    return outcome


@pytest.mark.eval
def test_a_clear_issue_gets_a_sourced_cost_estimate_with_a_valid_range():
    outcome = run_capturing_the_saved_outcome(CLEAR_ISSUE)

    assert outcome.status == "done"
    assert outcome.cost_best is not None
    assert outcome.cost_low is not None
    assert outcome.cost_high is not None
    assert outcome.cost_low <= outcome.cost_high
    assert outcome.cost_low <= outcome.cost_best <= outcome.cost_high
    assert len(outcome.sources) >= 2


@pytest.mark.eval
def test_a_vague_issue_gets_a_clarifying_question_instead_of_an_estimate():
    outcome = run_capturing_the_saved_outcome(VAGUE_ISSUE)

    assert outcome.status == "needs_info"
    assert outcome.clarifying_question
    assert outcome.cost_best is None
