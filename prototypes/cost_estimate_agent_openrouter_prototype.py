"""Slice 1 (OpenRouter variant) — an exact replica of the simple search loop in
cost_estimate_agent_search_prototype.py, but routed through OpenRouter's
OpenAI-compatible API so cheaper non-Anthropic models can be swapped in and priced.

Swap models by changing MODEL to any OpenRouter slug, e.g.:
  openai/gpt-5.6-luna       (verify the exact slug on openrouter.ai)
  inception/mercury-2.5
  z-ai/glm-5.3-flash

Web search: Anthropic's server-side web_search tool has no equivalent here, so
research_cost uses OpenRouter's model-agnostic `web` plugin (Exa-backed) instead.
Note: that plugin bills separately, ~$0.004 per result returned.

Cost instrumentation: every model call records tokens + cost. We ask OpenRouter for
inline usage (`usage.include`) and also fetch the per-generation record
(GET /api/v1/generation), which itemises normalised vs native tokens, reasoning
tokens, search results, and total cost (inference + plugin). A per-run table prints
at the end so the same run can be compared across models.

Needs OPENROUTER_API_KEY in prototypes/.env
Run:  ./.venv/bin/python cost_estimate_agent_openrouter_prototype.py
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load prototypes/.env explicitly, not relative to the current working directory.
load_dotenv(Path(__file__).with_name(".env"))

MODEL = "openai/gpt-5.6-luna"     # <- swap to any OpenRouter slug inception/mercury-2.5
# MODEL = "inception/mercury-2.5" 
# MODEL = "z-ai/glm-5.3-flash" 

MAX_ROUNDS = 10
WEB_PLUGIN = [{"id": "web", "max_results": 5}]     # OpenRouter web search plugin

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Ask OpenRouter to include cost/usage in every response body.
USAGE_EXTRA = {"usage": {"include": True}}

# One entry per model call, filled by record_usage().
USAGE_LOG: list[dict] = []


def _fetch_generation(gen_id: str) -> dict | None:
    """OpenRouter's per-generation record — definitive cost breakdown. Lags ~1-4s."""
    url = "https://openrouter.ai/api/v1/generation?" + urllib.parse.urlencode({"id": gen_id})
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"})
    for _ in range(6):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200:
                    return json.loads(r.read()).get("data")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(1.5)
    return None


def record_usage(label: str, response) -> None:
    """Log tokens + cost for one model call and print a one-line summary."""
    data = response.model_dump()
    usage = data.get("usage") or {}
    prompt = usage.get("prompt_tokens", 0) or 0
    completion = usage.get("completion_tokens", 0) or 0
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0
    cost = usage.get("cost")  # present because of USAGE_EXTRA

    gen = _fetch_generation(data.get("id")) if data.get("id") else None
    web_results = 0
    if gen:
        prompt = gen.get("tokens_prompt", prompt) or prompt
        completion = gen.get("tokens_completion", completion) or completion
        reasoning = gen.get("native_tokens_reasoning", reasoning) or reasoning
        web_results = gen.get("num_search_results", 0) or 0
        cost = gen.get("total_cost", cost)

    entry = {
        "label": label,
        "prompt": prompt,
        "completion": completion,
        "reasoning": reasoning,
        "web_results": web_results,
        "cost": cost or 0.0,
    }
    USAGE_LOG.append(entry)
    print(
        f"\n[usage: {label}] prompt={prompt:,} completion={completion:,} "
        f"reasoning={reasoning:,} web_results={web_results} cost=${entry['cost']:.5f}"
    )


def print_totals() -> None:
    if not USAGE_LOG:
        return
    tp = sum(e["prompt"] for e in USAGE_LOG)
    tc = sum(e["completion"] for e in USAGE_LOG)
    tr = sum(e["reasoning"] for e in USAGE_LOG)
    tw = sum(e["web_results"] for e in USAGE_LOG)
    tcost = sum(e["cost"] for e in USAGE_LOG)
    print(f"\n{'=' * 78}")
    print(f"RUN TOTAL  model={MODEL}  calls={len(USAGE_LOG)}")
    for e in USAGE_LOG:
        print(
            f"  {e['label']:<16} prompt={e['prompt']:>8,} completion={e['completion']:>7,} "
            f"reasoning={e['reasoning']:>7,} web={e['web_results']:>2} ${e['cost']:.5f}"
        )
    print(f"  {'-' * 66}")
    print(
        f"  {'TOTAL':<16} prompt={tp:>8,} completion={tc:>7,} "
        f"reasoning={tr:>7,} web={tw:>2} ${tcost:.5f}"
    )
    print(f"{'=' * 78}")

