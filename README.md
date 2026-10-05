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

## Running the tests locally

The backend tests need a local Postgres 15 (the same major version as production and CI).
From the repo root:

```bash
docker compose up -d                       # starts Postgres on localhost:5432
cd app/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest tests                     # unit tests; eval tests need real API keys
```

The test fixtures create and reset a separate `house_mgmt_test` database on that instance.
Without `docker compose up -d` the DB-backed tests fail with connection errors.

## Status

The maintenance agent is live: report an issue, and the agent researches real UK repair
costs, finds contractors, both, or asks a clarifying question — whichever the request
actually needs — saving the result (and any contractors) to a Postgres database and
showing it in an issues table with a Contractor Y/N column. The homepage also shows a
landlord news feed (NRLA, Tenancy Deposit Scheme), pulled automatically every 2 days by
a scheduled Cloud Run Job. Deployed behind Google-account-only auth (Cloud Run IAP), with
its own private VPC and database VM, Langfuse observability, and CI/CD to GCP Cloud Run.
A preferred-contractors whitelist, multi-turn interactions, issue history filtering, and
DB backups are still to come.
