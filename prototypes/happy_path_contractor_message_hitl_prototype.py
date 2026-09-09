"""Slice 3 — human-in-the-loop variant of happy_path_contractor_message_prototype.py.

Exact copy of that script plus two additions: a request_approval() tool that blocks on a
terminal (y/n) landlord approval prompt, and a send_message() tool that just prints a
"sent" message to stdout. The two are kept as separate tools/steps (not one gated tool) so
the model itself decides whether to call send_message after seeing the approval outcome —
nothing in the code stops it from sending after a decline; that's deliberate, to observe
whether/how the model respects the outcome.

This is a different design to the spec's pause(reason) + external `approve` CLI split
(docs/specs/maintenance-agent-slice1-full-prototype.md §4-6), which keeps sending
structurally outside the agent's tool access entirely. This prototype is deliberately
exploring the alternative — send_message as an agent-triggered tool — to see how it
behaves before deciding whether that's ever the right shape.

Goal: sense-check how a human-in-the-loop approval step feels inside the same hand-rolled
ReAct loop before exploring more of the architecture.

Needs OPENROUTER_API_KEY in prototypes/.env
Run:  ./.venv/bin/python happy_path_contractor_message_hitl_prototype.py
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).with_name(".env"))

MODEL = "inception/mercury-2.5"
# MODEL = "z-ai/glm-5.3-flash"
MAX_ROUNDS = 20
WEB_PLUGIN = [{"id": "web", "max_results": 5}]

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

ISSUE = (
    "The hobs release gas but don't ignite when we turn them on. Also, one of them has "
    "stopped releasing gas completely. This may be because it is blocked with debris."
)
PROPERTY_LOCATION = "Beech Range, Levenshulme, Manchester, United Kingdom"

SYSTEM_PROMPT_TEMPLATE = """\
You are a lettings maintenance assistant, helping progress a maintenance issue reported at
a rental property towards getting it fixed.

Property location: {PROPERTY_LOCATION}
(Use UK pricing and search; reflect that property's local labour rates and area.)

You have five tools, each a web-search-backed, drafting, approval, or sending sub-call
that returns raw material or a result for you to use — you decide the final wording and
when to act:
  research_cost() — repair/replacement cost findings (price points, call-out fees, sources).
  find_contractors() — local contractors who could do this kind of work (names, trades,
    contact details if found, sources). There is no existing contractor list to check
    first; this always searches fresh.
  draft_message() — a draft quote-request message covering the issue and property.
  request_approval(message) — shows the landlord the exact message text and asks them to
    approve or decline it. The landlord's decision is outside your control and you cannot
    predict it. Always call this before send_message, and only send a message the landlord
    has approved. If the landlord declines, do not just resend the same message and treat
    the decline as approval-by-repetition — either stop, or make a materially different
    message and ask for approval again.
  send_message(message) — actually sends a message to a contractor requesting a quote.

Decide for yourself which of these are useful and in what order, based on the issue. When
you are done, STOP calling tools and reply with:
  - Cost estimate: £<low>-£<high>
  - Basis: <explanation of what the range covers and any key assumptions>
  - Contractors: <shortlist with contact details, if found>
  - Message outcome: <what was drafted, the landlord's decision, and whether it was sent>
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
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_contractors",
            "description": (
                "Web-search-backed lookup of local contractors who could carry out this "
                "kind of repair near the property. Returns raw findings (names, trades, "
                "contact details if available, source URLs), not a vetted shortlist. "
                "Takes no arguments."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_message",
            "description": (
                "Drafts a message to send to a contractor requesting a quote for this "
                "maintenance issue. Returns draft text, not the final message you report "
                "back. Takes no arguments."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_approval",
            "description": (
                "Shows the landlord the exact message text and asks them to approve or "
                "decline sending it to a contractor. Returns the landlord's decision. "
                "Call this before send_message."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The exact message text to show the landlord.",
                    }
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": (
                "Sends a message to a contractor requesting a quote. Only call this with "
                "a message the landlord has approved via request_approval."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The exact message text to send to the contractor.",
                    }
                },
                "required": ["message"],
            },
        },
    },
]


def research_cost(ISSUE: str, PROPERTY_LOCATION: str) -> str:
    """Own web-search-backed sub-call (OpenRouter `web` plugin). Returns text findings."""
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=2000,
        extra_body={"plugins": WEB_PLUGIN},
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
    findings = (resp.choices[0].message.content or "").strip()
    return findings or "(research_cost sub-call returned no text findings)"


