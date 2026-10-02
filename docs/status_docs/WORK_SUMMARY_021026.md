# Work Summary — 2 October 2026

Branch: `build_newsfeed`. Picked up `docs/specs/news-feed-automation-brief-spec-011026.md`
directly, per last session's planned next step — built, deployed, and smoke-tested the full
news feed feature end to end.

## What was built

Backend (all TDD'd, 52 unit tests passing, `ruff`/`mypy` clean):

- **`app/backend/services/db_connection.py`** — extracted `get_database_url()`/Secret Manager
  credential resolution out of `issues_db.py`, generalized to recognize either `K_SERVICE`
  (Cloud Run Service) or `CLOUD_RUN_JOB` (Cloud Run Job — doesn't set `K_SERVICE`). `issues_db.py`
  now imports from here; kept its own name (not renamed to `issues_table.py` — reconsidered
  mid-session once it was clear the module also owns `init_schema()` for `contractors`/
  `issue_contractors`, not just `issues`, so `_db` is an accurate name for it).
- **`app/backend/models/article.py`** — `Article` Pydantic model (source, title, url,
  published_date, summary).
- **`app/backend/services/articles_table.py`** — `init_schema()`, `save_articles()` (upsert,
  `ON CONFLICT (url) DO NOTHING`, returns count actually inserted), `list_recent_articles(limit=10)`
  (newest-first). Named `articles_table` not `articles_db` — deliberately narrower in scope than
  `issues_db` (owns only one table, no joins), so a different name was correct, not just cosmetic
  symmetry.
- **`app/backend/services/news_data_pull.py`** — NOT called a "scraper" anywhere (explicit user
  correction). `fetch_nrla_articles()` (BeautifulSoup against NRLA's server-rendered `/news` HTML)
  and `fetch_tds_articles()` (TDS's sitemap XML via regex — its `/news` page is a client-rendered
  Salesforce SPA with nothing server-side to pull). Two independent functions, not one combined
  fetch, so the Job can commit/log per source separately. Tested against fixture HTML/XML
  (`tests/fixtures/`), no live network calls in unit tests.
- **`app/backend/routers/news_feed.py`** — `GET /api/news-feed`, latest 10 articles newest-first.
  Wired into `main.py`'s lifespan (`articles_table.init_schema()`) alongside `issues_db.init_schema()`.
- **`app/backend/jobs/pull_news_feed.py`** — the Cloud Run Job entrypoint. Commits per source
  (NRLA succeeds even if TDS fails, and vice versa); `run()` returns `False` if either source
  failed so `main()` exits non-zero, while whatever succeeded is still saved. `--lookback-days`
  CLI arg, default 2. Needed `load_dotenv()` added (missed on first local run — `DATABASE_URL`
  wasn't resolving without it, same pattern `main.py` already uses).
- **`app/backend/requirements.txt`** — added `beautifulsoup4==4.15.0`, `requests==2.34.2`.

Frontend (12 vitest tests passing, lint/typecheck clean):

- **`App.tsx`** — new `NewsFeed` component, fetches `/api/news-feed` on mount alongside
  `loadIssues()`, renders article cards. Laid out in a right-hand column (`.layout` CSS grid,
  stacks to one column under 760px) next to the issue form/result/table, matching
  `prototypes/news_feed_dashboard_prototype.html`'s layout — not stacked below, per explicit
  correction mid-session.
- **`index.css`** — styled `.agent-success`/`.agent-error`/`.agent-needs-info` for the first time
  (they had **no CSS at all** before — the only matching rule, `.agent-response`, was orphaned
  dead CSS that didn't match any class actually used in `App.tsx`). Also added `.article-card`
  etc., all reusing the purple-bordered box look from the prototype, per explicit user request.

e2e (both passing against the real local stack):

- **`app/tests/test_e2e_smoke_tests.py`** (moved from `app/backend/tests/e2e/test_issue_flow_e2e.py`,
  renamed since no longer issue-flow-specific) — new scenario: resets the `articles` table
  (`TRUNCATE`), runs `python -m jobs.pull_news_feed --lookback-days 2` as a subprocess against the
  real local Postgres, then drives a real browser (`agent-browser`) to confirm the frontend shows
  the pulled articles newest-first, all within the lookback window, and no more than 10 cards
  (`get count .article-card`). `app/tests/pytest.ini` added (new standalone test root, outside
  `app/backend`'s own `pytest.ini`).

Infra (applied to the real `house-management-agent` GCP project):

- **`infra/news_feed_job.tf`** — dedicated service accounts for the Job (`roles/secretmanager
  .secretAccessor` on `DATABASE_PASSWORD` only) and for Cloud Scheduler (`roles/run.invoker`
  scoped to just this one Job); `google_cloud_run_v2_job` sharing the Service's VPC subnet
  (`house-mgmt-run`) to reach the issues-DB VM; `google_cloud_scheduler_job` firing every 2 days
  (`0 6 */2 * *` UTC) via the Jobs API's `:run` method. Applied directly this session —
  `terraform plan` surfaced unrelated pre-existing drift on the Service (`launch_stage` GA→BETA,
  dropped `manual_instance_count`/`min_instance_count`), so the apply was `-target`ed to the 7 new
  resources only, leaving that drift untouched for a separate decision.
- **`infra/services.tf`** — added `cloudscheduler.googleapis.com` to required services.
- **`.github/workflows/ci-cd.yml`** — new step after the Service deploy: `gcloud run jobs update`
  points the Job at the same just-built image (no second Dockerfile — deliberate shared-image
  trade-off, discussed and confirmed with the user: extra unused deps in the image, negligible
  cost since Jobs bill for execution time not image size).
- **`infra/manual_deploy.sh`** — same Job image update added, to stay in sync with ci-cd.yml
  (this script exists specifically to mirror it when GitHub Actions is unavailable).

Docs:

- **`ARCHITECTURE.md`** — updated and then polished into a single consolidated "The news feed"
  bullet (matching the existing "The maintenance agent"/"The issues database" per-subsystem
  pattern) instead of scattering the Job/table/endpoint across the backend bullet and a separate
  jobs bullet. Also noted `GET /api/news-feed` in the request-flow section.

## What was explored / learnt

- **TDS vs NRLA data pull mechanism** (explained in detail mid-session): NRLA's `/news` page is
  server-rendered HTML, pulled directly. TDS's `/news` page is a Salesforce Lightning web-runtime
  shell — `requests.get()` returns only `<webruntime-app></webruntime-app>`, no JS execution, so
  nothing to pull from the page itself. The sitemap XML (a standard SEO file, URL + `lastmod`,
  never page content) is the only deterministic signal available — hence TDS articles are
  title-only (derived from the URL slug), never a real summary. Two sitemap URLs
  (`sitemap-webarticle-1.xml` + `-weekly.xml`) because TDS splits its sitemap across files;
  both fetched and merged, deduped by max date on URL collision.
- **`db_connection.py` extraction**: initially planned to also rename `issues_db.py` →
  `issues_table.py` for naming symmetry with the new `articles_table.py`. User questioned this
  mid-edit — correctly pointed out `issues_db.py` owns `init_schema()` for three tables
  (`issues`/`contractors`/`issue_contractors`), not just `issues`, so `_db` is accurate for it
  and the rename would have made the name less correct, not more consistent. Reverted; only the
  new module got a `_table` name, matching its actually-narrower scope.
- **Lookback override mechanism trade-off**: discussed env var (`LOOKBACK_DAYS`) vs CLI arg
  (`--lookback-days`) for the manual-seed override. Both are one-off per-execution overrides,
  neither touches the Job's permanent definition. The real difference: `gcloud run jobs execute
  --args=...` **replaces the entire args list** for that execution, not just the overridden flag
  — a footgun an env var override doesn't have. User chose `--lookback-days` anyway for
  explicitness, accepting that trade-off knowingly.
- **CI/CD shared-image trade-off**: confirmed with user — the Job reuses the Service's full image
  (frontend static build + all FastAPI deps it never touches) rather than a second Dockerfile.
  Negligible cost (Cloud Run Jobs bill for execution time, not image size); correlated risk is a
  shared dependency surface (a vuln in a frontend-build-stage dep lands in the Job's image too,
  even though it's never imported) — acceptable for a single-user side project, would lean
  separate-image if this were multi-tenant.
- **Terraform plan surfaced unrelated drift**: `launch_stage` GA (real state, likely set by a past
  manual `gcloud run deploy`) vs BETA (what `cloud_run.tf` has always specified) on the existing
  Service, plus `scaling.manual_instance_count`/`min_instance_count` not in Terraform's config at
  all. Not caused by anything this session touched — confirmed via `grep` on `cloud_run.tf`
  (only sets `launch_stage = "BETA"`, no scaling block). Excluded from this session's apply via
  `-target`; still unresolved, see Next steps.

## Decisions and trade-offs

- **Decision:** commit-per-source in the Job (`run()` tries NRLA and TDS independently, each via
  its own try/except), not one all-or-nothing transaction. **Why:** explicit user request — "as
  long as simple as writing to each db in a separate step and then overall job flags if TDS
  fails." **Trade-off:** none really — this was the simpler implementation too (two independent
  `_pull_source()` calls, no shared transaction object).
- **Decision:** `ON CONFLICT (url) DO NOTHING` (first-seen wins), not `DO UPDATE`. **Why:** avoids
  TDS's `lastmod`-bump-on-edit ambiguity being misread as a genuine new article. **Trade-off:**
  title/summary frozen at first pull even if a source edits an article later — accepted.
- **Decision:** single-role DB model accepted for now, no dedicated least-privilege Postgres role
  for the Job. **Why:** explicit user choice from the recommended options — matches the brief
  spec's framing as an already-accepted trade-off. **Trade-off:** the Job's `house_mgmt_app` role
  can write to `issues`/`contractors` just as easily as `articles` (no per-table ACL) — unchanged
  from before this session, not worsened by it.
- **Decision:** `--lookback-days` CLI arg (default 2) over an env var, despite the args-replacement
  footgun discussed above. **Why:** explicit user preference for explainability. **Trade-off:**
  any future manual override must repeat the full args list (`-m,jobs.pull_news_feed,--lookback-
  days=N`), not just the flag.
- **Decision:** TDS title-only cards (no summary) accepted as a long-term shape, not a stopgap
  needing a future headless-browser fetch. **Why:** explicit user choice from the recommended
  options — extra infra/maintenance cost not justified yet. **Trade-off:** none tracked as
  outstanding; this closes open question 5 from the brief spec.
- **Decision:** `articles_table.py` as the new module's name, `issues_db.py` left unrenamed. **Why:**
  see "What was explored" above — `issues_db` legitimately owns multi-table schema concerns,
  `articles_table` legitimately owns only one table; forcing naming symmetry would have been
  less accurate, not more consistent.
- **Decision:** Job shares the Service's Cloud Run image (CI/CD adds one `gcloud run jobs update`
  step after the Service deploy) rather than a second Dockerfile/build pipeline. **Why:** one
  build pipeline to maintain, Job gets the `db_connection.py` fix for free since it's running the
  same codebase. **Trade-off:** extra unused deps in the Job's image (frontend build, FastAPI/
  uvicorn/etc.) — negligible cost, correlated dependency-surface risk accepted for this
  single-user project.
- **Decision:** Terraform apply for the news feed resources was `-target`ed to exclude the
  pre-existing Service drift found in the same `terraform plan`. **Why:** that drift wasn't
  caused by this session's changes and reverting it wasn't something the user had agreed to as
  part of this feature. **Trade-off:** the drift is still live in state/config mismatch — a
  separate, deliberate decision still needed (see Next steps).

## Blockers

None currently blocking — the `articles` table is seeded locally (13 real articles).

## Next steps

Carried from 1 Oct, still open: multi-turn interactions (deprioritized again), general
unhandled-exception logging, `roles/iap.tunnelUser` IAM binding documentation gap.
