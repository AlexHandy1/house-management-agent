---
name: plan-recap
description: This skill should be used when the user runs "/plan-recap", asks to "recap the plan", "summarise the last session", "what were we working on", "catch me up", or wants a session briefing from planning docs.
version: 0.1.0
---

# Plan Recap

Read planning and work summary documents in the current project and produce a concise session briefing.

## Step 1: Find the documents

Search for markdown files matching these patterns in `docs/status_docs/` (this project's convention for planning and work-summary docs):

- `PLANNING*.md` — architecture and design decisions
- `WORK_SUMMARY*.md` — what was built, current state, next steps
- `EVENT_SCOUT_PLANNING*.md` or other `*PLANNING*.md` variants

Files carry a DDMMYY date marker (e.g. `WORK_SUMMARY_050626.md` = 5 June 2026). Use that marker to sort chronologically — the highest date is the most recent.

Run a find to locate all matching files:

```bash
find docs/status_docs -name "PLANNING*.md" -o -name "WORK_SUMMARY*.md" | sort
```

If `docs/status_docs/` doesn't exist yet, fall back to a broader search of the project root:

```bash
find . -maxdepth 3 \( -name "PLANNING*.md" -o -name "WORK_SUMMARY*.md" \) | sort
```

## Step 2: Read the most recent files

- Read the **most recent WORK_SUMMARY** file in full — this is the primary source of current state and next steps.
- Read the **most recent PLANNING** file in full — this provides the architectural context.
- If there are older files and the most recent docs reference unresolved items, skim the previous WORK_SUMMARY for additional context.

## Step 3: Produce the recap

Output a structured briefing with these sections, kept tight (aim for under 300 words total):

### What was built
One or two sentences on the concrete deliverables from the last session.

### Current state
The state of the system right now — what works, what is broken or incomplete.

### Blockers / open questions
Any unresolved issues, broken integrations, or decisions that were deferred.

### Next steps
The prioritised list of tasks to pick up, drawn directly from the docs.

---

Do not pad the recap. If the docs are sparse, the recap should be sparse. Preserve the exact priorities and wording from the planning docs rather than paraphrasing into generalities.
