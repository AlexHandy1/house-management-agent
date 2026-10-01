# Work Summary — 1 October 2026

Branch: `prototype_newsfeed`. Picked up the "news feed" item flagged as the key
next-session decision in `WORK_SUMMARY_300926.md` — prioritized it over multi-turn
thread support this session.

## What was built

- **`prototypes/news_feed_scrape_prototype.py`** — deterministic, no-LLM data pull for
  the two PRD-named sources (`docs/prds/production-v1-prd-200926.md`, Story 3/4):
  NRLA's `/news` page pulled directly with BeautifulSoup (server-rendered HTML);
  Tenancy Deposit Scheme pulled via its public sitemap XML instead, since its `/news`
  page turned out to be a client-rendered Salesforce SPA with a `<webruntime-app>` shell
  and no server-side content at all, even on individual article pages — confirmed by
  curling it directly. `Article` Pydantic model (source, title, url, published_date,
  summary); TDS entries get a title derived from the URL slug and no summary (no article
  body available this way). In-memory only, no persistence. `LOOKBACK_DAYS = 7` (not the
  PRD's target 2 — neither source had anything that recent at prototype time). Lives in
  `prototypes/` only — an earlier version was built inside `app/backend/services/` and
  `app/backend/routers/`, which the user caught and had removed; `beautifulsoup4` was
  uninstalled from `app/backend/venv` and reinstalled into `prototypes/.venv` instead, to
  keep production code/deps untouched.
- **`prototypes/news_feed_api_prototype.py`** — thin standalone FastAPI app (own
  `uvicorn` process, port 8001, `CORSMiddleware` with `allow_origins=["*"]` since it's
  local-only) wrapping `fetch_recent_articles()` as `GET /news-feed`. Deliberately not a
  route on the production API.
- **`prototypes/news_feed_ui_prototype.html`** — standalone static page (no build step,
  no npm project), styled with the same CSS custom properties copied from
  `app/frontend/src/index.css` (`--accent`/`--surface`/`--border`/etc., light+dark via
  `prefers-color-scheme`), fetching `http://localhost:8001/news-feed` and rendering
  article cards. Confirmed working against live data (10 real articles, 8 NRLA + 2 TDS,
  24–29 Sep).
- **`prototypes/news_feed_dashboard_prototype.html`** — second, wider layout: a
  two-column dashboard (stacks below 760px) putting a static mock of the issue-report
  form/result/table (copied markup/classes from `app/frontend/src/App.tsx`, wired to
  nothing — no submit logic) alongside the same live news feed on the right. Answers
  "what does the homepage look like with both features on it," not a re-test of the
  issue workflow.
- **`docs/specs/news-feed-automation-brief-spec-011026.md`** — deliberately brief spec
  (not the full `/create-technical-spec` template, per explicit user request — "requirements
  get extended or invented in that format") capturing the agreed automation design, to
  pick up in a build session. See Decisions below for its contents.

## What was explored / learnt

- **TDS's news page cannot be pulled with requests+BeautifulSoup at all** — confirmed
  by curling both the listing page and an individual article page directly; both return
  only a Salesforce Lightning web-runtime shell (`<webruntime-app></webruntime-app>`),
  even the article's `<title>` tag is a static placeholder ("Welcome to LWC
  Communities!"). Its `sitemap-webarticle-1.xml` / `sitemap-webarticle-weekly.xml` (URL +
  `lastmod`) were the only deterministic signal available — this is a durable constraint
  for the real build, not a prototype shortcut to fix later.
- **NRLA's `/news` listing page is a clean target**: `a.news-article` elements with
  `h3` (title), `.news-article-description` (summary), `.news-article-meta-date`
  (`DD/MM/YYYY`). One page load covers well over 7 days of articles — no pagination
  needed at this lookback window.
- **Dead end, corrected mid-session**: first attempt used the OpenRouter web-search
  plugin + `mercury-2.5` (mirroring `_research_cost`/`_find_contractors` in
  `services/agent.py`) to find and summarize articles via LLM web search. User rejected
  this as overkill once real source URLs were known — "Both could get the recent
  articles extracted using a more deterministic web data-pull approach." Switched to
  requests+BeautifulSoup/sitemap entirely; no LLM involved in the final prototype.
- **Dead end, corrected mid-session**: built the first data-pull/router pass directly
  inside `app/backend/services/` and `app/backend/routers/`. User stopped this
  immediately — "ALL prototype work should be within prototypes/... I don't want to
  corrupt the production code setup within app at all." Removed the file and the
  `beautifulsoup4`/`soupsieve` packages from `app/backend/venv`; rebuilt entirely under
  `prototypes/` with its own venv instead. Lesson for future prototyping in this repo:
  default to `prototypes/` for any throwaway backend code, even when it needs to be
  reachable by a frontend — use a second standalone process/port, not a route grafted
  onto the real app.
- **Security stress-test on the proposed automation design** (Cloud Scheduler → Cloud
  Run Job, direct `psycopg` write, no IAP in that path) surfaced three corrections to the
  user's working mental model, now recorded in the brief spec so they aren't
  re-litigated next session:
  1. "Not carrying any identification information" is wrong — the Job carries a GCP
     service-account identity (for the Secret Manager call) and a Postgres
     username/password (for the DB connection); IAP was never what protected the DB.
  2. "The primary gate is stealing my Google credentials" conflates project-wide
     owner-compromise (true of everything) with the narrower, more realistic risk: a
     compromised dependency/logging bug/leaked secret could write to the DB without
     anyone's Google account being touched at all.
  3. "Couldn't write to other tables because it doesn't have information about them" is
     false — `database.tf` grants `house_mgmt_app` `ALL ... ON SCHEMA public`, i.e. full
     CRUD on every table including `issues`/`contractors`, not just `articles`. No
     per-table ACL exists; this is an accepted trade-off now, not an assumed protection.

## Decisions and trade-offs

- **Decision:** 7-day lookback in the prototype, not the PRD's 2-day target. **Why:**
  neither NRLA nor TDS had published anything in a 2-day window at prototype time; 7
  days was chosen just to have real data to look at. **Trade-off:** production lookback
  value is an explicit open question in the brief spec, not decided here.
- **Decision:** news feed automation will be Cloud Scheduler → a Cloud Run **Job**
  (not a Service), writing directly to a new `articles` table via `psycopg`, read back
  by the existing IAP-gated Service via a new `GET /api/news-feed`-style endpoint
  returning the latest 10, newest-first, no pagination. **Why:** a Job has no HTTP
  ingress at all, so it sidesteps the IAP-for-non-interactive-callers problem entirely
  (discussed and rejected: Scheduler→authenticated-HTTP-call-into-the-Service, and a
  GitHub Actions scheduled workflow — the latter can't reach the private VPC to write to
  Postgres at all, since GitHub-hosted runners aren't on that network). Also rejected:
  an in-process scheduler (APScheduler/asyncio loop) inside the FastAPI app — unreliable
  on Cloud Run specifically, since an idle instance can be scaled to zero or have CPU
  throttled between requests unless paying for "CPU always allocated."
  **Trade-off:** one more Terraform resource + CI/CD build target to maintain.
- **Decision:** no message queue / pub-sub layer for this. **Why:** discussed at a
  system-design level (user referenced
  `systemdesigninterview.com`'s message-queue/async-processing guide) — decoupling,
  buffering, and per-source failure isolation are real benefits of a queue, but none of
  the problems they solve exist yet at 2 sources / one run every few days. **Trade-off:**
  flagged as the first well-motivated upgrade if the source list grows (fan out via
  Pub/Sub or Cloud Tasks, one message per source) — not built now, captured in the brief
  spec as explicitly out of scope for this slice.
- **Decision:** idempotent upsert keyed on article `url` (unique constraint), decided
  regardless of queueing. **Why:** at-least-once delivery/double-firing is the default
  assumption for any scheduler (Cloud Scheduler itself can double-fire), and this also
  satisfies the PRD's Story 4 no-duplicate-rows requirement for free. **Trade-off:**
  `DO NOTHING` vs `DO UPDATE` on conflict is left as an open question — TDS's
  "published date" is really sitemap `lastmod`, which can bump on an edit to an old
  article, not just a genuine repost, so the semantics aren't free of ambiguity.
- **Decision:** wrote a deliberately brief spec
  (`docs/specs/news-feed-automation-brief-spec-011026.md`) rather than running
  `/create-technical-spec`. **Why:** explicit user preference — "I've found requirements
  get extended or invented in that format... We'll be copiloting so it doesn't need to
  be comprehensively understandable for an autonomous agent." **Trade-off:** the spec
  captures agreed shape + explicit open questions rather than fully resolving every
  detail up front; expect clarification in the build session itself.

## Next steps

1. **Build session**: pick up `docs/specs/news-feed-automation-brief-spec-011026.md`
   directly — Terraform for the Cloud Run Job (`vpc_access` block mirroring
   `infra/cloud_run.tf`'s Service config, its own service account, IAM binding for
   `DATABASE_PASSWORD` access, Scheduler's `roles/run.invoker` grant scoped to the Job),
   the `articles` table migration, the Job's entrypoint code (note: cannot reuse
   `issues_db.get_database_url()` as-is — it branches on `K_SERVICE`, which Cloud Run
   Jobs don't set), and the new `GET /api/news-feed` read endpoint.
2. Resolve the five open questions listed in the brief spec before/during that build:
   transaction semantics (all-or-nothing vs. commit-per-source), upsert conflict
   semantics, whether to add a dedicated least-privilege Postgres role for the Job,
   production lookback window, and whether TDS's title-only (no summary) cards are
   acceptable long-term or need a headless-browser fetch later.
3. Prototype files (`prototypes/news_feed_scrape_prototype.py`,
   `news_feed_api_prototype.py`, `news_feed_ui_prototype.html`,
   `news_feed_dashboard_prototype.html`) are the primary source for the data-pull logic
   and UI shape — per the prototype skill's capture step, these should move to a
   throwaway branch (not stay loose on `main`) once the real build folds in the winning
   pieces.
4. Carried from 30 Sep, still open: multi-turn interactions (deprioritized again this
   session in favor of the news feed); general unhandled-exception logging;
   `roles/iap.tunnelUser` IAM binding documentation gap.
