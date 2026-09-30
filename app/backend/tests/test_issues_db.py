import os
from decimal import Decimal
from unittest.mock import MagicMock

import psycopg

from models.agent_outcome import AgentOutcome, ContractorResult
from services import issues_db


def test_the_database_url_is_assembled_from_secret_manager_on_cloud_run(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "house-management-agent")
    monkeypatch.setenv("DB_HOST", "10.20.0.2")
    monkeypatch.setenv("DB_NAME", "house_mgmt")
    monkeypatch.setenv("DB_USER", "house_mgmt_app")
    monkeypatch.setattr(
        issues_db.google.auth, "default", lambda: (None, "house-management-agent")
    )
    fake_secret_client = MagicMock()
    fake_secret_client.access_secret_version.return_value = MagicMock(
        payload=MagicMock(data=b"s3cret-pw")
    )
    monkeypatch.setattr(
        issues_db.secretmanager, "SecretManagerServiceClient", lambda: fake_secret_client
    )

    url = issues_db.get_database_url()

    assert url == "postgresql://house_mgmt_app:s3cret-pw@10.20.0.2/house_mgmt"
    fake_secret_client.access_secret_version.assert_called_once_with(
        request={
            "name": "projects/house-management-agent/secrets/DATABASE_PASSWORD/versions/latest"
        }
    )


def test_a_saved_cost_estimate_can_be_listed_back_with_its_sources(database_url):
    outcome = AgentOutcome(
        status="done",
        cost_best=Decimal(225),
        cost_low=Decimal(150),
        cost_high=Decimal(300),
        sources=["https://example.com/a", "https://example.com/b"],
        summary="Full breakdown of typical costs for a dripping tap...",
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
    assert issue["agent_summary"] == "Full breakdown of typical costs for a dripping tap..."


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


def test_an_issue_saved_with_contractors_is_listed_as_having_a_contractor(database_url):
    outcome = AgentOutcome(
        status="done",
        contractors=[
            ContractorResult(
                name="Test Plumbing Co",
                trade="plumbing/heating",
                source_url="https://example.com/test-plumbing-co",
                phone_number="0000 000 0001",
            ),
            ContractorResult(
                name="Sample Heating Ltd",
                trade="plumbing/heating",
                source_url="https://example.com/sample-heating-ltd",
                email="contact@example.com",
            ),
        ],
    )

    issues_db.save("The boiler is leaking", outcome)

    [issue] = issues_db.list_issues()
    assert issue["has_contractor"] is True


def test_an_issue_saved_without_contractors_is_not_listed_as_having_a_contractor(database_url):
    issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))

    [issue] = issues_db.list_issues()
    assert issue["has_contractor"] is False


def test_the_same_contractor_can_be_linked_to_more_than_one_issue_without_duplicating_it(
    database_url,
):
    test_contractor = ContractorResult(
        name="Test Plumbing Co",
        trade="plumbing/heating",
        source_url="https://example.com/test-plumbing-co",
        phone_number="0000 000 0001",
    )

    issues_db.save(
        "The boiler is leaking", AgentOutcome(status="done", contractors=[test_contractor])
    )
    issues_db.save("No hot water", AgentOutcome(status="done", contractors=[test_contractor]))

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        [(count,)] = conn.execute(
            "SELECT COUNT(*) FROM contractors WHERE name = %s", (test_contractor.name,)
        ).fetchall()
    assert count == 1
    boiler_issue, hot_water_issue = sorted(issues_db.list_issues(), key=lambda i: i["id"])
    assert boiler_issue["has_contractor"] is True
    assert hot_water_issue["has_contractor"] is True


def test_issues_are_listed_newest_first(database_url):
    for text in ["first issue", "second issue", "third issue"]:
        issues_db.save(text, AgentOutcome(status="failed"))

    assert [issue["source_text"] for issue in issues_db.list_issues()] == [
        "third issue",
        "second issue",
        "first issue",
    ]
