# Work Summary — 14 September 2026

Session goal: no code changes today. Purely exploratory/planning — figure out how the mobile
interaction pattern and ingress layer fit alongside a couple of general system-design topic
areas the user is looking to go deeper on in parallel (async processing & messaging; safety
and guardrails for agentic interaction), then work through the concrete architecture needed to
get a mobile message reaching the existing agent prototype end-to-end, landing on the next
prototype's scope.

## What was built

Nothing in this codebase — no files created or changed. This was a scoping/research session;
the output is this write-up plus the plan below for the next prototype slice.

## What was explored / learnt

### Topic pairing for the next prototype

Initially proposed pairing the mobile/ingress prototype with both "async processing &
messaging" and "serving & efficiency" (model-serving internals — batching, KV-cache,
quantization, GPU pools). User corrected this: serving & efficiency is irrelevant to an
ingress-layer prototype that calls an LLM API rather than hosting a model. Revised pairing,
agreed:
- **Async processing & messaging** — the ingress layer is the natural home for the
  sync-vs-async response decision (reply inline vs. ack-and-dispatch).
- **Safety & guardrails for agentic interaction** — the ingress point is where an untrusted
  mobile client hands input to an agent that can take real-world actions; input sanitization
  and action-scoping belong there.
Dropped "serving & efficiency" from this pairing as a mismatch.

### Messaging channel research (WhatsApp / Signal / Telegram)

Researched how each channel could be bound to a project identity rather than a personal phone
number:
- **WhatsApp Business Cloud API (Meta)**: needs a dedicated number never used for personal
  WhatsApp, a verified Meta Business account, and a Facebook Developer app. Meta's Cloud API
  is free-hosted with a free tier (1,000 conversations/month). For dev, Meta issues a **free
  test number** you allow-list your own phone against — no need to acquire a dedicated number
  until past prototype stage. Twilio is an alternative with a per-message markup for a more
  developer-friendly SDK.
- **Signal**: no official bot API. `signal-cli` (unofficial, JSON-RPC/REST interface) registered
  against its own dedicated/burner number. Most private option, weakest "official platform"
  story.
- **Telegram**: a bot has no phone number at all — created via `@BotFather` (`/newbot`), gets a
  username (e.g. `@HouseAgentBot`) and an API token. Zero number-provisioning friction, which
  is why it was chosen as the channel for the next prototype slice.
- Dead end / caveat: several search results came from SEO content sites riffing on
  agent-naming trends — treated as directionally useful but not authoritative; anything
  specific (ban-risk claims, rate limits) should be checked against Meta's/Telegram's own docs
  before relying on it.

### Multi-tenancy question (explicitly parked)

Confirmed a single Telegram bot serves any number of users out of the box — Telegram/WhatsApp
both hand every inbound message a unique sender id (`chat_id`/`wa_id`), so one ingress endpoint
already receives from all senders. The real multi-tenant work (identity/role resolution per
`chat_id`, data segregation, guardrails scoped per-identity) was explicitly deferred — user does
not want to build this yet, wants one landlord + one tenant set + one property working first.

### Local dev gap: Telegram can't reach `localhost`

Identified that a webhook-based channel needs a public URL — a laptop running the script has
none. Discussed **ngrok**/`cloudflared` tunnels as the standard local-dev bridge, then reasoned
through why to skip that entirely and deploy straight to Cloud Run instead (see Decisions).

### Cloud Run cost modelling for `min-instances=1`

Researched Cloud Run idle billing: in default mode (CPU allocated only during requests), an
idle `min-instances=1` is billed for **memory only**; `--no-cpu-throttling` bills idle CPU too
and is meaningfully more expensive. Rough estimate for a small (512MiB) always-warm instance in
default mode: **~$0–3/month** after the free tier (360,000 GiB-seconds/month free); the
`--no-cpu-throttling` equivalent runs closer to **~$11-12/month** based on real-world reports.
Confirmed `min-instances=1` is a legitimate way to get an always-warm endpoint cheaply, but
flagged that any resulting filesystem persistence would be incidental (wiped on redeploy/
instance replacement), not a real durability guarantee.

### Database hosting options research

Compared options for the eventual state DB (once the DB layer is added back), given the
existing `state_management_flow_prototype.py` schema is relational (SQLite: `issues`, `events`,
`issue_artifacts`, `contractors`, `issue_contractors`):
- **Cloud SQL (Postgres)**: near drop-in for the existing relational schema/SQL. Smallest
  shared-core tier (`db-f1-micro`) is always-on, ~$7–10/month regardless of traffic, not
  covered by Cloud SQL's SLA, not CUD-eligible.
- **Neon**: serverless Postgres, true scale-to-zero, usage-based billing (~$0.106–0.222/
  CU-hour), free tier of 100 CU-hours/month + 0.5GB storage — plausibly $0/month at this
  project's scale. Not a GCP product; connects over standard Postgres wire protocol.
- **Self-hosted Postgres on a free-tier GCP Compute Engine `e2-micro` VM**: genuinely $0/month
  if the VM is in `us-central1`, `us-east1`, or `us-west1` (Always Free eligibility is
  region-locked to these three). Initially framed by the model as "not worth the ops burden" —
  user pushed back given they're already maintaining the whole app themselves. Re-examined
  concretely:
  - Setup: create VM, `apt install postgresql`, connect from Cloud Run via **Direct VPC
    Egress** (the current native path — no separate Serverless VPC Access connector needed,
    which would otherwise add its own ~$8-10/month minimum).
  - OS patching: automate once via `unattended-upgrades` — converts to a one-time setup step,
    not recurring toil.
  - Backups: GCP Compute Engine snapshot schedules (a "resource policy" attached to the disk,
    set once via `gcloud`) or a simple `pg_dump | gsutil cp` cron job — both fire-and-forget
    after initial setup.
  - Real recurring cost: occasional major-version Postgres upgrades (minutes of work at this
    DB size), and the honest trade-off is **owning recovery time** if the VM dies (no vendor
    SLA/failover) — not vague "maintenance burden."

