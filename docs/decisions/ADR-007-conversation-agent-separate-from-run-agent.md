# ADR-007: A separate conversation agent, not an extension of run_agent

## Status
Accepted

## Date
2026-10-07

## Context
The multi-turn conversation slice (`docs/specs/multi-turn-conversation-brief-spec-061026.md`)
needs a loop that takes a follow-up message, replays a conversation's prior turns, calls
tools (starting with `lookup_issue`, later `research_cost`/`find_contractors`), and persists
the result — structurally the same ReAct shape `run_agent()`/`_run_loop()` already runs in
`services/agent.py`.

The obvious question at co-pilot was whether to extend `run_agent()`/`_run_loop()` to also
handle conversation turns, rather than add a second module. `run_agent()` carries a
deterministic invariant the conversation task cannot share:

- Every run must end with exactly one `save_*` tool call (`save_cost_estimate`,
  `save_contractors`, or the all-or-nothing `save_clarifying_question`). The system prompt
  states this explicitly ("never just reply with plain text and no tool call, even to decline
  a request"), and `_finalize_outcome` guarantees a fallback `needs_info` outcome even if the
  model goes quiet. This is what makes "write exactly one `issues` row per submission" a
  guarantee rather than a hope — see ADR-005.
- A conversational follow-up is the opposite shape on purpose: replying in plain text with no
  tool call is the *normal*, expected way a turn ends — the model answered the question. There
  is no outcome object to finalize, no DB row the turn must end by writing. The conversation's
  own stopping point is "the model stopped calling tools," full stop, and the only hard
  constraint is the 10-user-turn cap, enforced at persistence (`issues_db.append_turn`'s
  `ConversationCapReached`), not at the model-loop level.

Reconciling these inside one function means branching, per call, on: which tool list applies,
what the termination condition is (stop-on-`save_*`, discarding on `save_clarifying_question`,
vs. stop-on-no-tool-call), and which system prompt applies — three axes of conditional
behavior layered into what is otherwise the same `while`-loop-over-tool-calls shape used
elsewhere (and in the standard ReAct pattern generally: one tool set, one termination rule, one
prompt, for the lifetime of the loop).

## Decision
Keep `run_agent()`/`_run_loop()` untouched, and add `services/conversation_agent.py` with its
own entry point (`run_conversation_turn`), its own system prompt, and its own tool list. The
two loops share only what is genuinely common and carries no task-specific invariant with it:
the model constant (`MODEL`), the traced OpenRouter client builder (`build_client`), and the
retry-on-empty-choices behavior. Tool *implementations* that exist in both loops (the
`research_cost`/`find_contractors` web-search sub-calls) are reused directly from `agent.py`,
not reimplemented in `conversation_agent.py` — the loop/orchestration layer is kept separate
from the tool-implementation layer, so the same capability isn't duplicated just because two
different loops call it.

`conversation_agent.py`'s loop ends the moment the model stops calling tools (standard ReAct
termination), with no forced "must end via a specific tool" rule — because unlike the triage
flow, there is no single outcome object this loop is contractually obligated to produce.

## Alternatives Considered

### Extend `run_agent()`/`_run_loop()` with a conversation mode flag
- Pros: one less file; the sub-call tool reuse is trivially in-scope already.
- Cons: forces a choice between weakening `run_agent`'s "always ends in exactly one `save_*`
  call" guarantee (so conversational plain-text replies are allowed), or forcing conversational
  replies through an artificial save-like call they don't need — and either way, the tool list,
  termination condition, and system prompt all become mode-conditional inside one function.
- Rejected because: the branching this introduces is strictly worse than two small functions
  sharing the few things that are actually common (model constant, client builder, sub-call
  tool implementations).

### A single generic "agent loop" function parameterized by tools/prompt/termination rule
- Pros: removes the shape duplication between the two loops entirely.
- Cons: at two call sites with genuinely different termination semantics (one needs the
  `save_clarifying_question` all-or-nothing discard behavior; the other needs none of that),
  the generic version would need to expose that difference as a parameter anyway — which is
  the same branching, just relocated one level up and more abstract for a reader to follow.
- Rejected because: premature generalization for two call sites; revisit if a third
  structurally-different loop shape appears.

