# Product Requirements Document: Production v1 — Landlord Agent Web App

**Version**: 1.0
**Date**: 2026-09-20
**Status**: Draft

---

## Executive Summary

Prototyping since early September has proven out the core agent pattern for a landlord
maintenance workflow — a ReAct loop with `research_cost`/`find_contractors` tools, SQLite-backed
state, and (most recently) working Langfuse tracing and eval harnesses (see
`docs/status_docs/WORK_SUMMARY_180926.md`, `WORK_SUMMARY_160926.md`). None of this has been built
as a real, deployed, tested production system yet — everything so far is throwaway prototype code
(`prototypes/`, explicitly expected to be rewritten per `prototypes/README.md`).

This PRD scopes the first production version: a single web app, personally hosted on GCP, that
does two things for the landlord (currently: just the user). First, the already-prototyped "push"
workflow — submit a reported issue, get a cost estimate and recommended contractors back,
retrievable later. Second, a new "pull" workflow — a watch loop that periodically checks two UK
landlord-news sources and surfaces a summary on the same page, building a stored archive of
article links for future reference.

The project is intended to be open-sourced (NatureQuest-style) eventually, which should shape
naming, structure, and avoiding hardcoded secrets — but concrete configurability work for
other self-hosters is explicitly deferred past this version (see Scope).

---

## Problem Statement

**Current situation**: The user currently pays a managing agent (~10% of rental income) partly to
get a second opinion on repair cost estimates and to source contractors, without confidence the
agent is doing either well. The reasoning/tool loop that could replace this has been proven in
prototype form, but there is no deployed, usable, tested version of it — nothing the user can
actually rely on day-to-day yet. Separately, staying current on UK landlord-relevant news (NRLA,
Tenancy Deposit Scheme) is a manual, easy-to-neglect task with no current tooling support.

**Proposed solution**: Take the prototyped agent architecture and turn it into a real, deployed,
minimally-guarded web app covering issue → cost estimate → contractor recommendations (retrievable
history), plus a lightweight periodic news-watch workflow summarized on the same page.

**Impact**: The user gets a working, evidenced second opinion on repair costs and contractor
options without depending on the managing agent for it, plus a low-effort way to stay current on
landlord-relevant news — while establishing the production scaffolding (deployment, auth,
observability, evals, guardrails) that later slices (compliance scheduling, ledger, comms) will
build on.

---

## Success Metrics

No formal quantitative targets for this version — single-user, personal-utility scope.
Functionally "done" means: the user can submit a real issue through the deployed web page and get
a saved, retrievable cost estimate + contractor recommendation; and the page shows a news summary
that refreshes on its own without manual intervention.

[NEEDS INPUT: no explicit success metrics defined — flagged, since this is a personal tool the
bar may just be "used regularly by the user," but worth confirming.]

---

## User Personas

### Primary: The Landlord (the user)
- **Role**: Self-managing landlord, currently paying a managing agent for parts of this workflow
  and looking to reduce reliance on them.
- **Goals**: Get a fast, evidenced second opinion on repair costs; find suitable contractors
  without manual web search each time; stay current on regulatory/news developments without
  actively tracking multiple sites.
- **Pain points**: Managing agent's cost estimates and contractor suggestions aren't verifiable;
  manually checking news sites is easy to let slip.
- **Access**: Sole authenticated user of this deployment (Google auth restricted to the user's own
  email — see Technical Constraints).

### Secondary: Future open-source adopters (not built for yet)
Other landlords who might fork/self-host this later. Acknowledged in framing (naming, avoiding
hardcoded personal detail in code) but not a driver of any functional requirement in this version
— see Scope boundary.

---

## User Stories & Acceptance Criteria

### Story 1: Submit an issue and get a cost estimate + contractor recommendation

**As a** landlord **I want to** submit a reported maintenance issue through a web page **so that**
I get an evidenced cost estimate and recommended contractors without doing the research myself.

**Acceptance criteria:**
- [ ] Landlord can enter issue text (as reported by a tenant/managing agent) on the web homepage.
- [ ] Submitting triggers the agent (ReAct loop, `research_cost` + `find_contractors` tools) and
      returns a cost estimate (best estimate + range, evidenced) and 3–5 recommended contractors
      with contact details, per existing prototype behaviour.
- [ ] Result is persisted (SQLite) and associated with the submitted issue.
- [ ] A clearly broken/abusive submission (e.g. empty text, prompt-injection attempt) does not
      crash the endpoint or produce a nonsensical result — see Technical Constraints for guardrail
      posture.

### Story 2: Review past issue submissions

**As a** landlord **I want to** see a simple list of past submitted issues and their results **so
that** I can refer back to previous cost estimates and contractor recommendations.

