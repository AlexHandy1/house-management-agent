# Work Summary — 06 October 2026

## What was built
- `docs/specs/multi-turn-conversation-brief-spec-061026.md` — new build-ready brief spec for
  issue conversations. Supersedes `multi-turn-conversation-brief-spec-021026.md`, which is kept
  for discussion history. Committed as `9016e24`.
- Earlier attempts to write the spec and commit it were interrupted by the user before they ran,
  so the commit above is the only change on disk from this session.

## What was explored / learnt
- Reviewed the 2 Oct draft spec, `ARCHITECTURE.md`, and `news-feed-automation-brief-spec-011026.md`
  (used as the format reference).
- Tightened the scope from the 2 Oct draft. Settled decisions are recorded in the spec.
- The CLAUDE.md work-summary location is `docs/status_docs/`. The `summarise-session` skill
  refers to `planning_and_status_docs/`, which does not exist in this repo.

## Decisions and trade-offs
- **Decision:** A conversation opens immediately on issue submission.
  **Why:** The first response is then part of a conversation and can be referred back to.
  **Trade-off:** `POST /api/issue` now also creates a conversation row.
- **Decision:** Each issue can have multiple conversations, each capped at 10 user messages.
  **Why:** One conversation per issue would make the 10-message cap a lifetime cap on busy issues.
  **Trade-off:** `lookup_issue` must pull context from across several conversations, which
  raises the context-size question (open item 1).
- **Decision:** Issue context reaches the agent through tools (`lookup_issue`), not the system
  prompt. The system prompt instructs the agent to look up the issue and prior conversations
  first on every follow-up.
  **Why:** One source of truth, and no stale context baked into the prompt.
  **Trade-off:** Relies on the agent actually calling the tool. Revisit if it skips the call.
- **Decision:** One write tool, `find_contractors`, which adds to the issue's contractors and
  never replaces them.
  **Why:** Supports "find me more contractors" without a general write path.
  **Trade-off:** Reuses the existing contractor upsert and link, so no new contractor model.
- **Decision:** No cost-estimate revision in this slice. Lifecycle fields are deferred.
  **Why:** Keeps the slice read-and-search focused.
  **Trade-off:** Users cannot update an estimate from a conversation yet.
- **Decision:** Tracing must show the full hierarchy, both steps within each turn and how turns
  chain across a conversation. The Langfuse shape is decided at co-pilot.
  **Why:** Visibility is a requirement from the user.
  **Trade-off:** The design is deferred, so the build will need a decision before step 7.

## Blockers
- None. Open items for the build session are in the spec: cross-conversation context size,
  full-article reading depth, the thread-layout prototype, and the Langfuse trace shape.

## Next steps
1. Build session: settle the open items in the spec, starting with cross-conversation context size.
2. Build step 1: add `conversations` and `conversation_turns` in `services/issues_db.py`, test first.
3. Build step 2: create a conversation on `POST /api/issue` and return its `conversation_id`.
4. Continue the spec's build steps 3–9 in order, one commit per step.
5. Before the build session, reread `services/agent.py` and `services/issues_db.py` to confirm the
   file references in the spec.