ISSUE = (
    "The hobs release gas but don't ignite when we turn them on. Also, one of them has "
    "stopped releasing gas completely. This may be because it is blocked with debris."
)
PROPERTY_LOCATION = "Beech Range, Levenshulme, Manchester, United Kingdom"

SYSTEM_PROMPT_TEMPLATE = """\
You are a lettings maintenance assistant. Given a maintenance issue reported at a rental
property, your job is to produce a rough cost estimate (a low–high range in GBP,
plus an explanation) for getting the issue fixed.

Property location: {PROPERTY_LOCATION}
(Use UK pricing; reflect that property's local labour rates.)

You have one tool:
  research_cost() — runs a web-search-backed lookup and returns raw findings
  (price points, call-out fees, sources). It is NOT the committed estimate; you decide the
  final range from what it returns.

When you have enough to ground a range, STOP calling tools and reply with:
  - Cost estimate: £<low>–£<high>
  - Basis: <explanation of what the range covers and any key assumptions>
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "research_cost",
            "description": (
                "Web-search-backed lookup of repair/replacement costs for the maintenance "
                "issue. Returns raw findings (price points, call-out fees, source URLs), "
                "not a final estimate. Takes no arguments."
            )
        },
    }
]


def research_cost(ISSUE: str, PROPERTY_LOCATION: str) -> str:
    """Own web-search-backed sub-call (OpenRouter `web` plugin). Returns text findings."""
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=2000,
        extra_body={"plugins": WEB_PLUGIN, **USAGE_EXTRA},
        messages=[
            {
                "role": "user",
                "content": (
                    "Research typical UK costs for this maintenance issue. Give concrete "
                    "price points (parts, labour, call-out fees), note the region if the "
                    "source is region-specific, and list the source URLs you used.\n\n"
                    f"Issue: {ISSUE}\n"
                    f"Property location: {PROPERTY_LOCATION}"
                ),
            }
        ],
    )
    record_usage("research_cost", resp)
    findings = (resp.choices[0].message.content or "").strip()
    return findings or "(research_cost sub-call returned no text findings)"


def run(SYSTEM_PROMPT_TEMPLATE: str, ISSUE: str, PROPERTY_LOCATION: str) -> None:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(PROPERTY_LOCATION=PROPERTY_LOCATION)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Maintenance issue reported:\n\n{ISSUE}"},
    ]

    try:
        for round_no in range(1, MAX_ROUNDS + 1):
            print(f"\n{'=' * 70}\nROUND {round_no}\n{'=' * 70}")
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=4000,
                tools=TOOLS,
                messages=messages,
                extra_body=USAGE_EXTRA,
            )
            record_usage(f"loop r{round_no}", response)
            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if message.content:
                print(f"\n[model text]\n{message.content}")
            for tc in message.tool_calls or []:
                print(f"\n[tool call] {tc.function.name}({tc.function.arguments})")

            if not message.tool_calls:           # model stopped asking for tools -> done
                print(f"\n[finish_reason: {finish_reason}] DONE")
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ],
                }
            )
            for tc in message.tool_calls:
                result = research_cost(ISSUE, PROPERTY_LOCATION)
                print(f"\n[tool result] {tc.function.name}\n{result[:1500]}")
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )

        print(f"\nHIT MAX_ROUNDS ({MAX_ROUNDS}) — forced stop.")
    finally:
        print_totals()


if __name__ == "__main__":
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("Set OPENROUTER_API_KEY in prototypes/.env first.")
    run(SYSTEM_PROMPT_TEMPLATE, ISSUE, PROPERTY_LOCATION)
