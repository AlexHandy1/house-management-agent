---
name: create-technical-spec
description: Create a detailed technical specification for one slice of work, precise enough that an AI agent with no other context could implement it. Use when the user wants a technical spec, wants to plan a specific build (e.g. an API integration, a data pipeline step), or has a PRD and needs to break a slice out into implementable detail.
---

# Create Technical Spec

Produce one detailed, implementable technical specification for a single slice of work — not the whole product (that's `/create-prd`). The bar: an agent with zero conversation history should be able to read this file alone and build the right thing.

## Step 1: Confirm the slice

If it isn't already obvious from the conversation, ask the user which slice this spec covers. If a PRD exists in `docs/prds/`, check its "Technical Slices" table first and confirm against that rather than asking cold.

## Step 2: Gather everything already known about this slice

Read broadly before writing anything — a spec that re-derives or contradicts settled facts is worse than no spec:

1. **Existing production code** for this slice, if any already exists — the real, current source of truth for anything already built. Don't assume the prototype layer reflects final behavior once production code exists for the same area; check for drift.
2. `prototypes/` and its `README.md` — what's been built and verified there. These are especially load-bearing right now only because the project is early and most slices haven't been hardened into production code yet; as the project matures, weight production code over prototype code wherever both exist and disagree.
3. Every `docs/status_docs/PLANNING_*.md` and `WORK_SUMMARY_*.md` that touches this slice — not just the most recent. These documents mix prototype narrative with verified facts and decisions; pull out anything with lasting technical truth (verified API behavior, chosen constants, rejected alternatives and why) and treat prose narrative as background only.
4. The relevant PRD in `docs/prds/`, if one exists, for the user stories and constraints this slice needs to satisfy.
5. Any existing specs in `docs/specs/` this one depends on or should stay consistent with.

Where this research already answered a question (a verified API fact, a tuned constant, a rejected approach, current production behavior), write it into the spec as settled — cite the source. Do not re-open questions the project has already resolved.

## Step 3: Draft the spec

Use the template below. Every section should be filled in with real, specific content — not left as a placeholder. If something genuinely isn't decided yet and isn't safe to guess (a real open design branch, not just missing detail you could reasonably infer from context), mark it `[NEEDS INPUT: ...]` and name what would resolve it, rather than inventing an answer. Point genuinely unresolved design branches at `/grill-me` rather than guessing through them here.

For the test strategy section specifically: this spec describes **production work**, so it must follow this project's normal TDD approach (see `/tdd` and `/testing`) — not the project's light/deterministic-logic-only testing convention, which applies only to throwaway `/prototype` code and does not carry over here.

**Security-sensitive content:** Do not record specific, exploitable detail about security or anti-abuse mechanisms — exact rate-limit thresholds, the specific detection technique used, or an explicit statement that a given input is unvalidated/unenforced. Record the category or posture instead (e.g. "rate limiting applied to public endpoints," not the mechanism or number). If unsure whether a detail is safe to write down, ask the user rather than including it.

Save to `docs/specs/spec-{type}-{purpose}-{DDMMYY}.md`, where `{type}` is one of `schema | tool | data | infrastructure | process | architecture | design` and `{purpose}` is a short slug for the slice (e.g. `spec-tool-gbif-species-query-290726.md`). Create the `specs/` directory if it doesn't exist.

## Spec Template

```markdown
---
title: [Concise title describing the spec's focus]
version: 1.0
date_created: [YYYY-MM-DD]
last_updated: [YYYY-MM-DD]
tags: [schema | tool | data | infrastructure | process | architecture | design]
status: Design complete, not yet built | In progress | Built
sources: [List the production code, prototype scripts, and planning/work-summary docs this spec draws on]
---

# Introduction

[Short, concise statement of what this spec covers and the goal it achieves. State that this document is meant to be implementable by an agent with no other context — read it fully before writing code.]

## 1. Purpose & Scope

[What this spec's slice does, and its boundaries. State explicit non-goals — what's deliberately fixed, simplified, or deferred for this round.]

## 2. Verified Facts

[Anything already confirmed true — via existing production code, live API testing, prototype runs, or explicit decisions in prior sessions. Do not re-derive these; cite the source (file path, or "production: `path/to/file.py`") for each. This is the single most valuable section for an agent with no other context — err on the side of including more verified detail here, not less.]

## 3. Definitions

[Acronyms and domain-specific terms used in this spec.]

## 4. Requirements, Constraints & Guidelines

[Explicit, numbered list. Use bullet points or tables.]

- **REQ-001**: [Requirement]
- **CON-001**: [Constraint]
- **GUD-001**: [Guideline]
- **PAT-001**: [Pattern to follow, e.g. an existing convention in this codebase's production code]

## 5. Interfaces & Data Contracts

[APIs, function signatures, data shapes, integration points. Use code blocks or tables for schemas and real examples — prefer verified real responses/behavior over invented ones.]

## 6. Implementation Mechanics

[Concrete build detail: file layout, what's new vs. reused, concurrency/async approach, model/library choices and why, matching this project's existing production conventions and directory structure unless there's a stated reason to deviate.]

## 7. Acceptance Criteria

[Testable, Given-When-Then where useful.]

- **AC-001**: Given [context], when [action], then [expected outcome].

## 8. Test Strategy

[Full TDD per `/tdd` and `/testing` — this is production code, not a prototype, so the project's light/deterministic-logic-only prototype testing convention does not apply here. Name specific test cases and levels (unit/integration/e2e), not just "add tests".]

## 9. Rationale & Context

[Why these requirements/constraints, referencing the decisions and trade-offs already made in the source docs rather than re-justifying from scratch.]

## 10. Dependencies & External Integrations

[External systems, services, infrastructure, data sources this slice needs. Focus on what's needed, not specific package versions unless they're an architectural constraint.]

## 11. Examples & Edge Cases

[Concrete worked examples, including edge cases already discovered during prototyping or in production — cite the specific finding and its source.]

## 12. Validation Criteria

[What must be true for this slice to be considered correctly implemented — how to check the acceptance criteria in practice.]

## 13. Related Specs / Further Reading

[Links to related specs in `docs/specs/`, the parent PRD, and the production/prototype/planning source docs this spec was built from.]
```