## Consequences
- The ReAct loop *shape* (call model, check `tool_calls`, dispatch by name, append results,
  repeat until stop) is duplicated between `agent.py` and `conversation_agent.py`. This is
  accepted duplication, not oversight — see "Common Rationalizations" in
  `documentation-and-adrs`: the alternative (one function serving two incompatible contracts)
  is worse than a few lines of shared shape.
- Tool *implementations* (the web-search sub-calls) are shared via direct import from `agent.py`
  into `conversation_agent.py`; only the orchestration loop and system prompt are duplicated,
  not the underlying capability — see ARCHITECTURE.md's conversation agent section for the
  current tool-reuse map as it's built out across build steps 4-5.

### This is a trade-off we will hit again, by design, not a one-off call
This decision only holds because there are exactly two workflow shapes right now. **Each time
agent functionality grows a workflow shape that doesn't fit either existing invariant — a
different termination rule, a different "what must be true when the run ends" contract — this
same friction resurfaces**, and the honest fix each time is another small, separate loop, not
bending `run_agent()` or `conversation_agent()` to also cover it. That is sustainable for a
little while and then stops being sustainable: at some number of shapes (three is a reasonable
guess, not a hard rule), the cost of N near-identical duplicated loop skeletons overtakes the
cost of a shared loop runner parameterized by tool list + termination predicate (the second
alternative above, deliberately rejected here as premature). This ADR is the marker for that
future moment — when a third structurally-different shape shows up, that is the point to
revisit the rejected generic-runner alternative, not a sign this decision was wrong. The
likely trigger is a wider agent refactor once the number of distinct run-termination contracts
stops being "two, cleanly separable."

## Industry context
This two-loops-not-one shape, and the layering it depends on (orchestration/control-flow kept
separate from reusable tool implementations), matches how the major agent frameworks already
draw this line, rather than being a one-off choice for this codebase:

- **Thread/Run separation.** OpenAI's Assistants API (and its Responses/Conversations API
  successor) models a conversation as a persistent Thread plus discrete Runs executed against
  it — creating a thread and executing one run are already two different operations in that
  API, the same split this ADR draws between `create_conversation` and
  `run_conversation_turn`. ([Jacar.es: OpenAI Assistants API — stateful agents without your own
  infrastructure](https://jacar.es/en/openai-assistants-api-stateful-agents-without-your-own-infrastructure/))
- **Tools as a layer separate from the orchestrator.** LangChain explicitly separates tools
  (standalone, reusable callables) from the Agent Executor (the loop runtime that calls the
  model, dispatches tool calls, and feeds observations back) specifically so the same tools can
  be shared across different agents and different orchestration loops — the same reasoning
  behind reusing `agent.py`'s `research_cost`/`find_contractors` sub-calls from
  `conversation_agent.py` rather than reimplementing them.
  ([growwstacks.com: LangChain production guide — AI agents, ReAct, tools](https://growwstacks.com/blog/langchain-production-guide-ai-agents-react-tools))
- **Cognition/control kept separate from tool execution, and why conflating them is flagged as
  a real risk, not a style preference.** Broader agentic-architecture writing frames this as a
  control layer (planner/policy logic, state machines, termination rules) versus a tool layer
  (fetching data, executing actions) — and warns that a system needs these kept as genuinely
  separate layers because conflating them "collapses the audit trail that makes the agentic
  engine verifiable." That is the same failure mode this ADR avoids: a single function carrying
  two different termination contracts is harder to reason about and verify than two small ones.
  ([blog.vectorize.io: Designing Agentic AI Systems, Part 1 — Agent Architectures](https://blog.vectorize.io/designing-agentic-ai-systems-part-1-agent-architectures))
- **Shared tool libraries as the fix for duplicated capabilities across agents.** Where
  platforms built on top of OpenAI's function-calling primitive hit this exact N-agents/one-tool
  problem, the documented fix is a shared tools library ("define a tool once and reuse it
  across all your assistants") rather than each assistant re-implementing the same capability —
  reinforcing that tool reuse across loops, not loop reuse across tools, is the conventional
  direction to resolve this friction.
  ([developers.telnyx.com: Tools Library](https://developers.telnyx.com/docs/inference/ai-assistants/tools-library))
