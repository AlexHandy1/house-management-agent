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
