---
name: create-prd
description: Create a Product Requirements Document covering the problem, personas, user stories, requirements, and key technical slices for a product or feature. Use when the user wants a PRD, asks to document product requirements, or wants an overall picture of what's being built before technical spec work starts.
---

# Create PRD

Produce a PRD that gives an overall picture of the product or feature: the problem, who it's for, what they need to do, and the technical slices the work will break into. This is the *shape* document — `/create-technical-spec` writes the detailed, implementable spec for each slice afterward.

**Relationship to `/grill-me`**: this skill runs a short interview scoped only to filling PRD template gaps. It does not stress-test the underlying idea — that's `/grill-me`'s job. If the user wants the plan itself pressure-tested (edge cases, alternatives, "have you considered..."), point them at `/grill-me` after the PRD draft exists, don't try to do both here.

## Step 1: Gather context first

Before asking the user anything, read what already exists:

1. Root `README.md` and any `ARCHITECTURE*.md` — what the project is, current approach.
2. `prototypes/` (or wherever the project's throwaway prototype code lives) and its own `README.md` — the authoritative map of what's actually been built and proven, as opposed to what was only planned.
3. `docs/status_docs/` — every `WORK_SUMMARY_*.md` and `PLANNING_*.md`, not just the most recent (see `/plan-recap` for how to find and order these). Each of these docs tends to mix prototype learnings and design decisions together rather than mapping cleanly to one technical slice — so read broadly and synthesize which distinct slices of work actually exist, rather than assuming any single doc corresponds to one slice.
4. Any existing PRDs in `docs/prds/`.

Present a short interpretation of the feature/product being scoped, grounded in what you found: "Here's what I understand this PRD needs to cover, based on X and Y — is that right?"

## Step 2: Targeted interview

Ask only about gaps that would leave a PRD section empty or vague — not a general design interview. Use `AskUserQuestion`, 2-3 questions per round, and stop as soon as each section below has enough to write:

- **Problem & impact**: what's broken or missing today, why it matters now.
- **Personas**: who uses this, and anything about them that changes what "good" looks like.
- **User stories**: the 3-5 core things a user needs to be able to do (not implementation detail).
- **Scope boundary**: what's explicitly MVP vs. later vs. out of scope.
- **Known technical slices**: if prototyping has already happened, the slice boundaries usually already exist in practice even though the planning docs don't map 1:1 to them (a single `PLANNING_*.md`/`WORK_SUMMARY_*.md` often mixes prototype learnings for more than one eventual slice) — propose a slice breakdown based on what Step 1 surfaced and confirm it with the user rather than inventing one from scratch.

If the user has clearly already answered something in prior conversation or in the docs read in Step 1, don't ask again — state the assumption and let them correct it.

## Step 3: Draft the PRD

Write using the template below. Keep it tight — this is a working document for an AI-assisted team, not a stakeholder deck. Prefer citing real prototype findings and decisions (with file references, e.g. `WORK_SUMMARY_290726.md`) over generic placeholder language wherever the project already has evidence.

Save to `docs/prds/{feature-name}-prd-{DDMMYY}.md`, matching this project's existing `PLANNING_*`/`WORK_SUMMARY_*` date-marker convention. Create the `prds/` directory if it doesn't exist.

## Step 4: Completeness checklist, not a score

Instead of a numeric quality gate, end with a plain checklist of what's covered vs. still open:

```
Completeness check:
- [x] Problem statement grounded in real evidence
- [x] Personas defined
- [ ] Success metrics — not yet defined, flagged below
- [x] User stories with acceptance criteria
- [ ] Risk assessment — thin, only one risk identified
```

Anything unchecked should also appear inline in the doc as `[NEEDS INPUT: ...]` rather than being silently left blank or invented. Don't gate saving the file on completeness — an honest partial PRD beats a fabricated complete one.

**Security-sensitive content:** Do not record specific, exploitable detail about security or anti-abuse mechanisms — exact rate-limit thresholds, the specific detection technique used, or an explicit statement that a given input is unvalidated/unenforced. Record the category or posture instead (e.g. "rate limiting applied to public endpoints," not the mechanism or number). If unsure whether a detail is safe to write down, ask the user rather than including it.

Close by suggesting next steps: run `/grill-me` on this PRD if the user wants the plan itself pressure-tested, or move to `/create-technical-spec` for a specific slice once the PRD is settled.

## PRD Template

```markdown
# Product Requirements Document: [Feature Name]

**Version**: 1.0
**Date**: [YYYY-MM-DD]
**Status**: Draft

---

## Executive Summary

[2-3 paragraphs: what problem this solves, who it helps, why it matters now.]

---

## Problem Statement

**Current situation**: [Pain points or limitations today]

**Proposed solution**: [High-level description]

**Impact**: [Expected outcome, quantified where possible]

---

## Success Metrics

- [Metric]: [Target and how it's measured]

---

## User Personas

### Primary: [Persona Name]
- **Role**: [Who they are]
- **Goals**: [What they want to achieve]
- **Pain points**: [Current frustrations]

[Add secondary persona if relevant]

---

## User Stories & Acceptance Criteria

### Story 1: [Title]

**As a** [persona] **I want to** [action] **so that** [benefit]

**Acceptance criteria:**
- [ ] [Specific, testable criterion]
- [ ] [Edge case or error handling]

[Repeat for 3-5 core stories]

---

## Functional Requirements

### Core Features

**Feature: [Name]**
- Description: [What it does]
- User flow: [Step-by-step]
- Edge cases: [What happens when...]

### Out of Scope
- [Explicitly excluded from this release]

---

## Technical Slices

The pieces of work this PRD breaks into, each of which gets its own `/create-technical-spec` document. List what's already been validated by prototyping vs. what's still unbuilt.

| Slice | Status | Spec |
|---|---|---|
| [e.g. NL query → GBIF species selection] | Prototyped, verified | `docs/specs/spec-....md` |
| [e.g. Web deployment & CI/CD] | Not started | — |

---

## Technical Constraints

- **Performance**: [requirements, if any]
- **Security/compliance**: [requirements, if any]
- **Integration**: [external systems this depends on]

---

## MVP Scope & Phasing

### Phase 1: MVP
- [Core feature]

### Phase 2: Enhancements
- [Enhancement]

### Future considerations
- [Deferred idea]

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| [Risk] | High/Med/Low | High/Med/Low | [Plan] |

---

## Dependencies & Blockers

**Dependencies**: [What this relies on]

**Known blockers**: [Anything already identified]

---

## Appendix

### Glossary
- **[Term]**: [Definition]

### References
- [Related planning docs, prototype READMEs, external docs]
```
