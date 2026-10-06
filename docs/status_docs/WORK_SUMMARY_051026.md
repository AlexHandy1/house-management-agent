# Work Summary — 5 October 2026

Branches: `fix/tds-sitemap-404` (off `origin/main`, merged as PR #14 → `3d58158`),
then `scope_multi_turn` merged with latest `main` (`1083da0`, local only, not pushed).

## What was built

- **TDS sitemap fix** (`app/backend/services/news_data_pull.py`) — removed
  `sitemap-webarticle-weekly.xml` from `TDS_SITEMAP_URLS`. It now returns 404; the
  live sitemap index lists only `sitemap-webarticle-1.xml`. Commit `266edf1`.
- **Regression test** (`app/backend/tests/test_news_data_pull.py`) —
  `test_fetch_tds_articles_only_requests_sitemaps_listed_in_the_live_index`. Written
  first (RED: requested the weekly URL), then passed after the fix.
- **Local Postgres docs** — `README.md` gained a "Running the tests locally" section
  (`docker compose up -d`, venv, `python -m pytest tests`). `ARCHITECTURE.md`'s backend
  bullet now points to it. Commit `fec80c6`.
- **Production verification** — manual execution
  `house-mgmt-news-feed-pull-5nxq7` completed with exit 0; both NRLA and Tenancy Deposit
  Scheme logged "News feed pull succeeded". Logs don't include fetched/inserted counts.

## What was explored / learnt

- **Root cause of the recurring "failed" runs:** the 06:00 UTC job exits 1 because TDS
  raised `HTTPError 404` on the weekly sitemap. NRLA succeeded and saved in the same run.
  Job exits non-zero on any single-source failure (per ADR-006), so a TDS-only break looks
  like a whole-Job failure.
- **Live TDS check** (`fetch_tds_articles` against the real site, post-fix): 200 from
  `sitemap-webarticle-1.xml`. With the 2-day cutoff (3 Oct) → 0 articles (newest entry is
  2 Oct). With cutoff 1 Sep → 8 articles, parsing correct.
- **Dead end — gcloud default project:** `gcloud` was configured to `ai-workflow-tests`,
  which returned empty log results and prompted to enable APIs. Use
  `--project=house-management-agent` explicitly.
- **Backend DB tests need Postgres:** 15 errors (`conftest.py` connection failures) with
  no local DB running. Fixed by `docker compose up -d` (Postgres 15, `docker-compose.yml`).
  The gap was that README/ARCHITECTURE didn't say so.
- **Lint:** CI's backend job runs `ruff check .` and `mypy .` from `app/backend`
  (`requirements-dev.txt`). Both pass. `ruff format --check` flags 19 pre-existing files
  (not run in CI, left alone).
- **CI not showing on PR #14 at first:** the run was created ~2 minutes after the PR was
  opened, so the check rollup was empty briefly. Both jobs then sat in QUEUED. Not verified
  who triggered the run.
- **Scope note:** `scope_multi_turn` working tree was clean throughout; the `fix/` branch
  was briefly set to track `origin/main`, unset to avoid accidental pushes to main.

## Decisions and trade-offs

- **Decision:** remove the weekly sitemap URL (option 1) rather than discover sitemaps
  from the index at runtime (option 2). **Why:** smallest change that fixes the 404 now.
  **Trade-off:** a future TDS sitemap rename will break the Job again; runtime discovery
  remains the more robust follow-up.
- **Decision:** keep the partial-failure exit-1 behaviour (ADR-006) unchanged.
  **Why:** not in scope for this fix. **Trade-off:** a single-source failure still shows as
  a red Job with no alerting.
- **Decision:** document the local Postgres prerequisite in README and ARCHITECTURE rather
  than only in the `conftest.py` docstring. **Why:** the gap cost a debugging detour.

## Blockers

- None on the TDS fix. The full news-feed Job was **not** run against the local DB — the
  step was interrupted by the user, so the `init_schema` → job → dedupe re-run sequence is
  untested locally.

## Next steps

1. Check the next scheduled run (06:00 UTC, every 2 days) and confirm both sources
   succeed. Confirm exit 0 for the scheduled execution.
2. Run `pull_news_feed.py` end to end against local Postgres (`DATABASE_URL` →
   `house_mgmt`; call `articles_table.init_schema()` first), then re-run to confirm
   `ON CONFLICT (url) DO NOTHING` dedupe.
3. Consider runtime sitemap discovery from `sitemap.xml` (option 2) so future TDS sitemap
   changes don't break the Job.
4. Decide on alerting for single-source failures (Job currently exits 1 for either).
5. Frontend lint (`npm run lint`, `npx tsc -b`) not run locally this session — CI covers it.
6. Carried from 30 Sep: landlord news feed vs. multi-turn priority; preferred-contractors
   whitelist; multi-turn interactions; general unhandled-exception logging;
   `roles/iap.tunnelUser` IAM binding documentation.
