# Work Summary — 16 September 2026

Session goal: no code changes. Strategic pivot discussion — reconsider the mobile/Telegram-first
direction from the 14 Sep session and agree the next actual build priority.

## What was built

Nothing in this codebase — planning/direction session only.

## What was explored / learnt

### Pivot away from mobile-channel-first

User proposed refocusing the first build around a web interface (accessible via mobile browser)
rather than a Telegram-type bot, and prioritising functionality that replaces what the user
currently does manually to support an estate agent:
- Generate a cost estimate for a reported issue, to compare against contractor quotes
  (extended: vet whether the issue needs more info / needs a contractor at all).
- Find appropriate contractors for a reported issue via web search, compared against an existing
  list (extended: vet contractors, e.g. online reviews — also applicable to agent-suggested
  contractors).
- Get a comparison quote from a real contractor vs. what the estate agent suggested — covers
  drafting a ready-to-send email to target contacts (extended: get mobile number, start SMS/
  mobile comms pathway).
- Building a year-end ledger of income vs. expenses (later slice).

Managing tenant↔contractor comms pathways (the rationale behind the mobile-chat-first idea from
14 Sep) is still seen as important for a full replacement system, but explicitly not what to
spend time on now.

### Reconciling with existing design work

On review, this pivot is smaller than it first appears: the ReAct loop design in
`docs/specs/maintenance-agent-slice1-full-prototype.md` is already channel-agnostic (artifacts +
`approve` CLI, no Telegram assumption). The new priority list maps closely onto tools already
specified there — `research_cost`, `find_contractors`, `propose_cost_estimate`,
`shortlist_contractor`, `draft_message` — so the pivot mainly resequences *which layer wraps the
loop* (web UI now, mobile channel later), not the loop design itself. The 14 Sep Telegram/Cloud
Run ingress research is deferred, not wasted.

Auth/login was raised as a reason web would be "quicker to extend" — clarified that auth is
**not** needed for the current single-user, landlord/estate-agent-facing scope, and should wait
until the system extends into invoicing/ledgers (multi-party, higher-stakes data).

## Decisions and trade-offs

- **Decision:** Defer the Telegram/mobile-ingress prototype planned on 14 Sep; do not build it
  next. **Why:** faster path to personal utility and to a demoable artifact, per priorities below.
  **Trade-off:** the ingress/webhook/Cloud Run research from 14 Sep sits unused for now — accepted
  as still valid when the mobile channel is picked back up later, not wasted work.
- **Decision:** Priority order is (1) personal utility tooling for the user's own manual
  estate-agent workflow, (2) a demoable version of the same (dashboard or a visual example of the
  agent completing a cost estimate — form not yet decided), (3) auth/login only once the system
  extends to invoicing/ledgers. **Why:** get immediate value from the user's own recurring manual
  work before investing in presentation or multi-user concerns. **Trade-off:** no shareable/
  demoable output until priority 2, which may matter if the user wants to show this to others
  sooner.
- **Decision:** The next prototyping focus is the evaluation and observability harness for the
  reported-issue → cost-estimate → find-contractors loop, built out from the plan already in
  `docs/specs/maintenance-agent-slice1-full-prototype.md` §9 (trace pretty-printer → error
  taxonomy → golden cases), rather than moving straight to a production web build. **Why:** user
  wants desired agent behaviour nailed down and made robust/observable before investing in a full
  production UI around it. **Trade-off:** delays any user-facing (even personal-utility) surface
  until the harness work is done — accepted since it de-risks the production build.
- **Decision (explicit scope note, not yet resolved):** all existing state-management work
  (`state_management_flow_prototype.py`, the SQLite schema in spec §7 — `issues`,
  `issue_artifacts`, `issue_turns`, `contractors`) stays in scope and must be carried into the
  harness/production work so updates and progress can be stored as the build continues. **Why:**
  user does not want to lose the state-persistence design already done. **Trade-off:** none
  identified — this was reconfirmed as still required, not re-litigated.

## Blockers

None. Planning/discussion session only.

## Next steps

1. **Scope the evaluation/observability harness** for the issue → cost estimate → find
   contractors loop. Two open questions raised but not yet answered:
   - **Path scope:** does the harness cover Paths C and D only (known-contractors / full-search,
     the paths that actually exercise contractor search), or all four paths (A triage-only, B
     needs-info, C, D) including path-selection correctness?
   - **Replay vs. live tools first:** start with real web-backed tool calls to observe genuine
     research quality and freeze good runs into fixtures, or hand-write golden cases first and
     develop against the replay suite from the start?
2. Once the harness scope is agreed, move to detailed prototyping of it (separate session/slice —
   user explicitly paused before going deeper here).
3. After the loop's behaviour is nailed down and the harness is robust, move that slice into a
   full production web build — carrying forward the existing state-management design.
4. Carried over, unchanged from 14 Sep: fake-tool-call gap with the `mercury` model; exact-name
   contractor matching risk in `find_or_create_contractor()`; deferred paths (triage-only,
   needs-info, landlord `reject` re-entry); real ingress classifier; whether to move the loop
   model to `claude-sonnet-5`; contractor-mutation tool design question; property-in-DB domain
   model (currently file-only); mobile approval shape; `ARCHITECTURE.md` still a placeholder now
   that there's also a prioritisation decision and an evaluation-harness plan to describe;
   `prototypes/README.md` update noting the preferred-contractor flow — still not done.
