# Work Summary — 07 October 2026

## What was built

Built out `docs/specs/multi-turn-conversation-brief-spec-061026.md` end to end (steps 1–9),
plus live UI testing and a documentation pass.

- **Schema** (`app/backend/services/issues_db.py`): `conversations` and `conversation_steps`
  tables. Mid-build, renamed `conversation_turns` → `conversation_steps` and added a computed
  `turn_number` column, to distinguish a *turn* (one user message plus everything the agent
  does in response) from a *step* (one row). `append_step()` derives `turn_number` itself
  (count of prior user steps); the 10-user-turn cap (`ConversationCapReached`) reads the same
  count. `get_conversation()`, `get_conversation_steps()`, `list_conversations_for_issue()`,
  `lookup_issue()` (composes issue + contractors + conversations), and
  `add_contractors_to_issue()` (extracted from `save()`'s contractor-linking logic, reused by
  both — additive, never touches the `issues` row).
- **`POST /api/issue`** (`routers/issue.py`) now also creates a conversation on submit and
  returns `conversation_id` in the response (`IssueResponse(AgentOutcome)`).
- **`app/backend/services/conversation_agent.py`** (new) — `run_conversation_turn()`: a
  second ReAct loop, deliberately separate from `agent.py`'s `run_agent()` (see ADR-007).
  Four tools: `lookup_issue` (new), `research_cost`, `find_contractors`, `save_contractors`
  (the last three reused verbatim from `agent.py`'s existing tool contracts/implementations,
  per ADR-007 — only `save_contractors`'s commit handler differs, binding to
  `add_contractors_to_issue()`). Traced as one Langfuse span per turn
  (`run_conversation_turn`), tagged `conversation_id`/`turn_number`;
  `session_id=conversation_id` chains a conversation's turns together in Langfuse's session
  view.
- **`routers/conversations.py`** (new) — `GET /api/issues/{issue_id}/conversations`,
  `GET /api/conversations/{conversation_id}`, `POST /api/conversations/{conversation_id}/messages`
  (rate-limited 10/min like `POST /api/issue`; `ConversationCapReached` → 409). `issue_id` is
  always derived from the conversation's own DB row, never accepted from the client.
- **Frontend**: `app/frontend/src/ConversationPanel.tsx` (new) — issue dropdown, thread view
  grouped by `turn_number` (only the user step and final assistant reply render as bubbles;
  tool-call/tool-result steps never do), message input with a live X/10 counter, a
  "Thinking…" status, a closed state at the cap (client-side and from a 409). `App.tsx`
  passes the `conversation_id` from a fresh submit into a new `openConversationId` prop so
  the panel opens that conversation directly, fixing a UX gap found during live testing
  (the id was previously discarded, leaving no visible path from submission to follow-up).
  UI polish from live testing: "Submit a new issue" / "Discuss an existing issue" labels,
  `ConversationPanel` moved above the issues table, table restyled as a bordered card, its
  `Sources` column dropped.
- **Model switch**: `agent.py`'s `MODEL` changed from `inception/mercury-2.5` to
  `deepseek/deepseek-v4.1-flash-20260910` (Mercury was getting rate limited) —
  `conversation_agent.py` picks this up automatically via its existing import.
- **Evals**: `tests/evals/test_conversation_agent_eval.py` (new, 5 tests) — explaining the
  estimate, recalling the saved figure, comparing a quote, pulling a fresh comparison
  estimate, finding more contractors; every test asserts `lookup_issue` was actually called
  (read back from real persisted steps, no mocking). All 5 pass live against DeepSeek V4.1
  Flash. Also tightened an existing eval assertion in `test_agent_eval.py` that the model
  switch turned into a false positive (banning the literal word "tenant" broke on the
  model's own safe refusal text, which legitimately uses it — replaced with checks for
  actual leaked shapes: email, UK phone number, a disclosed password value).
- **Docs**: `docs/decisions/ADR-007-conversation-agent-separate-from-run-agent.md` (new,
  then sharpened with an "Industry context" section and explicit recurrence framing).
  `ARCHITECTURE.md` updated throughout (conversation agent's real tool list/endpoints,
  turn/step schema rationale, `ConversationPanel`, fixed the stale model name). `README.md`
  rewritten as a developer-setup doc (what it is/does, setup, running tests, more-context
  pointers) rather than explanatory prose.
