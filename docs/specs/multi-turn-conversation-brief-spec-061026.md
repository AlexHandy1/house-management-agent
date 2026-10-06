# Brief spec: issue conversations (read/search slice, build-ready)

**Date**: 2026-10-06
**Supersedes**: `multi-turn-conversation-brief-spec-021026.md` (kept for discussion history).
**Status**: Not built. Decisions below are agreed. Open items are flagged and should be
settled at the start of the build session, not before.
**Format note**: deliberately brief, not the full `/create-technical-spec` template. This is
a co-pilot starting point. Expect to clarify and extend in the build session itself.

## Goal

Let the landlord hold bounded conversations about an issue, so follow-up questions are
answered with the issue's real context instead of a fresh one-shot run. Each issue can have
multiple conversations, and each conversation is capped at 10 user messages. Primary value is
**read and search**: explaining and interrogating what the agent already produced.

Motivating examples:
- "Explain further why you gave that cost estimate. I don't understand point XYZ."
- "I received this quote from a contractor. Why might it differ from your estimate?"
- "Find me some more contractors for this issue."

## Agreed shape

- **A conversation opens immediately on issue submission.** The first response is already
  part of a conversation, so it can be referred back to right away. The existing
  `POST /api/issue` response is unchanged, plus a `conversation_id`.
- **Multiple conversations per issue.** Each has its own 10-message cap. The agent draws
  context from across all of an issue's conversations, not just the one open.
- **Cap counts user messages only**, per conversation. Enforced server-side (HTTP 409 at the
  limit).
- **Context via tools, not the system prompt.** Issue context is not injected into the
  prompt. The system prompt spells out the expected flow: on any follow-up, first call
  `lookup_issue` to pull the bound issue and its prior conversations, then answer. The agent
  should always pull both, since the links are direct.
- **Read tools**: `lookup_issue(issue_id)`, `research_cost` (for "go deeper" and "compare"),
  and read access to the `articles` table.
- **One write tool**: `find_contractors` bound to the issue. Results are **added** to the
  issue's contractors, never replace them. Dedup uses the existing contractor upsert and
  `issue_contractors` link.
- **No cost estimate revision.** A conversation never overwrites an estimate. Revision,
  lifecycle status (`status`, `actual_cost`, `resolved_at`) and the "confirm resolved" step
  are deferred to the lifecycle slice.
- **UI tool-call visibility**: a single status line while a tool runs. Full detail is stored
  in turns.
- **Tracing requirement**: the trace must show the full hierarchy: steps within each turn
  (tool calls and sub-calls, as today) and how turns chain across a conversation. The shape
  is decided at co-pilot, but this is the bar it has to meet.

## Build steps (proposed order, TDD per step)

Each step is one logical commit. Steps 1–3 are backend and testable without the UI.

1. **Schema.** Add `conversations` and `conversation_turns` in `services/issues_db.py`
   (`init_schema()` on startup). Tests cover create, append, and the message-count cap.
2. **Create conversation on submit.** `POST /api/issue` creates the conversation alongside
   the issue row and returns its `conversation_id`. The existing outcome contract and the
   `AgentOutcome` shape stay unchanged.
3. **Read tools.** `lookup_issue(issue_id)` returns the issue row, its estimate, its
   contractors, and all prior conversations for it (see open item 1 on how much history).
   Tests use the same capturing-function pattern as the existing evals.
4. **Conversation agent entry point.** A new function separate from `run_agent()`. It takes
   the conversation's stored turns, runs the loop, persists the new user/assistant/tool turns,
   and enforces the cap. System prompt encodes the lookup-first flow.
5. **Write tool.** `find_contractors` bound to the issue, saving via the existing upsert and
   link. Test that it adds without removing existing contractors.
6. **Endpoints.** List an issue's conversations, read one conversation's turns, post a
   message to a conversation (runs step 4 and returns the new assistant turn).
7. **Trace.** Each post produces a turn-level Langfuse span nesting that turn's tool calls,
   and the conversation id is attached so turns can be grouped (see open item 4).
8. **Frontend.** Issue dropdown (fed by the existing issues list), conversation list for the
   chosen issue, a thread view in the ChatGPT/Claude style, a message input, a visible
   message counter, a "conversation closed" state at the cap, and a status line during tool
   calls. Prototype the layout first (see open item 3).
9. **Validation.** One agent-browser pass over submit → follow-up → second conversation on
   the same issue → find more contractors. Plus an eval or two for the "explain this
   estimate" and "why might this quote differ" questions.

## Security and deployment notes

- No auth change. IAP single-owner gating is unchanged, and the new endpoints sit behind it
  like the existing ones.
- Same database role and VPC path as the Service. No new infrastructure is expected. Confirm
  this at step 1.
- Known gap carried over: the `house_mgmt_app` role has `GRANT ALL ON SCHEMA public`, so there
  is no per-table isolation. Accepted, as in ADR-006.

## Open items (settle at the start of the build session)

1. **Cross-conversation context size.** `lookup_issue` pulls prior conversations. Full replay
   of all of them could grow large. Options: full history (simple, risks size), or a short
   per-conversation summary plus the most recent conversation in full. This is a
   context-growth question, so it's flagged even though compaction is out of scope.
2. **Article depth.** Can the agent usefully read full article bodies, or is stored text plus
   summary enough? Test how much complexity full-article access adds before committing. Only
   text and summary are stored today.
3. **Tool-call visibility and cap-hit UX** can be prototyped at step 8 (`/prototype` for the
   thread layout and status line).
4. **Langfuse trace shape.** Requirement is set above. Choose the nesting and conversation
   grouping at step 7, using the co-pilot session.

## Explicitly not in this slice

- Cost estimate revision and lifecycle fields (`status`, `actual_cost`, `resolved_at`).
- Creating a different issue mid-conversation.
- Context compaction or summarisation (the cap of 10 per conversation keeps this bounded).
- Per-table least-privilege DB role (deferred, not rejected).
- Full-article reading, unless open item 2 says it's worth it.

## References

- `ARCHITECTURE.md`: current agent loop, issues DB and request flow.
- `docs/specs/multi-turn-conversation-brief-spec-021026.md`: predecessor draft and the original
  discussion.
- `docs/specs/news-feed-automation-brief-spec-011026.md`: format reference for this doc.
- `docs/decisions/ADR-005-contractors-data-model-and-agent-tool-independence.md`: agent-loop and
  outcome contract this slice must stay compatible with.
- `docs/decisions/ADR-004-issues-database-hosting.md`: DB hosting for the new tables.
