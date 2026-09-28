from decimal import Decimal

from models.agent_outcome import AgentOutcome
from services import issues_db


def test_a_saved_cost_estimate_can_be_listed_back_with_its_sources(database_url):
    outcome = AgentOutcome(
        status="done",
        cost_best=Decimal(225),
        cost_low=Decimal(150),
        cost_high=Decimal(300),
        sources=["https://example.com/a", "https://example.com/b"],
    )

    issues_db.save("The kitchen tap is dripping", outcome)

    [issue] = issues_db.list_issues()
    assert issue["source_text"] == "The kitchen tap is dripping"
    assert issue["status"] == "done"
    assert (issue["cost_best"], issue["cost_low"], issue["cost_high"]) == (
        Decimal(225),
        Decimal(150),
        Decimal(300),
    )
    assert issue["supporting_web_sources"] == ["https://example.com/a", "https://example.com/b"]


def test_a_clarifying_question_and_a_failed_run_are_stored_without_cost_estimates(database_url):
    issues_db.save(
        "Something is broken",
        AgentOutcome(status="needs_info", clarifying_question="Which room is affected?"),
    )
    issues_db.save("The boiler is leaking", AgentOutcome(status="failed"))

    failed, needs_info = issues_db.list_issues()
    assert failed["status"] == "failed"
    assert failed["cost_best"] is None
    assert needs_info["status"] == "needs_info"
    assert needs_info["clarifying_question"] == "Which room is affected?"
    assert needs_info["cost_best"] is None
    assert needs_info["supporting_web_sources"] == []


def test_issues_are_listed_newest_first(database_url):
    for text in ["first issue", "second issue", "third issue"]:
        issues_db.save(text, AgentOutcome(status="failed"))

    assert [issue["source_text"] for issue in issues_db.list_issues()] == [
        "third issue",
        "second issue",
        "first issue",
    ]
