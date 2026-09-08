"""Slice 1 — simplest possible hand-rolled ReAct loop for a maintenance cost estimate.

Deliberately minimal (see docs/specs/maintenance-agent-slice1-full-prototype.md):

  * framework-free — raw Anthropic SDK, native tool calling, a plain while-loop we own
  * ONE read tool: research_cost (makes its own web-search-backed sub-call)
  * NO pause tool yet — the loop ends when the model returns no tool_use block. The
    spec's forced pause(reason) termination model is a later step; here we just want to
    see whether a hand-rolled loop can get a grounded estimate out.
  * NO persistence — issue/property are constants, every step is printed to stdout.

Backstop: MAX_ROUNDS cap so a misbehaving loop can't run forever.

Run:  ./.venv/bin/python cost_estimate_agent_search_prototype.py
"""

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"          
MAX_ROUNDS = 10                   
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}

# ISSUE = (
#     "The hobs release gas but don't ignite when we turn them on. Also, one of them has "
#     "stopped releasing gas completely. This may be because it is blocked with debris."
# )


# ISSUE = (
#     "Something smells off"
# )

ISSUE = (
    "The hot water tap is leaking. Sometimes there is a small but steady stream of water coming out of it, other times it is just dripping. It's turned as far as it will go but it's still coming out."
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
        "name": "research_cost",
        "description": (
            "Web-search-backed lookup of repair/replacement costs for the maintenance "
            "issue. Returns raw findings (price points, call-out fees, source URLs), not a "
            "final estimate. Takes no arguments."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    }
]


def research_cost(client: anthropic.Anthropic, ISSUE: str, PROPERTY_LOCATION: str) -> str:
    """Own web-search-backed sub-call. Returns the sub-agent's text findings."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        tools=[WEB_SEARCH_TOOL],
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
    parts = [b.text for b in resp.content if b.type == "text" and b.text.strip()]
    findings = "\n\n".join(parts).strip()
    return findings or "(research_cost sub-call returned no text findings)"


def run(SYSTEM_PROMPT_TEMPLATE: str, ISSUE: str, PROPERTY_LOCATION: str) -> None:
    client = anthropic.Anthropic()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(PROPERTY_LOCATION=PROPERTY_LOCATION)
    messages = [{"role": "user", "content": f"Maintenance issue reported:\n\n{ISSUE}"}]

    for round_no in range(1, MAX_ROUNDS + 1):
        print(f"\n{'=' * 70}\nROUND {round_no}\n{'=' * 70}")
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )
        for block in response.content:
            if block.type == "text":
                print(f"\n[model text]\n{block.text}")
            elif block.type == "tool_use":
                print(f"\n[tool call] {block.name}({block.input})")

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:                       
            print(f"\n[stop_reason: {response.stop_reason}] DONE")
            return

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tu in tool_uses:
            result = research_cost(client, ISSUE, PROPERTY_LOCATION)
            print(f"\n[tool result] {tu.name}\n{result[:1500]}")
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.id, "content": result}
            )
        messages.append({"role": "user", "content": tool_results})

    print(f"\nHIT MAX_ROUNDS ({MAX_ROUNDS}) — forced stop.")


if __name__ == "__main__":
    run(SYSTEM_PROMPT_TEMPLATE, ISSUE, PROPERTY_LOCATION)
