import os

import google.auth
from google.cloud import secretmanager
from langfuse import get_client
from openai import OpenAI

MODEL = "inception/mercury-2.5"
SECRET_ID = "openrouter-api-key"

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