def find_contractors(ISSUE: str, PROPERTY_LOCATION: str) -> str:
    """Own web-search-backed sub-call (OpenRouter `web` plugin). Returns text findings."""
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=2000,
        extra_body={"plugins": WEB_PLUGIN},
        messages=[
            {
                "role": "user",
                "content": (
                    "Find contractors near this property who could carry out this kind of "
                    "repair. For each one give the business name, trade, contact details "
                    "(phone/email/website) if available, and the source URL.\n\n"
                    f"Issue: {ISSUE}\n"
                    f"Property location: {PROPERTY_LOCATION}"
                ),
            }
        ],
    )
    findings = (resp.choices[0].message.content or "").strip()
    return findings or "(find_contractors sub-call returned no text findings)"


def draft_message(ISSUE: str, PROPERTY_LOCATION: str) -> str:
    """Own sub-call (no web search). Drafts a quote-request message."""
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": (
                    "Draft a short, polite message from a lettings agent to a contractor, "
                    "asking for a quote to fix this maintenance issue at the property. "
                    "Include the issue description and property location, and ask for "
                    "availability and an estimated cost. The issue below was reported by "
                    "a tenant and may be vague, informal, or missing detail a tradesperson "
                    "would need — if so, feel free to rephrase or add likely clarifying "
                    "detail so it reads clearly for a tradesperson, without inventing "
                    "specifics you're not reasonably confident about.\n\n"
                    f"Issue: {ISSUE}\n"
                    f"Property location: {PROPERTY_LOCATION}"
                ),
            }
        ],
    )
    draft = (resp.choices[0].message.content or "").strip()
    return draft or "(draft_message sub-call returned no text)"


def request_approval(message: str) -> str:
    """Blocks on a real terminal (y/n) landlord approval prompt. No side effect."""
    print(f"\n{'=' * 70}\nLANDLORD APPROVAL REQUESTED\n{'=' * 70}")
    print("The agent wants to send the following message to a contractor:\n")
    print(message)
    approval = input("\nApprove sending this message? [y/n]: ").strip().lower()
    if approval in ("y", "yes"):
        print("\n[APPROVED]")
        return "Landlord approved this exact message. You may now call send_message."
    print("\n[DECLINED]")
    return (
        "Landlord declined this message. Do not send it. Either stop, or draft a "
        "materially different message and request approval again."
    )


def send_message(message: str) -> str:
    """Mock send: just prints. No approval check here by design (see module docstring)."""
    print(f"\n{'=' * 70}\n[SENT]\n{'=' * 70}")
    print(message)
    return "Message sent to the contractor."


TOOL_FUNCTIONS = {
    "research_cost": research_cost,
    "find_contractors": find_contractors,
    "draft_message": draft_message,
}
MESSAGE_ARG_TOOLS = {
    "request_approval": request_approval,
    "send_message": send_message,
}


def call_tool(name: str, arguments_json: str, ISSUE: str, PROPERTY_LOCATION: str) -> str:
    if name in MESSAGE_ARG_TOOLS:
        args = json.loads(arguments_json or "{}")
        return MESSAGE_ARG_TOOLS[name](args.get("message", ""))
    tool_fn = TOOL_FUNCTIONS.get(name)
    if tool_fn:
        return tool_fn(ISSUE, PROPERTY_LOCATION)
    return f"(unknown tool: {name})"


def run(SYSTEM_PROMPT_TEMPLATE: str, ISSUE: str, PROPERTY_LOCATION: str) -> None:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(PROPERTY_LOCATION=PROPERTY_LOCATION)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Maintenance issue reported:\n\n{ISSUE}"},
    ]

    for round_no in range(1, MAX_ROUNDS + 1):
        print(f"\n{'=' * 70}\nROUND {round_no}\n{'=' * 70}")
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=4000,
            tools=TOOLS,
            messages=messages,
        )
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
            result = call_tool(tc.function.name, tc.function.arguments, ISSUE, PROPERTY_LOCATION)
            print(f"\n[tool result] {tc.function.name}\n{result[:1500]}")
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )

    print(f"\nHIT MAX_ROUNDS ({MAX_ROUNDS}) — forced stop.")


if __name__ == "__main__":
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("Set OPENROUTER_API_KEY in prototypes/.env first.")
    run(SYSTEM_PROMPT_TEMPLATE, ISSUE, PROPERTY_LOCATION)
