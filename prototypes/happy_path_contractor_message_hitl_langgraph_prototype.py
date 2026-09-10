"""LangGraph port of happy_path_contractor_message_hitl_prototype.py.

Same maintenance issue, same 5 tools, same model (inception/mercury-2.5 via OpenRouter),
same deliberate "request_approval and send_message are separate, nothing enforces the
outcome" design. Every model-facing string is copied verbatim from that script into the
constants below; parity is checked mechanically by _check_prompt_parity.py.

Changed: the agent machinery is an explicit `StateGraph` — a model node, a ToolNode, and
a conditional edge between them — rather than the hand-rolled while-loop OR LangChain's
one-call `create_agent`. This is the low-level view: you wire the loop yourself, but every
edge is visible.

Fully self-contained (no imports from the other prototype variants), matching the project
convention for these files — the tool bodies are duplicated on purpose.

Human-in-the-loop: request_approval() raises `interrupt()`; the graph suspends at the
ToolNode, the driver loop prompts the terminal and resumes with `Command(resume=...)`.
The InMemorySaver checkpointer + thread_id make the pause durable within the process.

Needs OPENROUTER_API_KEY in prototypes/.env
Run:  ./.venv/bin/python happy_path_contractor_message_hitl_langgraph_prototype.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).with_name(".env"))

MODEL = "inception/mercury-2.5"
MAX_ROUNDS = 20
WEB_PLUGIN = [{"id": "web", "max_results": 5}]

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

ISSUE = (
    "The hobs release gas but don't ignite when we turn them on. Also, one of them has "
    "stopped releasing gas completely. This may be because it is blocked with debris."
)
PROPERTY_LOCATION = "Beech Range, Levenshulme, Manchester, United Kingdom"

# ---------------------------------------------------------------------------
# Model-facing strings — copied verbatim from
# happy_path_contractor_message_hitl_prototype.py. Do not edit here without
# editing there; _check_prompt_parity.py asserts these match.
# ---------------------------------------------------------------------------

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

USER_MESSAGE = f"Maintenance issue reported:\n\n{ISSUE}"

RESEARCH_COST_PROMPT = (
    "Research typical UK costs for this maintenance issue. Give concrete "
    "price points (parts, labour, call-out fees), note the region if the "
    "source is region-specific, and list the source URLs you used.\n\n"
    f"Issue: {ISSUE}\n"
    f"Property location: {PROPERTY_LOCATION}"
)
FIND_CONTRACTORS_PROMPT = (
    "Find contractors near this property who could carry out this kind of "
    "repair. For each one give the business name, trade, contact details "
    "(phone/email/website) if available, and the source URL.\n\n"
    f"Issue: {ISSUE}\n"
    f"Property location: {PROPERTY_LOCATION}"
)
DRAFT_MESSAGE_PROMPT = (
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
)

RESEARCH_COST_DESC = (
    "Web-search-backed lookup of repair/replacement costs for the maintenance "
    "issue. Returns raw findings (price points, call-out fees, source URLs), "
    "not a final estimate. Takes no arguments."
)
FIND_CONTRACTORS_DESC = (
    "Web-search-backed lookup of local contractors who could carry out this "
    "kind of repair near the property. Returns raw findings (names, trades, "
    "contact details if available, source URLs), not a vetted shortlist. "
    "Takes no arguments."
)
DRAFT_MESSAGE_DESC = (
    "Drafts a message to send to a contractor requesting a quote for this "
    "maintenance issue. Returns draft text, not the final message you report "
    "back. Takes no arguments."
)
REQUEST_APPROVAL_DESC = (
    "Shows the landlord the exact message text and asks them to approve or "
    "decline sending it to a contractor. Returns the landlord's decision. "
    "Call this before send_message."
)
SEND_MESSAGE_DESC = (
    "Sends a message to a contractor requesting a quote. Only call this with "
    "a message the landlord has approved via request_approval."
)
APPROVAL_MESSAGE_ARG_DESC = "The exact message text to show the landlord."
SEND_MESSAGE_ARG_DESC = "The exact message text to send to the contractor."

APPROVED_RESULT = "Landlord approved this exact message. You may now call send_message."
DECLINED_RESULT = (
    "Landlord declined this message. Do not send it. Either stop, or draft a "
    "materially different message and request approval again."
)
SENT_RESULT = "Message sent to the contractor."

# ---------------------------------------------------------------------------


class ApprovalArgs(BaseModel):
    message: str = Field(description=APPROVAL_MESSAGE_ARG_DESC)


class SendArgs(BaseModel):
    message: str = Field(description=SEND_MESSAGE_ARG_DESC)


def _search_subcall(prompt: str, max_tokens: int) -> str:
    llm = ChatOpenAI(
        model=MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        max_tokens=max_tokens,
        extra_body={"plugins": WEB_PLUGIN},
    )
    return (llm.invoke(prompt).content or "").strip()


@tool(description=RESEARCH_COST_DESC)
def research_cost() -> str:
    out = _search_subcall(RESEARCH_COST_PROMPT, max_tokens=6000)
    return out or "(research_cost sub-call returned no text findings)"


@tool(description=FIND_CONTRACTORS_DESC)
def find_contractors() -> str:
    out = _search_subcall(FIND_CONTRACTORS_PROMPT, max_tokens=6000)
    return out or "(find_contractors sub-call returned no text findings)"


@tool(description=DRAFT_MESSAGE_DESC)
def draft_message() -> str:
    llm = ChatOpenAI(
        model=MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        max_tokens=4000,
    )
    draft = (llm.invoke(DRAFT_MESSAGE_PROMPT).content or "").strip()
    return draft or "(draft_message sub-call returned no text)"


@tool(description=REQUEST_APPROVAL_DESC, args_schema=ApprovalArgs)
def request_approval(message: str) -> str:
    """Blocks (via interrupt) on a landlord approval decision. No side effect."""
    approval = str(interrupt({"kind": "landlord_approval", "message": message})).strip().lower()
    if approval in ("y", "yes"):
        return APPROVED_RESULT
    return DECLINED_RESULT


@tool(description=SEND_MESSAGE_DESC, args_schema=SendArgs)
def send_message(message: str) -> str:
    """Mock send: just prints. No approval check here by design (see module docstring)."""
    print(f"\n{'=' * 70}\n[SENT]\n{'=' * 70}")
    print(message)
    return SENT_RESULT


TOOLS = [research_cost, find_contractors, draft_message, request_approval, send_message]


def build_graph():
    model = ChatOpenAI(
        model=MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        max_tokens=4000,
    ).bind_tools(TOOLS)
    system_message = SystemMessage(SYSTEM_PROMPT_TEMPLATE.format(PROPERTY_LOCATION=PROPERTY_LOCATION))

    def call_model(state: MessagesState) -> dict:
        return {"messages": [model.invoke([system_message, *state["messages"]])]}

    def route(state: MessagesState) -> str:
        return "tools" if state["messages"][-1].tool_calls else END

    g = StateGraph(MessagesState)
    g.add_node("call_model", call_model)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_edge(START, "call_model")
    g.add_conditional_edges("call_model", route, {"tools": "tools", END: END})
    g.add_edge("tools", "call_model")
    return g.compile(checkpointer=InMemorySaver())


def _print_step(chunk: dict) -> None:
    for node, update in chunk.items():
        for msg in update.get("messages", []) if isinstance(update, dict) else []:
            role = getattr(msg, "type", "?")
            text = (getattr(msg, "content", "") or "").strip()
            for c in getattr(msg, "tool_calls", None) or []:
                print(f"\n[{node}: tool call] {c['name']}({c.get('args', {})})")
            if text:
                label = "tool result" if role == "tool" else role
                print(f"\n[{node}: {label}]\n{text[:1500]}")


def run() -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": "hitl-1"}, "recursion_limit": 2 * MAX_ROUNDS + 1}
    payload = {"messages": [{"role": "user", "content": USER_MESSAGE}]}

    while True:
        for chunk in graph.stream(payload, config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                data = chunk["__interrupt__"][0].value
                print(f"\n{'=' * 70}\nLANDLORD APPROVAL REQUESTED\n{'=' * 70}")
                print("The agent wants to send the following message to a contractor:\n")
                print(data["message"])
                ans = input("\nApprove sending this message? [y/n]: ").strip().lower()
                print("\n[APPROVED]" if ans in ("y", "yes") else "\n[DECLINED]")
                payload = Command(resume=ans)
                break
            _print_step(chunk)
        else:
            break

    final = graph.get_state(config).values["messages"][-1]
    print(f"\n{'=' * 70}\nFINAL\n{'=' * 70}\n{(final.content or '').strip()}")


if __name__ == "__main__":
    if not OPENROUTER_API_KEY:
        raise SystemExit("Set OPENROUTER_API_KEY in prototypes/.env first.")
    run()