## Decisions and trade-offs

- **Decision:** Pair the mobile/ingress prototype with "async processing & messaging" and
  "safety & guardrails for agentic interaction," not "serving & efficiency." **Why:** serving &
  efficiency is model-serving-internals territory (KV-cache, batching, GPU pools), irrelevant
  to an ingress-layer prototype that calls an LLM API rather than hosting a model.
  **Trade-off:** none — serving & efficiency can be paired with a different future prototype
  (e.g. one that actually touches model-serving choices).
- **Decision:** Use Telegram as the channel for the next prototype, not WhatsApp or Signal.
  **Why:** zero phone-number/business-verification overhead — a bot is just a username + token.
  **Trade-off:** no end-to-end encryption by default (messages pass through Telegram's servers)
  — acceptable for house-maintenance chores, would need revisiting for anything sensitive.
- **Decision:** Skip ngrok/local tunneling; deploy the next prototype straight to Cloud Run.
  **Why:** ngrok is throwaway setup (URL changes on restart, needs re-registering the webhook)
  and briefly makes a personal laptop internet-facing; Cloud Run proves the actual production
  shape rather than a shape that gets rebuilt again later, and better matches the ingress/
  hosting learning goal. **Trade-off:** slower local iteration loop (deploy vs. save-and-rerun)
  — mitigated by keeping the toy agent runnable locally too.
- **Decision:** Use `min-instances=1` in Cloud Run's **default** billing mode (not
  `--no-cpu-throttling`) for the next prototype. **Why:** ~$0–3/month idle cost vs. ~$11-12/
  month for the always-CPU-allocated mode; no current need for background processing between
  requests that would require the latter. **Trade-off:** none identified yet — revisit if a
  future slice needs work to continue after the webhook response is sent.
- **Decision (working hypothesis, not yet built):** Self-host Postgres on a free-tier GCP
  Compute Engine `e2-micro` VM for the state DB, until scale demands otherwise; defer Cloud SQL
  and Neon. **Why:** genuinely $0/month at this project's scale, user is already carrying ops
  responsibility for the whole app so the setup (Direct VPC Egress, `unattended-upgrades`,
  snapshot schedules) is a reasonable one-time cost, and it doubles as deliberate infra
  learning. **Trade-off:** owns recovery time if the VM fails (no vendor SLA/failover) — an
  accepted risk for a single-landlord, no-external-uptime-commitment system. To revisit if/when
  scale or reliability requirements change.

## Blockers

None. Purely exploratory session, no implementation attempted.

## Next steps — the next prototype slice

Goal: prove the basic production interaction chain end-to-end in the smallest possible slice —
message on a phone → hosted agent → LLM → response back on the phone. No state DB, no
multi-turn agent loop, no tenancy: all deliberately deferred to keep this slice narrow.

**Components:**
1. **Telegram bot** — create via `@BotFather` (`/newbot`), get a bot token. No phone number,
   no business verification.
2. **`toy_house_agent.py`** (new, much smaller than `state_management_flow_prototype.py`):
   - One HTTP route (`/webhook`, Flask or FastAPI).
   - Parses the inbound Telegram `Update` payload → extracts message text.
   - Makes **one** LLM call reusing the cost-estimate web-search pattern already proven in
     `state_management_flow_prototype.py`'s `research_cost` tool — no tool loop, no `pause()`,
     no multi-round agent behaviour.
   - Sends the LLM's response back to the same `chat_id` via Telegram's `sendMessage` API.
   - No DB, no `issues`/`events`/`artifacts` tables — genuinely stateless per message.
3. **Hosting: Cloud Run** — containerize `toy_house_agent.py` (Dockerfile), deploy with
   `gcloud run deploy`, `min-instances=1` in default billing mode. One-time `setWebhook` call
   pointing Telegram at the Cloud Run service URL.
4. **Response delivery** — synchronous for this slice: handle the request, call the LLM, call
   `sendMessage`, return `200`. The ack-then-process/async pattern is deferred until latency
   from a single LLM call actually becomes a problem.

**Deliberately deferred (not in this slice):**
- Persistence / state DB (self-hosted Postgres on Compute Engine — the working hypothesis
  above, not built yet).
- Multi-turn agent loop, tools, contractor/quote flow (already exists in
  `state_management_flow_prototype.py`, not being ported yet).
- WhatsApp/Signal channels, multi-tenant identity mapping, guardrails beyond basic webhook
  authenticity checking.
- ngrok/local tunneling.

**Other items carried over from prior sessions (still open, unchanged this session):**
- Fake-tool-call gap with the `mercury` model (11 Sep) — not attempted.
- Exact-name contractor matching risk in `find_or_create_contractor()` — not attempted.
- Deferred paths: triage-only, needs-info, landlord `reject` re-entry.
- Real ingress classifier (inbound text → typed `events` row) as its own piece.
- Whether to move the loop model to `claude-sonnet-5`.
- Contractor-mutation tool design question (hand-predicted tools vs. more agent autonomy).
- Property-in-DB domain model (currently file-only).
- Mobile approval shape; eval + observability harness; OpenRouter `web` plugin inconsistency;
  real project `README.md`; `ARCHITECTURE.md` still a placeholder — increasingly overdue now
  that there's a state model, a deployment decision, a domain model, *and* an ingress
  architecture to describe.
- `prototypes/README.md` update noting the preferred-contractor flow (from 11 Sep) — still not
  done.
