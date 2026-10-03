# Work Summary — 3 October 2026

## What was built
- `infra/news_feed_job.tf`: scheduler `http_target.uri` had a duplicated `apis/run.googleapis.com` segment. Fixed in commit `0469ea0` on branch `fix/news-feed-scheduler-uri` (off `main`). Not pushed yet.
- Applied the fix to the live scheduler `house-mgmt-news-feed-pull` with a targeted apply (`-target=google_cloud_scheduler_job.news_feed_pull`).
- Verified in production: a manual `gcloud scheduler jobs run` created execution `house-mgmt-news-feed-pull-cbbfm`, run by `house-mgmt-news-feed-sched@…`. Scheduler returned HTTP 200; execution completed 1/1 with `exit(0)`.

## What was explored / learnt
- The 2 Oct manual execution (`tw7vk`, run by the user's account) succeeded because it used the correct API path. It did not exercise the scheduler's URI, so it missed the bug.
- The scheduler was created in `59219bc` (2 Oct), so 3 Oct 06:00 UTC was its first scheduled run.
- A full `terraform plan` also showed unrelated in-place drift on the production Cloud Run Service (`launch_stage` GA → BETA, null `scaling` block) and Job `client` metadata. Not applied; needs a separate look.
- `gcloud` default project is `ai-workflow-tests`, not `house-management-agent`. Pass `--project` explicitly.

## Decisions and trade-offs
- **Decision:** apply only the scheduler resource with `-target`. **Why:** the Service drift touches production and is unrelated to this fix. **Trade-off:** targeted applies skip the rest of the plan, so the drift remains.
- **Decision:** test by triggering the scheduler, not by a manual Job execution. **Why:** the manual route doesn't exercise the scheduler's URI. **Trade-off:** the test was an extra production news pull outside the every-two-days cadence.
- **Decision:** the `owner_email` used for Terraform is the deployment owner's account, supplied as `TF_VAR_owner_email` at apply time per `infra/README.md`.

## Next steps
1. Push `fix/news-feed-scheduler-uri` and open a PR to `main`.
2. Confirm the scheduled run at 06:00 UTC on 5 Oct succeeds (`gcloud run jobs executions list --job=house-mgmt-news-feed-pull --region=europe-west1 --project=house-management-agent`).
3. Investigate the Cloud Run Service drift (`launch_stage`, `scaling`) before the next full apply.
4. Return to `scope_multi_turn` for the multi-turn extension.
