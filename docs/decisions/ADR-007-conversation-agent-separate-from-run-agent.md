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
- **This will recur.** Any future feature that adds a third fundamentally different workflow
  shape to the agent (a different termination rule, a different "what must be true when the
  run ends" invariant) raises the same question again, and at three shapes the "duplicated
  loop skeleton across N files" cost starts to outweigh the "no cross-contaminated invariants"
  benefit. At that point, extracting a shared loop runner parameterized by tool list +
  termination predicate (the second alternative above, rejected for now) should be
  reconsidered — not as a correction of this decision, but as the point where the trade-off
  tips the other way. Flag this ADR when that happens rather than re-deriving the reasoning
  from scratch.
- Tool *implementations* (the web-search sub-calls) are shared via direct import from `agent.py`
  into `conversation_agent.py`; only the orchestration loop and system prompt are duplicated,
  not the underlying capability — see ARCHITECTURE.md's conversation agent section for the
  current tool-reuse map as it's built out across build steps 4-5.
