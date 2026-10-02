# ADR-006: News feed automation topology

## Status
Accepted

## Date
2026-10-02

## Context
The PRD (`docs/prds/production-v1-prd-200926.md`, Story 3/4) wants landlord-relevant news
(NRLA, Tenancy Deposit Scheme) pulled periodically, persisted, and shown on the homepage. The
data-pull logic and UI shape were already prototyped and validated
(`prototypes/news_feed_data_pull_prototype.py`, `news_feed_api_prototype.py`,
`news_feed_dashboard_prototype.html`); this decision is about how that pull runs in production
on a schedule, not what it pulls or how it's displayed. Needed to choose: what triggers the
pull, what compute runs it, how it reaches the issues database, and how the frontend reads the
result. Full design discussion captured in
`docs/specs/news-feed-automation-brief-spec-011026.md`; this ADR formalizes the topology
decision and supersedes that spec as the source of truth for it.

## Decision
- **Cloud Scheduler → a Cloud Run Job** (`infra/news_feed_job.tf`), not a Service. A Job has no
  HTTP ingress at all, so IAP's native-integration model (ADR-002, built for an interactive
  browser flow) doesn't apply and doesn't need to — there's no inbound request to gate. Cloud
  Scheduler calls the Cloud Run Jobs API's `:run` method directly, authenticated as a dedicated
  scheduler service account with `roles/run.invoker` scoped to just this one Job.
- **Direct `psycopg` write to the issues database**, no API/HTTP layer in that path. The Job
  shares the Service's VPC subnet (`house-mgmt-run`) and connects to the same Postgres VM
  (ADR-004) the same way the Service does — same network path, same `house_mgmt_app` role.
- **A dedicated service account for the Job** (`google_service_account.news_feed_job`),
  separate from the Service's own runtime identity and the DB VM's, matching this project's
  existing one-SA-per-workload pattern (ADR-004). It has `secretAccessor` on
  `DATABASE_PASSWORD` only — no other project roles.
- **Shared Cloud Run image, not a second Dockerfile.** CI/CD's deploy step
  (`.github/workflows/ci-cd.yml`) now also runs `gcloud run jobs update --image=...` against
  the same image it just built and deployed to the Service, overriding only the container
  command (`python -m jobs.pull_news_feed`) via Terraform. `infra/manual_deploy.sh` mirrors
  this for the no-Actions fallback path.
- **Read path stays entirely inside the existing IAP-gated Service**: `GET /api/news-feed`
  (`routers/news_feed.py`) returns the latest 10 articles, newest-first — read-only, never
  writes to `articles`. Only the Job writes.
- **`services/db_connection.py`**, extracted from `services/issues_db.py` this session, resolves
  DB credentials for both the Service and the Job: it checks for either `K_SERVICE`
  (Service-only) or `CLOUD_RUN_JOB` (Job-only — Cloud Run Jobs don't set `K_SERVICE`), since
  both need the same Secret-Manager-backed credential assembly in production.

## Alternatives Considered

### Cloud Scheduler → authenticated HTTP call into the existing Service
- Pros: no second Cloud Run resource to provision; reuses the Service's existing request
  handling.
- Cons: the Service sits behind Cloud Run's native IAP integration (ADR-002), which is built
  for interactive Google-account sign-in, not a non-interactive scheduled caller — would need
  either a second, non-IAP ingress path carved out of the same Service (undermining the
  "every path gated" property ADR-002 relies on) or a separate authentication scheme bolted on
  just for this one caller.
- Rejected because: a Job has no ingress at all, which sidesteps the mismatch entirely instead
  of working around it.

### A GitHub Actions scheduled workflow (`schedule:` trigger)
- Pros: no new GCP compute resource; reuses CI/CD's existing credentials and tooling.
- Cons: GitHub-hosted runners aren't on the project's VPC (`infra/network.tf`) and can't reach
  the issues-DB VM's private IP at all — the DB has no public port by design (ADR-004).
- Rejected because: would require either exposing the DB publicly (contradicts ADR-004's whole
  network design) or adding an HTTP layer in front of it just for this one caller — more moving
  parts than a Cloud Run Job already on the right network.

### An in-process scheduler inside the FastAPI app (APScheduler / an asyncio loop)
- Pros: zero new infrastructure — ships inside the existing Service.
- Cons: unreliable specifically on Cloud Run — an idle Service instance can be scaled to zero or
  have its CPU throttled between requests unless paying for "CPU always allocated," so a timer
  running inside the process has no guarantee it ever fires.
- Rejected because: Cloud Run's execution model doesn't support "stays running and does things
  on its own schedule" without paying for always-on CPU, which this single-user app doesn't
  otherwise need.

### A queue/pub-sub layer (Pub/Sub or Cloud Tasks) fanning out per source
- Pros: per-source failure isolation, buffering, decoupling — real benefits at scale.
- Cons: none of the problems a queue solves exist yet at 2 sources run once every 2 days.
- Rejected (for now) because: commit-per-source inside a single Job execution already gets the
  main benefit (one source failing doesn't lose the other's data) without the operational
  overhead of a queue. Revisit if the source list grows meaningfully — the natural upgrade path
  is fan-out via Pub/Sub or Cloud Tasks, one message per source.

### A second, dedicated least-privilege Postgres role for the Job
- Pros: the Job could only ever write to `articles`, not `issues`/`contractors` — genuine
  defense in depth.
- Cons: the existing `house_mgmt_app` role already has `GRANT ALL ... ON SCHEMA public`
  (ADR-004) with no per-table ACL anywhere in this project yet; building per-table isolation
  for just this one new workload, without a broader least-privilege pass across every role,
  is inconsistent scope for this slice.
- Rejected (for now) because: explicitly accepted as a known, deliberate gap, not an oversight —
  revisit if/when this project does a broader DB privilege-separation pass.

## Consequences
- Two Cloud Run resources (a Service and a Job) now share one image and one CI/CD deploy
  step — a future change to the Job's runtime behavior that isn't just the image (e.g. a
  different Python version, a different base image) would need its own build path, not just a
  Terraform edit.
- The Job can write to any table `house_mgmt_app` can reach, not just `articles` — unchanged
  from the existing single-role model (ADR-004), now shared by a second, independently-triggered
  workload. A future incident involving the Job's credentials has the same blast radius as one
  involving the Service's.
- `services/db_connection.py`'s `K_SERVICE`/`CLOUD_RUN_JOB` branch is now load-bearing for two
  independent production workloads — a future Cloud Run product change to either env var would
  break both, not just one.
- No queue/fan-out exists yet — adding a third news source is still a straightforward addition
  to the same Job (one more `fetch_*`/`_pull_source()` call), not a redesign, up to the point
  where per-source isolation or independent scheduling actually becomes necessary.
