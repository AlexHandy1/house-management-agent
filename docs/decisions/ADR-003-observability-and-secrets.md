# ADR-003: Observability (Langfuse) and secrets management

## Status
Accepted

## Date
2026-09-23

## Context
The agent loop calls an LLM via OpenRouter and needs tracing to be
debuggable/reviewable in production, plus a testing/evals story that
doesn't run real LLM calls (cost, non-determinism) on every CI run.
`nature-quest` used PostHog for this; this project's prototyping phase had
already proven out Langfuse instead (`docs/status_docs/WORK_SUMMARY_180926.md`),
so this is a deliberate divergence from the nature-quest precedent, not a
gap.

Both the OpenRouter and Langfuse SDKs need runtime credentials in
production. They turned out to need different resolution strategies, which
is itself worth recording so a future change doesn't accidentally
"harmonize" them into a shared pattern that breaks one of them.

## Decision
- **Observability**: Langfuse, wrapping the agent's single LLM call in a
  `generation` observation (`services/agent.py`). Pytest's `eval` marker
  (mirroring `nature-quest`'s pattern) excludes real-LLM-calling tests from
  the default `pytest` run; only `pytest -m eval` hits the live model, and
  CI never runs that marker.
- **Secrets in production**: GCP Secret Manager, fetched explicitly in
  application code (not Cloud Run's native `secret_key_ref` env injection)
  — same rationale as nature-quest's ADR-006: reduces accidental-leak risk
  specific to an open-source project with unknown future contributors.
  Secret *values* are set out-of-band (`gcloud secrets versions add`),
  never in Terraform config.
- **Credential resolution timing differs deliberately between the two
  SDKs**:
  - OpenRouter (`services/agent.py`'s `build_client()`): resolves the key
    fresh on every call, passed explicitly as `OpenAI(api_key=...)`. Safe
    to do lazily per-request because there's no shared/global state — each
    call constructs an independent client.
  - Langfuse (`services/langfuse_config.py`'s `configure()`): resolves
    credentials **once, at process startup**, before anything calls
    `langfuse.get_client()`. Langfuse's `get_client()` is a singleton
    factory keyed by public key — the *first* call in the process reads
    `os.environ` and caches the resulting client for the process's
    lifetime; later calls (even with different arguments) reuse that
    cached instance. Resolving lazily per-request, as OpenRouter does,
    would either be silently ignored (same key) or leak a new background
    batching thread/queue per call (different key) — confirmed via the
    SDK's own source and Langfuse's documented best practice
    ("initialize once at startup, reuse via `get_client()`").
  - A Secret Manager failure while resolving Langfuse's credentials must
    never crash app startup — Langfuse is an observability sidecar, not
    required for the app's core function. On failure it logs a warning and
    leaves tracing disabled (Langfuse's own client degrades to a no-op
    state) rather than propagating the exception.
- **Test isolation**: unit tests get fake Langfuse/OpenRouter credentials
  by default (`tests/conftest.py`), so an accidentally-unmocked code path
  in an ordinary `pytest` run can't send real trace data to the production
  Langfuse project — only the explicit eval test path uses real
  credentials.

## Alternatives Considered

### Resolving Langfuse credentials lazily per-request, matching OpenRouter's pattern
- Pros: one consistent pattern across both SDKs, simpler to explain.
- Cons: doesn't actually work correctly for Langfuse — its client is a
  process-wide singleton, so per-call resolution either does nothing (same
  key, cached instance reused, new arguments ignored) or leaks a new
  background thread/queue per distinct key.
- Rejected because: verified directly against the SDK's own source and
  documented guidance; the two SDKs have genuinely different
  initialization semantics, and forcing a shared pattern would silently
  misconfigure one of them.

### Cloud Run's native `secret_key_ref` (automatic secret-to-env-var injection)
- Pros: simpler — no application code needed to fetch secrets.
- Cons: an env var is more exposed to accidental leakage (crash dumps,
  debug logs, error pages) than a value the app fetches once and holds in
  memory — a meaningfully worse trade-off specifically for a public,
  open-source codebase.
- Rejected because: same reasoning as `nature-quest`'s ADR-006, which this
  project deliberately continues rather than re-litigates.

## Consequences
- Two different credential-resolution code shapes exist side by side
  (`agent.py`'s per-call `resolve_api_key()` vs `langfuse_config.py`'s
  startup-once `configure()`) — this is intentional, not inconsistent; see
  Decision above before "fixing" it to look uniform.
- `langfuse_config.configure()` must be called before `create_app()`/any
  request handling — currently done at `main.py` module level, immediately
  after `load_dotenv()`. Moving it later (e.g. into a request handler)
  would reintroduce the race this ADR exists to avoid.
- Adding a third LLM-adjacent SDK in future should default to Langfuse's
  pattern (verify its own client lifecycle before assuming OpenRouter's
  per-call pattern is safe to copy).
