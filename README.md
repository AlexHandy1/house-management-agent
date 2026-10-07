# House Management Agent

An AI agent for rental-property maintenance, and a landlord's assistant more broadly.
A closed, deterministic triage step handles the initial report — a cost estimate,
contractors, or a clarifying question, whichever it actually calls for — but a landlord
isn't boxed into that fixed set of outcomes: an open-ended conversation layer sits on top
of it, reasoning freely over the saved context rather than being limited to pre-defined
actions, alongside a news feed keeping the landlord current on the regulatory/industry
context around all of this.

## What it does

- `POST /api/issue` — reports a maintenance issue. The agent researches UK repair costs,
  finds contractors, both, or asks a clarifying question — whichever the request actually
  needs — saves the result to Postgres, and opens a conversation for follow-up (returns
  `conversation_id`).
- `POST /api/conversations/{id}/messages` — an open-ended, bounded (10 user messages)
  conversation on that issue: explain the estimate, compare a quote, pull a fresh
  comparison estimate, find more contractors, or just ask — not limited to the fixed
  outcomes the triage step itself can produce.
- `GET /api/news-feed` — a landlord news feed (NRLA, Tenancy Deposit Scheme), pulled
  automatically every 2 days by a scheduled Cloud Run Job and shown alongside the issue
  history.
- Deployed behind Google-account-only auth (Cloud Run IAP), with Langfuse tracing and
  CI/CD to GCP Cloud Run.

## Setup

Requires Python 3.13, Node, and Docker.

```bash
docker compose up -d                  # Postgres 15 on localhost:5432 (repo root)

cd app/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt pytest
cp .env.example .env                  # fill in OPENROUTER_API_KEY; Langfuse keys optional locally
uvicorn main:app --reload --port 8000

# separate terminal
cd app/frontend
npm install
npm run dev                           # proxies /api/* to the backend in dev
```

## Running the tests

```bash
cd app/backend && source venv/bin/activate
python -m pytest tests                # unit tests — need docker compose up -d
python -m pytest -m eval tests/evals -s   # real LLM/web calls, costs money — run explicitly
```

```bash
cd app/frontend
npx vitest run
npx tsc -b
```

The backend test fixtures create and reset a `house_mgmt_test` database on the same
Postgres instance; without `docker compose up -d` the DB-backed tests fail with
connection errors.

## More context

- `ARCHITECTURE.md` — whole-system map: components, request flow, deploy flow
- `docs/decisions/` — ADRs for significant technical decisions
- `docs/specs/` — technical specs for individual build slices
- `docs/prds/production-v1-prd-200926.md` — the production v1 PRD
- `docs/status_docs/` — session notes and planning
- `prototypes/` — throwaway loop experiments (`prototypes/README.md`), not production code
- `infra/` — Terraform; see `infra/README.md` for the bootstrap sequence
