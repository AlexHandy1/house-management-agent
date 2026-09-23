# House Management Agent

Exploring an AI agent for rental-property maintenance: take a reported issue, research a
cost estimate, find contractors, draft the messages — with a human approving anything sent.

See:

- `ARCHITECTURE.md` — whole-system map of the production app
- `docs/decisions/` — ADRs for significant technical decisions
- `docs/prds/production-v1-prd-200926.md` — the production v1 PRD
- `docs/specs/maintenance-agent-slice1-full-prototype.md` — the slice 1 prototype spec
- `docs/status_docs/` — session notes and planning
- `prototypes/` — throwaway loop experiments (`prototypes/README.md`), not production code
- `app/backend`, `app/frontend`, `infra/` — the production app and its infrastructure

## Status

Phase 1 MVP scaffolding deployed: minimal ReAct loop (no tools yet), web UX, guardrails,
Langfuse observability, Google-account-only auth (Cloud Run IAP), CI/CD to GCP Cloud Run.
The real cost-estimate/contractor-find agent behaviour (prototyped, not yet wired into
production) and issue history are still to come — see `ARCHITECTURE.md`'s "What's live vs.
deferred".