**Acceptance criteria:**
- [ ] Homepage (or a linked view) shows a list of previously submitted issues.
- [ ] Selecting a past issue shows its stored cost estimate and contractor recommendations.
- [ ] List reflects only this deployment's own data (single-user scope, no multi-tenant
      separation needed).

### Story 3: See the latest landlord news summary

**As a** landlord **I want to** see a summary of the latest relevant news on the same web page
**so that** I stay current without checking multiple sites myself.

**Acceptance criteria:**
- [ ] Page displays a summary of the most recent article(s) found from the two watched sources
      (NRLA news, Tenancy Deposit Scheme news).
- [ ] Summary is generated and refreshed by a periodic watch loop (approx. every 2 days), not
      on-demand per page load.
- [ ] If the watch loop hasn't run since the last summary was posted, the page still shows the
      last-known summary rather than an empty/broken state.

### Story 4: Build a retrievable archive of news article links

**As a** landlord **I want to** new articles found by the watch loop stored for later reference
**so that** I have a growing archive of landlord-relevant resources, not just the latest one.

**Acceptance criteria:**
- [ ] Each new article found (URL, title, fetched date) is stored in an `articles` entity, not
      just the most recent one.
- [ ] Watch loop detects and stores only genuinely new articles per run (no duplicate rows for
      articles already seen).

### Story 5: Only the landlord can access the deployed app

**As the deployment owner** **I want to** restrict web access to my own Google account **so that**
no one else can submit issues, see results, or run up LLM spend against my deployment.

**Acceptance criteria:**
- [ ] Unauthenticated requests to the web app are rejected.
- [ ] Only the owner's specific Google email can authenticate successfully.
- [ ] Public-facing endpoints have basic rate limiting / abuse guardrails given the light-touch
      auth model.

---

## Functional Requirements

### Core Features

**Feature: Issue submission + agent workflow (push)**
- Description: Web form → issue text → triggers the existing ReAct-loop agent (`research_cost`,
  `find_contractors` tools) → returns and persists a cost estimate + contractor shortlist.
- User flow: Landlord opens homepage → enters issue text → submits → sees result once the agent
  run completes → result and issue are saved for later retrieval.
- Edge cases: agent run fails/errors (surface a clear failure state, don't silently drop the
  submission); adversarial/injection input (existing prototype work flagged upstream-provider
  hard-refusal as a known edge case, not yet handled — see Risks); very long processing time
  (synchronous vs. async response not yet decided — see Technical Slices).

**Feature: Issue history**
- Description: Simple list of past submitted issues with their stored results.
- User flow: Landlord views list on/linked from homepage → selects an issue → sees its stored
  cost estimate and contractors.
- Edge cases: no issues submitted yet (empty state).

**Feature: News watch loop (pull)**
- Description: Scheduled job runs approx. every 2 days, checks the two configured news sources
  for new articles, stores new article links (URL, title, fetched date), reads and summarizes the
  latest, posts the summary for display.
- User flow: Runs unattended on a schedule; landlord never triggers it directly.
- Edge cases: no new articles since last run (page keeps showing last summary, per Story 3); a
  watched site is unreachable/changes structure (loop should not crash the app; failure handling
  detail deferred — see Technical Slices).

**Feature: Latest news summary display**
- Description: Same homepage (or a section of it) shows the most recent summary produced by the
  watch loop.
- User flow: Passive — landlord just sees it when visiting the page.

### Out of Scope
- Multi-tenant support / other landlords using this deployment (single-user only for this
  version).
- Tenant/contractor-facing communication features (drafting/sending messages, quote negotiation) —
  already explored in prototypes but not part of this production slice.
- Compliance scheduling, income/expense ledger — later domains per the existing design doc
  (`docs/status_docs/LANDLORD_AI_AGENT_DESIGN_IDEAS_040926.md`).
- Categorization/tagging of news articles beyond URL, title, fetched date.
- Config-driven self-host support (owner identity, watched sources, secrets as env/config for
  other adopters) — acknowledged as an open-source goal but explicitly deferred past this
  version.
- Photo/attachment support on issue submission.

---

## Technical Slices

| Slice | Status | Spec |
|---|---|---|
| Agent core (ReAct loop, `research_cost`/`find_contractors` tools) | Prototyped extensively (`prototypes/basic_eval_harness_prototype.py`, `state_management_flow_prototype.py`, `happy_path_*` variants); not production-hardened | `docs/specs/maintenance-agent-slice1-full-prototype.md` |
| State management (SQLite: issues, artifacts, contractors) | Prototyped (`state_management_flow_prototype.py`); production schema/rewrite not started | — |
| Landlord web UX (submit issue, view result, issue history) | Not started | — |
| Rate limiting / LLM guardrails on public endpoints | Not started (upstream-provider adversarial-refusal edge case noted but deferred — `WORK_SUMMARY_180926.md`) | — |
| Observability (Langfuse) | Prototyped and reviewed positively (`langfuse_eval_harness_prototype.py`, `WORK_SUMMARY_180926.md`) | — |
| Evals (deterministic + LLM-judge, vanilla + Langfuse) | Prototyped (`basic_eval_harness_prototype.py`, `run_basic_llm_judge.py`, `langfuse_eval_harness_prototype.py`) | — |
| GCP deployment (Cloud Run, DB hosting, Google auth) | Researched, not built (`WORK_SUMMARY_140926.md` — Cloud Run cost modelling, DB hosting options) | — |
| News watch loop (scheduled fetch + summarize) | Not started, needs scoping | — |
| News summary display on homepage | Not started | — |

