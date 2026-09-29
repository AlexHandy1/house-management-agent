# ADR-004: Issues database hosting and access

## Status
Accepted

## Date
2026-09-29

## Context
The research-cost agent needs a persistent issues database
(`services/issues_db.py`, `docs/specs/spec-architecture-research-cost-agent-and-issues-db-280926.md`).
This required choosing: managed vs. self-managed Postgres, network topology
(the auto-created `default` GCP network vs. a dedicated VPC), Postgres
version, backup strategy, and how the app resolves its DB credentials in
production vs. local dev.

## Decision
- **Self-managed Postgres on a free-tier `e2-micro` Compute Engine VM** in
  `us-central1` (`infra/database.tf`), not Cloud SQL. This is a
  single-table, single-user personal app; Cloud SQL's cheapest tier still
  costs meaningfully more per month than a free-tier VM, for operational
  guarantees (managed backups, HA, in-place upgrades) this app doesn't need.
- **A dedicated custom VPC** (`infra/network.tf`), not the auto-created
  `default` network, with `routing_mode = "GLOBAL"` set explicitly. A
  custom VPC has no default firewall rules — this project's only two rules
  (Postgres from the Cloud Run subnet, SSH via IAP only) are the ones it
  defines itself, nothing inherited.
- **Cross-region topology**: Cloud Run stays in `europe-west1` (existing
  service, unchanged); the DB VM is in `us-central1`, chosen for free-tier
  `e2-micro` eligibility, not proximity. Cloud Run reaches it over Direct
  VPC egress on a private subnet — private IP only, no public Postgres
  port. Cross-region latency (~100ms) is negligible against the agent's
  tens-of-seconds runs; the resulting inter-region egress cost is expected
  to be pennies at single-user volume.
- **Postgres version: the distro default via apt** (Debian 12 ships 15),
  pinned identically in `docker-compose.yml`, CI, and the VM — not the
  newest available (16), to avoid a third-party apt repository (PGDG)
  purely to chase a version number nothing in this schema/query set
  requires.
- **Privilege separation**: a dedicated non-superuser role
  (`house_mgmt_app`) owns the `issues` database; the app never connects as
  the `postgres` superuser.
- **Snapshot backups: deferred**, not built in this slice — no data is
  valuable enough yet to justify the ongoing storage cost. Add when that
  changes (see spec 6.3, item 3, marked deferred 29 Sep).
- **Credential resolution mirrors the existing OpenRouter-key pattern**
  (`services/agent.py`'s `resolve_api_key()`): `K_SERVICE` (auto-set by
  Cloud Run, never set locally) switches `get_database_url()` between
  reading `DATABASE_URL` directly (local dev — one fully-formed
  connection string) and assembling a DSN from three non-secret env vars
  (`DB_HOST`, `DB_NAME`, `DB_USER`, set in `infra/cloud_run.tf`) plus a
  password fetched live from Secret Manager on every call (production).
  The DB VM has its **own** dedicated service account (separate from Cloud
  Run's), with `secretAccessor` on that one password secret only, and
  refreshes the role's password from it on every boot.

## Alternatives Considered

### Cloud SQL (managed Postgres)
- Pros: managed backups/HA/upgrades, no VM to patch.
- Cons: no tier that fits this workload for free; the cheapest always-on
  tier costs several times an `e2-micro` VM per month, for guarantees a
  single-user personal app doesn't need.
- Rejected because: cost/complexity doesn't match the app's actual scale.

### The auto-created `default` network
- Pros: zero network config — Compute Engine "just works" without a
  custom VPC.
- Cons: enabling the Compute Engine API auto-creates permissive default
  firewall rules (SSH/RDP open to `0.0.0.0/0`); importing and then
  destroying rules on a network still implicitly available to future
  resources is more fragile than never creating them.
- Rejected because: a custom VPC with zero default rules is simpler to
  reason about, not just "more secure" in the abstract.

### Pinning Postgres 16 via the PGDG apt repository
- Pros: matches the version used in earlier local prototyping (Docker
  `postgres:16`).
- Cons: adds a third-party apt repository, a GPG key fetch, and one more
  moving part to the VM's first-boot script, for a version difference
  nothing in this schema/query set depends on.
- Rejected because: aligning everything down to the distro default (15)
  is strictly simpler and removes a boot-time failure mode, at no
  functional cost.

### Snapshot backups from day one
- Pros: matches the original spec plan (6.3), protects against data loss
  immediately.
- Cons: ongoing storage cost for data that, at this stage, isn't valuable
  enough to justify it.
- Rejected (for now) because: no real users/data yet; revisit once that
  changes.

## Consequences
- Local dev, CI, and production Postgres are now version-aligned (15) — a
  future decision to adopt a PG16-only feature would need to revisit this
  ADR, not just bump one environment's image tag.
- The issues database has **no backups** until a future decision explicitly
  adds them — a VM failure or operator error currently means real data
  loss risk once this holds real landlord data. Revisit before treating
  this deployment as anything but a personal/low-stakes tool.
- Adding a second Cloud Run-adjacent VM-hosted resource in future should
  follow the same pattern here (dedicated service account, custom VPC
  subnet, no default network) rather than reintroducing default-network
  exposure.
- `get_database_url()` (`services/issues_db.py`) and `resolve_api_key()`
  (`services/agent.py`) are now the same shape by design — see ADR-003 for
  why Langfuse's credential resolution deliberately differs from this
  pattern, so a future refactor doesn't accidentally "harmonize" all three
  into one shape.
