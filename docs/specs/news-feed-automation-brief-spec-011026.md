# Brief spec: news feed automation (pulling data + scheduling + display)

**Date**: 2026-10-01
**Status**: Agreed direction, not yet built — pick up in a new session.
**Format note**: deliberately brief, not the full `/create-technical-spec` template —
this is a copilot session starting point, not a spec for an autonomous agent to build
unsupervised from. Expect to clarify/extend in the build session itself.

## Goal

Automate the "pull" workflow from the PRD (`docs/prds/production-v1-prd-200926.md`,
Story 3/4): periodically pull new NRLA + Tenancy Deposit Scheme articles, persist them,
show the latest on the homepage. The data-pull logic and UI shape are already prototyped
and validated (`prototypes/news_feed_scrape_prototype.py`,
`news_feed_api_prototype.py`, `news_feed_dashboard_prototype.html`) — this spec is about
productionizing and automating that, not re-deciding what it looks like.

## Agreed shape

- **Trigger**: Cloud Scheduler, every 2 days → runs a **Cloud Run Job** (not a Service —
  no HTTP ingress, so IAP doesn't apply/isn't needed; see session discussion).
- **Data pull**: same deterministic approach as the prototype — BeautifulSoup against
  NRLA's server-rendered `/news` HTML; TDS's sitemap XML (its `/news` page is a
  client-rendered Salesforce SPA with nothing server-side to pull from directly).
- **Storage**: new `articles` table in the existing Postgres DB (same VM, same
  `house_mgmt_app` role, same VPC path as the main Service). Write is a direct
  `psycopg` connection from the Job — no API/HTTP layer in that path.
- **Idempotency**: upsert keyed on article `url` (unique constraint). Must decide
  `ON CONFLICT ... DO NOTHING` vs `DO UPDATE` — see open questions.
- **Read path**: existing IAP-gated web Service adds a `GET /api/news-feed`-style
  endpoint (mirrors `list_issues()`'s shape) returning the latest 10 articles,
  newest-first. No pagination.
- **No-new-articles case**: not an error — just log the outcome (0 new this run); the
  frontend naturally keeps showing whatever's already in the table.
- **Failure case**: a failed run writes nothing new (see open question on atomicity);
  check Cloud Run Job execution logs, no special frontend handling needed.

## Security model (stress-tested this session — don't re-litigate, just implement correctly)

- The Job needs its own explicit `vpc_access` block (Terraform) attached to the
  `house-mgmt-run` subnet — **not automatic**, must be configured same as the Service.
- The Job needs IAM access to the `DATABASE_PASSWORD` secret (via its own service
  account, or reuse of `google_service_account.run` — leaning toward a dedicated SA,
  least-privilege, matching the DB VM's own existing pattern of a separate SA).
- Cloud Scheduler's own service account needs `roles/run.invoker` scoped to just this
  Job resource.
- **Known gap, accepted for now**: the `house_mgmt_app` Postgres role has
  `GRANT ALL ... ON SCHEMA public` — i.e. no per-table isolation. The Job can write to
  `issues`/`contractors` just as easily as `articles`. True least-privilege would need a
  second DB role scoped only to `articles`. Not blocking this build; flagged as a
  deliberate trade-off, not an oversight.
- **Known code gotcha**: `issues_db.get_database_url()` branches on `K_SERVICE`, which
  Cloud Run Jobs don't set (Jobs set `CLOUD_RUN_JOB`/`CLOUD_RUN_EXECUTION` instead). The
  Job's entrypoint needs its own credential-resolution path, not a direct reuse of that
  function as-is.

## Open questions for the build session

1. Transaction semantics: one all-or-nothing transaction per run, or commit-per-source
   (NRLA succeeds even if TDS fails)? Affects what "failed run = nothing written" means.
2. Upsert semantics on a URL collision: `DO NOTHING` (first-seen wins) or `DO UPDATE`
   (refresh title/summary/date)? Matters because TDS's "published date" is really sitemap
   `lastmod`, which can bump on an edit to an old article, not just a genuine repost.
3. Dedicated Postgres role for the Job, or accept the existing single-role model for now?
4. Lookback window for production: prototype used 7 days (NRLA/TDS had nothing in the
   PRD's target 2-day window at prototype time) — confirm 2 days is viable now, or keep
   a wider window permanently.
5. TDS articles currently have no summary (no server-rendered content available) — is a
   title-only card acceptable long-term, or does this need a headless-browser fetch
   later to get real summaries?

## Explicitly not in this slice

- Per-table least-privilege DB role (see open question 3 — deferred, not rejected).
- Article categorization/tagging (PRD's own out-of-scope list).
- Any queue/pub-sub layer — discussed as a future scaling path (more sources, fan-out to
  multiple consumers), not warranted at 2 sources.
- Config-driven source lists for other self-hosters (PRD's existing deferred item).

## References

- `docs/prds/production-v1-prd-200926.md` — Stories 3 & 4, original scope.
- `docs/decisions/ADR-004-issues-database-hosting.md` — DB hosting/network/credential
  pattern this Job must follow.
- `prototypes/news_feed_scrape_prototype.py`, `news_feed_api_prototype.py`,
  `news_feed_dashboard_prototype.html` — validated data-pull logic + UI shape.
- `infra/cloud_run.tf`, `infra/database.tf` — existing Service's VPC/IAM/secret pattern
  to mirror for the new Job.