---

## Technical Constraints

- **Performance**: none specified — single-user, low-volume, latency of an agent run is
  acceptable as long as the UI doesn't appear broken while waiting (see Story 1 edge cases).
- **Security/compliance**: access restricted to the owner's Google account only; public endpoints
  guarded by rate limiting and other LLM-input guardrails given auth relies solely on Google
  sign-in rather than deeper access controls. [Exact thresholds/mechanisms intentionally not
  detailed in this PRD.]
- **Integration**: depends on GCP (Cloud Run for hosting, a SQL-capable DB on Cloud Compute per
  prior research in `WORK_SUMMARY_140926.md`), Google OAuth, Langfuse, and the two external news
  sites (NRLA, Tenancy Deposit Scheme) as unauthenticated scrape/fetch targets.

---

## MVP Scope & Phasing

Matches the user's proposed build order.

### Phase 1: MVP
- End-to-end scaffolding: minimal ReAct loop with no tools, basic web UX skeleton, testing/evals
  infrastructure, rate limiting and other guardrails, observability wiring, CI/CD deployment, GCP
  setup, Google account auth.
- Cost estimate + contractor-find agent functionality built out into the scaffolding, with tests
  and evals.
- Issue history view.

### Phase 2: Enhancements
- News watch workflow (scheduled fetch, article storage, summarization) and its web UX.
- Minor web UX additions supporting both workflows on one page.

### Future considerations
- Config-driven self-hosting for other open-source adopters.
- Tenant/contractor comms (drafting/sending messages), compliance scheduling, income/expense
  ledger — per `docs/status_docs/LANDLORD_AI_AGENT_DESIGN_IDEAS_040926.md`.
- A demo mode/example illustrating use to others without the owner's auth (explicitly mentioned by
  the user as a later step, after both workflows exist).

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Public-facing endpoint abused/over-used given lightweight (Google-only) auth | Med | Med | Rate limiting and input guardrails called out as a required Phase 1 slice, not an afterthought |
| Upstream LLM provider hard-refuses on adversarial/injection input, surfacing as an ungraceful error rather than a handled case | Med | Low | Known from prototyping (`WORK_SUMMARY_180926.md`); explicitly deferred there — needs a production decision in this build, not further deferral |
| Watched news site changes structure or becomes unreachable, silently breaking the watch loop | Med | Low | Not yet designed — flag as an open item for the news-slice technical spec |
| Self-hosted DB on GCP Compute has no vendor SLA/failover | Low | Med | Accepted trade-off already reasoned through in `WORK_SUMMARY_140926.md` (cost vs. ops ownership) |

---

## Dependencies & Blockers

**Dependencies**: GCP account/project setup; Google OAuth app registration; Langfuse account
(already in use per prototyping); the two news source URLs remaining stable and scrapeable.

**Known blockers**: None currently — all prior prototyping blockers (deepeval trace-dump issue,
etc.) are scoped to a tool comparison that's no longer part of this plan (Langfuse was the
preferred direction — see `WORK_SUMMARY_180926.md`).

---

## Appendix

### Glossary
- **Push workflow**: Landlord-initiated — submit an issue, get a result back (cost estimate +
  contractors).
- **Pull workflow**: System-initiated on a schedule — watch loop checks news sources
  independently of any landlord action.
- **ReAct loop**: Reasoning + acting agent pattern — the agent interleaves reasoning steps with
  tool calls until it produces a final answer.

### References
- `docs/status_docs/LANDLORD_AI_AGENT_DESIGN_IDEAS_040926.md` — full functional requirement list
  and architecture reasoning for the broader landlord-agent vision.
- `docs/status_docs/WORK_SUMMARY_180926.md` — eval harness build, Langfuse/deepeval comparison.
- `docs/status_docs/WORK_SUMMARY_160926.md` — pivot to web-first, eval harness scoping.
- `docs/status_docs/WORK_SUMMARY_140926.md` — Cloud Run cost modelling, DB hosting options
  research.
- `docs/specs/maintenance-agent-slice1-full-prototype.md` — slice 1 agent behaviour spec.
- `prototypes/README.md` — map of all prototype scripts and what each proved.