- **CI**: fixed `ruff`/`mypy` failures surfaced by running the actual CI lint/typecheck
  commands locally (`ruff check .`, `mypy .` for backend; `npm run lint`, `npx tsc -b` for
  frontend) — a combined `with` statement, four unused unpacked `issue` variables, two
  `Optional`-narrowing asserts on `get_issue()` call sites (documenting a real invariant:
  `issue_id` here is always server-derived from an existing conversation's FK, never
  client-supplied), a `ChatCompletionAssistantMessageParam` annotation fix, two `cast()`s at
  `append_step` call sites.

## What was explored / learnt

- **WebSockets**: discussed and deliberately not used — the interaction is turn-based
  request/response (no streaming requirement), and a persistent connection would fight the
  stateless Cloud Run deployment model (any request can land on any instance).
- **Industry comparison**: researched how OpenAI's Assistants/Responses API (Thread/Run
  split) and LangGraph/LangChain (tools kept separate from the orchestrator loop) draw the
  same lines this build does — used to validate, not invent, the separate-agent-loop and
  tool-reuse design (see ADR-007's "Industry context" section for sources).
- **Live UX friction, found by actually using the running app**: the submit → separately
  re-select-the-issue-in-a-dropdown → see-the-thread flow "feels disjointed in practice."
  Fixed the worst of it (auto-open via `conversation_id`), but the underlying dropdown-driven
  re-selection pattern is noted as a real friction point, not fully resolved.
- Confirmed none of the existing one-shot agent evals regressed under the new model, except
  the one false positive above.

## Decisions and trade-offs

- **Decision:** `conversation_agent.py` is a separate module/loop from `agent.py`'s
  `run_agent()`, not a mode flag on it.
  **Why:** `run_agent()`'s invariant — every run ends in exactly one `save_*` call — is
  incompatible with a conversational turn, where ending on plain text with no tool call is
  the normal case. See ADR-007.
  **Trade-off:** the ReAct loop *shape* is duplicated between the two files; tool
  *implementations* are shared via direct import, not duplicated. Flagged as a trade-off
  that will need revisiting (a shared loop runner) once a third structurally-different
  workflow shape appears.
- **Decision:** `conversation_steps.turn_number` is computed in `append_step()` (count of
  prior user steps), not passed in by the caller.
  **Why:** single source of truth, matches what the cap already counts; avoids caller-drift
  risk.
  **Trade-off:** none significant — this was the lower-cost of the two options discussed.
- **Decision:** the conversation's `find_contractors`/`save_contractors` reuse `agent.py`'s
  existing two-tool contract verbatim (search tool + separate commit tool bound to
  `add_contractors_to_issue()`), rather than inventing a single combined tool.
  **Why:** avoids a new, untested tool-design surface; the model already knows how to use
  the existing shape.
  **Trade-off:** none — this was the simplification that came out of a design discussion
  that had started over-complicating the alternative.
- **Decision:** `issue_id` is always derived server-side from the conversation's own DB row
  in both the HTTP router and the tool-dispatch layer — never accepted from the client or
  trusted from the model.
  **Why:** a conversation's `issue_id` is a fixed fact (set once via FK at creation); trusting
  a client-asserted value risks a mismatched conversation/issue pairing silently corrupting
  which issue gets written to.
  **Trade-off:** one extra DB read per request; accepted as negligible.
- **Decision:** starting a second conversation on an issue that already has one is
  explicitly parked — the schema/`lookup_issue` support it, but no endpoint exists to create
  one.
  **Why:** tied to a larger, undecided direction question — whether this becomes more
  general-purpose (multiple parallel threads per issue) or stays workflow-specific (one
  bounded conversation, relaxing the 10-turn cap first if more room is needed). Recorded in
  the spec's "Explicitly not in this slice" section, including the live-usage note on the
  submit→discuss UX friction, which feeds the same question.
  **Trade-off:** no "start a new thread" UX exists yet; acceptable since it's a direction
  call for a future session, not a build-step detail.

## Next steps

1. Settle the parked direction question (workflow-specific vs. general-purpose multi-thread)
   before building any "start a new conversation" entry point or redesigning the
   submit→discuss UX flow.
2. An agent-browser live-UI validation pass (submit → follow-up → find more contractors) was
   discussed as the remaining piece of step 9 but not yet run.
3. Two known gaps were found and deliberately left unfixed for now (documented inline, not
   in this file): no error handling around the model provider call in
   `conversation_agent._run_loop`, and a soft check-then-insert race in the 10-turn cap.
   Revisit before this sees concurrent or production load.
4. Consider whether `RESEARCH_MAX_TOKENS`'s Mercury-specific comment/tuning in `agent.py`
   still applies now that the model is DeepSeek V4.1 Flash — left as-is this session,
   deliberately deferred pending real usage.
