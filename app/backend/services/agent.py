import json
import os
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import google.auth
from google.cloud import secretmanager
from langfuse import get_client
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageParam,
)

from models.agent_outcome import AgentOutcome

MODEL = "inception/mercury-2.5"
SECRET_ID = "OPENROUTER_API_KEY"
MAX_ROUNDS = 10

# Persists an outcome for an issue. Injected so the agent never imports the DB:
# production passes issues_db.save, evals pass a capturing function.
Save = Callable[[str, AgentOutcome], Any]

SAVE_COST_ESTIMATE_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "save_cost_estimate",
        "description": (
            "Write your final cost estimate for this issue, in GBP, to the issues "
            "database: your single best estimate plus the plausible low-high range around "
            "it. This is the only way your result is recorded, and it ends the task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "best": {"type": "number"},
                "low": {"type": "number"},
                "high": {"type": "number"},
            },
            "required": ["best", "low", "high"],
        },
    },
}
TOOLS = [SAVE_COST_ESTIMATE_TOOL]

SYSTEM_PROMPT = (
    "You are a helpful rental property maintenance agent. A landlord will describe "
    "an issue reported at one of their properties. Help them think through it."
)


def build_client() -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=resolve_api_key(),
    )


def resolve_api_key() -> str | None:
    """Picks the key source by environment: Secret Manager when deployed on
    Cloud Run (K_SERVICE is set automatically there, never locally), the
    local OPENROUTER_API_KEY env var (.env) otherwise."""
    if os.environ.get("K_SERVICE"):
        return _fetch_api_key_from_secret_manager()
    return os.environ.get("OPENROUTER_API_KEY")


def _fetch_api_key_from_secret_manager() -> str:
    _, project_id = google.auth.default()
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{SECRET_ID}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def respond_to_issue(issue_text: str, client: OpenAI) -> str:
    langfuse = get_client()
    with langfuse.start_as_current_observation(
        as_type="generation", name="respond_to_issue", model=MODEL, input=issue_text
    ) as generation:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": issue_text},
            ],
        )
        reply = completion.choices[0].message.content or ""
        generation.update(output=reply)
    return reply


def run_agent(issue_text: str, client: OpenAI, save: Save) -> AgentOutcome:
    """Runs the agent until it writes its result by calling a save_* tool. If it
    never does, the runtime saves a `failed` outcome instead, so every run results
    in exactly one saved row."""
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": issue_text},
    ]
    for _ in range(MAX_ROUNDS):
        response = client.chat.completions.create(model=MODEL, tools=TOOLS, messages=messages)
        for call in response.choices[0].message.tool_calls or []:
            if call.type != "function":
                continue
            if call.function.name == "save_cost_estimate":
                args = json.loads(call.function.arguments)
                outcome = AgentOutcome(
                    status="done",
                    cost_best=Decimal(str(args["best"])),
                    cost_low=Decimal(str(args["low"])),
                    cost_high=Decimal(str(args["high"])),
                )
                save(issue_text, outcome)
                return outcome
    outcome = AgentOutcome(status="failed")
    save(issue_text, outcome)
    return outcome
