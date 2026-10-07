import logging
import os
from decimal import Decimal

import psycopg
import pytest

from models.agent_outcome import AgentOutcome, ContractorResult
from services import issues_db


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


def test_saving_an_issue_logs_the_issue_id_and_contractor_count_without_the_issue_text(
    database_url, caplog
):
    outcome = AgentOutcome(
        status="done",
        contractors=[
            ContractorResult(name="Test Plumbing Co"),
            ContractorResult(name="Sample Heating Ltd"),
        ],
    )

    with caplog.at_level(logging.INFO):
        row = issues_db.save("The boiler is leaking", outcome)

    matching = [
        record
        for record in caplog.records
        if getattr(record, "issue_id", None) == row["id"]
    ]
    assert matching, "expected a log record tagged with the saved issue's id"
    assert getattr(matching[0], "contractor_count", None) == 2
    assert not any("boiler" in record.getMessage().lower() for record in caplog.records)


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


def test_add_contractors_to_issue_links_them_without_touching_the_issue_row(database_url):
    issue = issues_db.save("The boiler is leaking", AgentOutcome(status="done"))

    issues_db.add_contractors_to_issue(
        issue["id"], [ContractorResult(name="Test Plumbing Co", trade="plumbing/heating")]
    )

    contractors = issues_db.list_contractors_for_issue(issue["id"])
    assert [c["name"] for c in contractors] == ["Test Plumbing Co"]
    [refetched] = issues_db.list_issues()
    assert refetched["source_text"] == "The boiler is leaking"


def test_add_contractors_to_issue_is_additive_not_replacing(database_url):
    issue = issues_db.save(
        "The boiler is leaking",
        AgentOutcome(status="done", contractors=[ContractorResult(name="Test Plumbing Co")]),
    )

    issues_db.add_contractors_to_issue(issue["id"], [ContractorResult(name="Sample Heating Ltd")])

    contractors = issues_db.list_contractors_for_issue(issue["id"])
    assert {c["name"] for c in contractors} == {"Test Plumbing Co", "Sample Heating Ltd"}


def test_a_created_conversation_is_linked_to_its_issue(database_url):
    issue = issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))

    conversation = issues_db.create_conversation(issue["id"])

    assert conversation["issue_id"] == issue["id"]


def test_appended_steps_are_retrievable_in_order_tagged_with_their_turn_number(database_url):
    issue = issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))
    conversation = issues_db.create_conversation(issue["id"])

    issues_db.append_step(conversation["id"], role="user", content="Why that estimate?")
    issues_db.append_step(
        conversation["id"],
        role="assistant",
        content=None,
        tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "lookup_issue"}}],
    )
    issues_db.append_step(
        conversation["id"], role="tool", content="issue details...", tool_call_id="call_1"
    )

    steps = issues_db.get_conversation_steps(conversation["id"])
    assert [step["role"] for step in steps] == ["user", "assistant", "tool"]
    assert [step["turn_number"] for step in steps] == [1, 1, 1]
    assert steps[0]["content"] == "Why that estimate?"
    assert steps[1]["tool_calls"][0]["function"]["name"] == "lookup_issue"
    assert steps[2]["tool_call_id"] == "call_1"


def test_a_second_user_message_starts_a_new_turn_number(database_url):
    issue = issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))
    conversation = issues_db.create_conversation(issue["id"])

    issues_db.append_step(conversation["id"], role="user", content="Why that estimate?")
    issues_db.append_step(conversation["id"], role="assistant", content="Because X.")
    issues_db.append_step(conversation["id"], role="user", content="Find me more contractors")

    steps = issues_db.get_conversation_steps(conversation["id"])
    assert [step["turn_number"] for step in steps] == [1, 1, 2]


def test_an_eleventh_user_turn_is_rejected_by_the_conversation_cap(database_url):
    issue = issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))
    conversation = issues_db.create_conversation(issue["id"])

    for i in range(10):
        issues_db.append_step(conversation["id"], role="user", content=f"message {i}")

    with pytest.raises(issues_db.ConversationCapReached):
        issues_db.append_step(conversation["id"], role="user", content="one too many")


def test_get_issue_returns_the_issue_row(database_url):
    saved = issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))

    issue = issues_db.get_issue(saved["id"])

    assert issue["source_text"] == "The kitchen tap is dripping"


def test_list_contractors_for_issue_returns_its_linked_contractors(database_url):
    issue = issues_db.save(
        "The boiler is leaking",
        AgentOutcome(
            status="done",
            contractors=[
                ContractorResult(name="Test Plumbing Co", trade="plumbing/heating"),
                ContractorResult(name="Sample Heating Ltd", trade="plumbing/heating"),
            ],
        ),
    )

    contractors = issues_db.list_contractors_for_issue(issue["id"])

    assert {c["name"] for c in contractors} == {"Test Plumbing Co", "Sample Heating Ltd"}


def test_list_conversations_for_issue_includes_each_conversations_steps(database_url):
    issue = issues_db.save("The kitchen tap is dripping", AgentOutcome(status="done"))
    first = issues_db.create_conversation(issue["id"])
    second = issues_db.create_conversation(issue["id"])
    issues_db.append_step(first["id"], role="user", content="Why that estimate?")
    issues_db.append_step(second["id"], role="user", content="Find me more contractors")

    conversations = issues_db.list_conversations_for_issue(issue["id"])

    assert [c["id"] for c in conversations] == [first["id"], second["id"]]
    assert [step["content"] for step in conversations[0]["steps"]] == ["Why that estimate?"]
    assert [step["content"] for step in conversations[1]["steps"]] == ["Find me more contractors"]


def test_lookup_issue_composes_the_issue_contractors_and_conversations(database_url):
    issue = issues_db.save(
        "The boiler is leaking",
        AgentOutcome(status="done", contractors=[ContractorResult(name="Test Plumbing Co")]),
    )
    conversation = issues_db.create_conversation(issue["id"])
    issues_db.append_step(conversation["id"], role="user", content="Why that estimate?")

    result = issues_db.lookup_issue(issue["id"])

    assert result["issue"]["id"] == issue["id"]
    assert [c["name"] for c in result["contractors"]] == ["Test Plumbing Co"]
    assert [c["id"] for c in result["conversations"]] == [conversation["id"]]
    assert result["conversations"][0]["steps"][0]["content"] == "Why that estimate?"


def test_issues_are_listed_newest_first(database_url):
    for text in ["first issue", "second issue", "third issue"]:
        issues_db.save(text, AgentOutcome(status="failed"))

    assert [issue["source_text"] for issue in issues_db.list_issues()] == [
        "third issue",
        "second issue",
        "first issue",
    ]
