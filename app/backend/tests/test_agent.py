import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from openai import APIConnectionError

from services import agent


@pytest.fixture(autouse=True)
def no_langfuse(monkeypatch):
    monkeypatch.setattr(agent, "get_client", lambda: MagicMock())


def tool_call_reply(name, arguments, content=None):
    call = SimpleNamespace(
        id="call_1",
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )
    message = SimpleNamespace(content=content, tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")])


def text_reply(content):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def empty_choices_reply():
    return SimpleNamespace(choices=[], model_dump=lambda: {"choices": []})


def llm_replying_with(*replies):
    llm = MagicMock()
    llm.chat.completions.create.side_effect = list(replies)
    return llm


def test_the_agent_saves_the_cost_estimate_it_commits_to():
    llm = llm_replying_with(
        tool_call_reply("save_cost_estimate", {"best": 225, "low": 150, "high": 300}),
        text_reply("Done."),
    )
    saved = []

    outcome = agent.run_agent(
        "The kitchen tap is dripping", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("The kitchen tap is dripping", outcome)]
    assert outcome.status == "done"
    assert (outcome.cost_best, outcome.cost_low, outcome.cost_high) == (
        Decimal(225),
        Decimal(150),
        Decimal(300),
    )


def test_the_agent_can_save_a_cost_estimate_and_then_keep_working_in_the_same_run():
    llm = llm_replying_with(
        tool_call_reply("save_cost_estimate", {"best": 225, "low": 150, "high": 300}),
        tool_call_reply("find_contractors", {}),
        text_reply("Test Plumbing Co, https://example.com/test-plumbing-co"),  # sub-call findings
        text_reply("Done."),
    )
    saved = []

    outcome = agent.run_agent(
        "The kitchen tap is dripping", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("The kitchen tap is dripping", outcome)]
    assert (outcome.cost_best, outcome.cost_low, outcome.cost_high) == (
        Decimal(225),
        Decimal(150),
        Decimal(300),
    )
    # all four queued model replies were consumed — the loop kept going past the
    # save_cost_estimate call instead of ending the run on the first save
    assert llm.chat.completions.create.call_count == 4


def test_the_sources_saved_with_an_estimate_are_the_urls_the_cost_research_found():
    llm = llm_replying_with(
        tool_call_reply("research_cost", {}),
        text_reply(
            "Replacement tap washers cost £5-£20 (https://example.com/a), plumbers charge "
            "£60-£90 per hour: https://example.com/b, see also https://example.com/a."
        ),
        tool_call_reply("save_cost_estimate", {"best": 120, "low": 80, "high": 200}),
        text_reply("Done."),
    )
    saved = []

    outcome = agent.run_agent(
        "The kitchen tap is dripping", llm, save=lambda text, o: saved.append((text, o))
    )

    assert outcome.sources == ["https://example.com/a", "https://example.com/b"]
    assert saved == [("The kitchen tap is dripping", outcome)]


def test_the_research_findings_are_saved_as_the_outcomes_full_summary():
    llm = llm_replying_with(
        tool_call_reply("research_cost", {}),
        text_reply(
            "Replacement tap washers cost £5-£20, plumbers charge £60-£90 per hour: "
            "https://example.com/a."
        ),
        tool_call_reply("save_cost_estimate", {"best": 120, "low": 80, "high": 200}),
        text_reply("Done."),
    )
    saved = []

    outcome = agent.run_agent(
        "The kitchen tap is dripping", llm, save=lambda text, o: saved.append((text, o))
    )

    assert outcome.summary == (
        "Replacement tap washers cost £5-£20, plumbers charge £60-£90 per hour: "
        "https://example.com/a."
    )


def test_the_agent_saves_the_contractors_it_shortlists():
    llm = llm_replying_with(
        tool_call_reply("find_contractors", {}),
        text_reply("Test Plumbing Co, 0000 000 0001, https://example.com/test-plumbing-co"),
        tool_call_reply(
            "save_contractors",
            {
                "contractors": [
                    {
                        "name": "Test Plumbing Co",
                        "trade": "plumbing",
                        "source_url": "https://example.com/test-plumbing-co",
                        "phone_number": "0000 000 0001",
                    }
                ]
            },
        ),
        text_reply("Done."),
    )
    saved = []

    outcome = agent.run_agent(
        "The boiler is leaking", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("The boiler is leaking", outcome)]
    assert outcome.status == "done"
    assert outcome.contractors == [
        agent.ContractorResult(
            name="Test Plumbing Co",
            trade="plumbing",
            source_url="https://example.com/test-plumbing-co",
            phone_number="0000 000 0001",
        )
    ]


def test_the_agent_can_save_contractors_without_a_cost_estimate_when_only_that_is_asked_for():
    llm = llm_replying_with(
        tool_call_reply("find_contractors", {}),
        text_reply("Test Plumbing Co, https://example.com/test-plumbing-co"),
        tool_call_reply(
            "save_contractors",
            {"contractors": [{"name": "Test Plumbing Co"}]},
        ),
        text_reply("Done."),
    )
    saved = []

    outcome = agent.run_agent(
        "Do we already have a contractor for the boiler?",
        llm,
        save=lambda text, o: saved.append((text, o)),
    )

    assert outcome.status == "done"
    assert outcome.cost_best is None
    assert len(outcome.contractors) == 1
    assert saved == [("Do we already have a contractor for the boiler?", outcome)]


def test_a_clarifying_question_discards_any_cost_estimate_already_saved_this_run():
    llm = llm_replying_with(
        tool_call_reply("save_cost_estimate", {"best": 225, "low": 150, "high": 300}),
        tool_call_reply("save_clarifying_question", {"question": "Which room is affected?"}),
    )
    saved = []

    outcome = agent.run_agent(
        "It's broken", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("It's broken", outcome)]
    assert outcome.status == "needs_info"
    assert outcome.clarifying_question == "Which room is affected?"
    assert outcome.cost_best is None


def test_a_saved_cost_estimate_survives_hitting_the_round_limit_without_a_final_stop():
    # 10 rounds of save_cost_estimate, never followed by a no-tool-call reply — the loop
    # exhausts MAX_ROUNDS without the model ever naturally stopping.
    llm = llm_replying_with(
        *(tool_call_reply("save_cost_estimate", {"best": 225, "low": 150, "high": 300})
          for _ in range(10))
    )
    saved = []

    outcome = agent.run_agent(
        "The kitchen tap is dripping", llm, save=lambda text, o: saved.append((text, o))
    )

    assert outcome.status == "done"
    assert outcome.cost_best == Decimal(225)
    assert saved == [("The kitchen tap is dripping", outcome)]


def test_the_agent_saves_a_clarifying_question_when_the_issue_is_too_vague():
    llm = llm_replying_with(
        tool_call_reply("save_clarifying_question", {"question": "Which room is affected?"})
    )
    saved = []

    outcome = agent.run_agent(
        "Something is broken", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("Something is broken", outcome)]
    assert outcome.status == "needs_info"
    assert outcome.clarifying_question == "Which room is affected?"
    assert outcome.cost_best is None


def test_a_failed_outcome_is_saved_when_the_agent_stops_without_saving_a_result():
    llm = llm_replying_with(text_reply("It's probably a washer."))
    saved = []

    outcome = agent.run_agent(
        "The tap drips", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("The tap drips", outcome)]
    assert outcome.status == "failed"


def test_the_agent_recovers_from_a_single_transient_empty_choices_response():
    llm = llm_replying_with(
        empty_choices_reply(),
        tool_call_reply("save_cost_estimate", {"best": 225, "low": 150, "high": 300}),
        text_reply("Done."),
    )
    saved = []

    outcome = agent.run_agent(
        "The kitchen tap is dripping", llm, save=lambda text, o: saved.append((text, o))
    )

    assert outcome.status == "done"
    assert saved == [("The kitchen tap is dripping", outcome)]


def test_a_failed_outcome_is_saved_when_choices_stay_empty_after_a_retry():
    llm = llm_replying_with(empty_choices_reply(), empty_choices_reply())
    saved = []

    outcome = agent.run_agent(
        "The kitchen tap is dripping", llm, save=lambda text, o: saved.append((text, o))
    )

    assert outcome.status == "failed"
    assert saved == [("The kitchen tap is dripping", outcome)]


def test_a_failed_outcome_is_saved_when_the_model_provider_call_errors():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
    saved = []

    outcome = agent.run_agent(
        "The tap drips", llm, save=lambda text, o: saved.append((text, o))
    )

    assert saved == [("The tap drips", outcome)]
    assert outcome.status == "failed"
