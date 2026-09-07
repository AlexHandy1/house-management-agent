# Maintenance Agent — Slice 1 (Full Prototype)

**Status:** Spec for a throwaway prototype. Not production code. Built with a "real tool" mindset
so the system-design learning comes for free, but the code is expected to be rewritten.

**Parent design:** `docs/status_docs/LANDLORD_AI_AGENT_DESIGN_IDEAS_040926.md`

---

## 1. Purpose & core question

**Primary question this prototype answers:**
Is a single-agent ReAct loop with a forced-pause termination model the right execution spine for
maintenance issues, and can I evaluate its trajectories?

**Secondary goal:**
Start exercising how the loop fits the wider sketched architecture — reading/writing a state-store
DB, and sending drafted communications to a comms endpoint via a separate human-gated step.

**Explicitly not goals:** foundational/production code, a durable schema, channel adapters,
compliance/ledger domains, multi-turn resume.

---

## 2. Scope

### In

- A hand-rolled ReAct loop (Python, Anthropic SDK, native tool calling) that takes one
  plain-text maintenance issue and runs **one turn**.
- Real tools: web-backed cost research and contractor search; real draft generation.
- A minimal SQLite state store (durable agent memory) + a separate file-based JSONL trace.
- A local **comms stub** (tiny HTTP service that logs the payload and returns an ack).
- A manual `approve` step that triggers the only external send.
- Light evaluation: a trace pretty-printer + manual review first, then a handful of golden cases.

### Out (deferred)

- Multi-turn resume (tenant reply / rejection re-entering the loop).
- Approval-gate *policy* (auto vs. sign-off per action type) — in slice 1 everything needs manual approve.
- Idempotency machinery, prompt caching, crash recovery.
- Domain-state projection tables (Issue/Quote/Contractor as first-class rows).
- Photos / structured issue input.
- Multi-trade orchestration for a single issue.

---

## 3. The four paths

The loop is **not a fixed pipeline**. Paths are distinguished by *which artifacts get proposed*,
not by a stage counter. Branch *decisions* are in scope; only the multi-turn *resume* is deferred.

| Path | Trigger | Artifacts proposed | Terminal state |
|---|---|---|---|
| **A. Triage-only** | Trivial / tenant-actionable ("porch light bulb") | `draft_message` (guidance reply to tenant) | `AWAITING_LANDLORD_APPROVAL` |
| **B. Needs info** | Too vague to ground an estimate ("tap making a noise") | `draft_message` (clarifying question to tenant) | `AWAITING_TENANT_INFO` — dead-ends in slice 1 |
| **C. Known contractors** | Clear issue + ≥2 whitelisted contractors for the trade | `propose_cost_estimate` + `draft_message` ×N (quote requests to whitelist) | `AWAITING_LANDLORD_APPROVAL` |
| **D. Full path** | Clear issue + fewer than 2 whitelisted contractors for the trade | `propose_cost_estimate` + `shortlist_contractor` ×N + `draft_message` ×N | `AWAITING_LANDLORD_APPROVAL` |

Notes:

- **No immediate `RESOLVED_NO_ACTION_NEEDED`.** Even a trivial issue is triaged to *some* response.
- The whitelist decision is the **agent's**, informed by a read tool — not deterministic pre-routing.
  Rule of thumb it applies: ≥2 whitelisted contractors for the trade → use them (Path C); fewer → search to top up (Path D).
- Path D is the deliberately **held-out** path — it is not shown in the few-shot examples (see §8),
  so path selection into it tests generalisation.

---

## 4. Tool set

Split follows the parent design's read / propose discipline.

### Read tools (no writes to our system; callable freely during reasoning)

| Tool | Behaviour |
|---|---|
| `get_preferred_contractors(trade, area?)` | Returns approved contractors from the state store whitelist. |
| `research_cost(issue_summary)` | Makes its own web-search-backed model sub-call; returns raw findings (price points, sources). **Not** the committed estimate. |
| `find_contractors(trade, area, exclude?)` | Web-search-backed sub-call; returns 3–5 candidate contractors (name, trade, contact, source URL). |

### Propose tools (write a durable artifact to our state store; no external side effect)

| Tool | Writes |
|---|---|
| `propose_cost_estimate(low, high, currency, basis)` | `issue_artifacts` row, kind `cost_estimate`. |
| `shortlist_contractor(contractor_ref, rank, reason)` | `issue_artifacts` row, kind `shortlist_entry`. Path D only. |
| `draft_message(recipient_type, recipient_ref, body)` | `issue_artifacts` row, kind `draft_message`. `recipient_type ∈ {tenant, contractor}`. |

### Control

| Tool | Behaviour |
|---|---|
| `pause(reason)` | Ends the turn. `reason ∈ {AWAITING_TENANT_INFO, AWAITING_LANDLORD_APPROVAL, NEEDS_HUMAN_REVIEW}`. Writes the terminal step and updates `issues.status`. |

### Write powers — precise statement

- **No agent tool causes an external or irreversible side effect.**
- Propose tools and `pause` write only to our own state store (append artifacts / update status) — internal, durable, reversible.
- Read tools persist nothing.
- The single external side effect in slice 1 — POSTing an approved draft to the comms stub — is performed by the **`approve` CLI command**, a human action outside the loop. It is not an agent tool.
- There is no agent-facing `write_events` tool. The **runner** owns the trace and the per-turn ledger.

**Decomposition note:** the originally-envisaged `get_cost_estimate` is deliberately split into
`research_cost` (read) + `propose_cost_estimate` (propose) to preserve the read/propose split, give
more observable loop iterations, and let evals score "was the research useful" separately from
"given that research, was the range sane".

---

## 5. Loop control & termination

- **Forced termination (Option 1).** A turn ends *only* by calling `pause(reason)`. If the model
  returns no tool call, the runner injects an observation ("you must call a tool or pause") and re-prompts.
  This gives the outer event-driven system an unambiguous typed "what wakes this issue next" signal,
  and makes the termination decision a first-class, gradable step.
- **Iteration cap = 30 tool-call rounds per turn.** Generous on purpose — watch traces before tuning.
  On hit: the runner stops, writes a synthetic `forced_termination` step (distinct from an agent
  `pause`), and sets terminal state `NEEDS_HUMAN_REVIEW`. No auto-retry.
- **Count everything toward the cap:** read calls, propose calls, malformed calls, re-prompts. One counter, no exemptions.
- **No other guards in slice 1.** The stall / duplicate-call / malformed-strike / pause-precondition
  guards are parked (see §12) — deliberately, so the messier failure modes show up in traces first.

---

## 6. Invariants (drive the prompt and eval "Layer 5")

1. **Never send.** The loop only writes `draft_message` artifacts; nothing reaches the comms stub except via the separate `approve` command.
2. **Never fabricate an under-informed estimate.** If the issue is too vague to ground a cost range, the agent must pause `AWAITING_TENANT_INFO` with a clarifying question — not guess.
3. **Always triage to a response.** No path ends without at least one proposed artifact directed at someone (tenant or contractor). "Do nothing" is not a valid outcome.
4. **No external side effect from the agent.** The agent has no tool that sends, books, or pays; read tools read the web but persist nothing.
5. **Terminate cleanly.** Every turn ends in `pause(reason)` or the runner's `forced_termination` — never an unterminated transcript.

---

## 7. Persistence model

Two distinct concerns, kept separate (do **not** conflate observability with agent memory):

| Concern | Holds | Read back into a prompt? |
|---|---|---|
| **Durable agent memory** (SQLite state store) | Compact salient facts + committed artifacts per issue | **Yes** — rendered as history every turn |
| **Observability trace** (JSONL files) | Every LLM call, tool call, args, raw result, re-prompts, malformed calls, tokens, latency | **Never** |

The within-turn ReAct scratchpad lives in the LLM context for that turn and is flushed to the trace
afterwards; it is not separately persisted for the agent's sake (a crashed turn is re-run from the
last durable artifact state).

### Static config / fixtures (seeded before a run)

```
property.yaml:
  locality: "Levenshulme"
  city: "Manchester"
  postcode: "M19 ..."
  country: "UK"
  notes: "<free text: boiler type, access notes, etc.>"
  tenancy: { tenant_name: "...", tenant_contact: "..." }   # single tenancy
```

Property + tenancy are **injected into the system prompt** as static grounding (no tool). The real-system
form would be a `get_property_profile()` read tool backed by the state store; prototype keeps it simple.

`contractors` seed (YAML → `contractors` table): approved / trusted contractors only, no reliability
flags, spanning 2–3 trades so Paths C and D are both exercisable.

### State store (SQLite)

```
issues(id, source_text, status, created_at)
  -- status: OPEN | AWAITING_TENANT_INFO | AWAITING_LANDLORD_APPROVAL | NEEDS_HUMAN_REVIEW
  -- denormalized current status, updated only on the terminal step

issue_artifacts(id, issue_id, seq, kind, data_json, created_at)
  -- kind ∈ cost_estimate | shortlist_entry | draft_message
  --       | tenant_info_request | tenant_info_response | note | sent

issue_turns(id, issue_id, turn_no, trigger, terminal_state, step_count, started_at, ended_at)
  -- compact per-turn ledger, no step detail
  -- trigger: issue_created (only reachable value in slice 1; tenant_reply deferred)

contractors(id, name, trade, area, contact, approved_at)   -- whitelist fixture
```

Next-turn agent context = property/tenancy config + `issues.source_text` + ordered `issue_artifacts`
(+ on a future resume, the new trigger event). Bounded and small — O(handful) per issue.

### Trace

`traces/{issue_id}/turn_{n}.jsonl`, one line per step (tool, args, result, error, tokens, latency),
written by the runner. Consumed by the pretty-printer and the eval harness. Never loaded into a prompt.

### Trade vocabulary

Controlled list, in the prompt; agent classifies the issue into one and passes it as the `trade` arg:

```
plumbing, electrical, heating_gas, roofing, glazing, carpentry, handyman, appliance_repair
```

Primary trade only — no multi-trade handling for one issue (known limitation). No `classify_trade`
tool; the agent just reasons and passes the arg (revisit if classification proves unreliable).

---

## 8. System prompt approach

**Option (c): middle.** The prompt provides:

- role / goal / property + tenancy grounding
- the tool set
- the terminal states and their preconditions
- the hard invariants (§6)
- **2–3 few-shot example trajectories** spanning Triage / Needs-info / Known-contractors — framed as
  illustrations, not an if/then decision tree. Path D is **not** shown (held-out).

Rationale: the evals then test real path-selection judgment (the core question) while few-shot keeps
the loop from being wildly unreliable. If path selection proves too noisy, tighten toward an explicit
decision tree — and record "the loop needed explicit branch guidance to be reliable" as a finding,
since that itself answers the core question. May also experiment toward option (b) (principles only).

---

## 9. Evaluation approach

**Start very light.** Manual trace review is the first and main source of value.

### Build order

1. **Trace pretty-printer** — JSONL → readable turn transcript. Everything else depends on cheap human review.
2. **Error taxonomy note** — started during the first trace reviews, grown over time.
3. **A handful of golden cases** (later, once behaviour has been observed) — spanning the four paths,
   plus 2–3 counterfactual pairs (toggle whitelist → path must switch C↔D; add/remove detail → B↔D),
   plus 1–2 adversarial invariant cases (under-specified issue; injection-like text in the report).
   Each golden case: `{issue text, seeded property + whitelist, recorded tool outputs, expected path
   assertions, expected terminal state, cost band, message checklist}`.

### The evaluation layers (reference — not all built in slice 1)

| Layer | Question | In slice 1? |
|---|---|---|
| 0. Component / tool unit | Do the tools parse/return valid structures? | Yes — plain unit tests |
| 1. Single-step decision | Given a frozen context, is the next action right? | Deferred |
| 2. Trajectory / path | Is the sequence sound — right branch, no wasted calls, correct stop? | **Yes — primary** (assertions on ordered tool names + terminal state) |
| 3. Outcome / artifact | Are the deliverables usable (cost sane, message complete, right question)? | Structure asserts yes; **quality judge advisory-only** |
| 4. End-to-end task success | Right terminal state + artifacts, judged holistically | Deferred |
| 5. System invariants / safety | Are the never-rules never violated? | **Yes — hard pass/fail** |
| 6. Regression | Did a prompt/model/tool change move any of the above? | Informal (re-run golden cases) |

### Techniques chosen

- **Assertion-graded trajectory checks** (Layer 2) — primary.
- **Counterfactual / perturbation pairs** — highest value-per-effort for the branch logic.
- **Rubric-as-binary-checklist LLM judge** for the quote-request message and the clarifying
  question (e.g. `[names the fault] [names property locality] [requests a quote] [gives a contact
  route] [professional tone] [no fabricated details]`) — output treated as **advisory** in slice 1.
- **Reference-band check for cost** — human sets a plausible low/high band per golden issue;
  assert the agent's range overlaps and width is within tolerance. No judge model needed.
- **Non-determinism**: run each golden case N≈5 times, report pass rate / distribution, threshold
  (e.g. path correct ≥4/5) rather than single pass/fail.

### Reproducibility — two suites (when golden cases exist)

- **Replay suite** (fast, deterministic, workhorse): tool dispatcher returns **recorded fixtures**
  instead of hitting the web; isolates the reasoning loop; gates changes.
- **Live suite** (slow, tolerant, on demand): real tools; loosened assertions (path + structure +
  judge + cost band); flakiness expected — read the trace, not just pass/fail.

### Deferred eval work

Single-step decision harness (Layer 1), automated trajectory-critique judge, full
validate-the-validator statistics, task-success labelling (Layer 4).

---

## 10. Runner / entry point

**Start simpler than the full CLI:** a single script that runs the loop on one example issue and
writes the trace + artifacts for review. Exact shape TBD at build time.

**Target CLI for the fuller prototype** (not all needed on day one):

| Command | Does |
|---|---|
| `init-db` / `reset` | Create/clear SQLite; seed property + tenancy + contractor whitelist |
| `run-issue --text "..." [--id X]` | Create issue, run one turn, persist artifacts + turn ledger + JSONL trace, print terminal state + summary |
| `approve <id>` | Flip status, POST approved drafts to the comms stub, record `sent` artifacts |
| `reject <id> "<note>"` | Record rejection, re-open (resume deferred) |
| `show <id>` | Pretty-print artifacts + turn ledger |
| `trace <id> [turn]` | Pretty-print the JSONL trace |

One turn per invocation — no daemon, no queue. `--resume-with-reply` exists in name only (deferred).
Config: `property.yaml`, contractor seed YAML, `.env` for the API key, model ID in a constants
module, DB path in config.

---

## 11. Tech choices

- **Python, framework-free.** Hand-rolled loop: call model → parse tool call → dispatch → append
  observation → repeat → until `pause` or cap. No LangChain/LangGraph. (May trial other frameworks
  later purely for comparison.)
- **Anthropic SDK, native tool calling** (`tool_use` / `tool_result` blocks) — not text-parsed ReAct.
- **Model: `claude-sonnet-5`** for the loop, held in one config constant for easy swapping.
- **Web search: Anthropic server-side `web_search`**, used *inside* `research_cost` and
  `find_contractors` (each makes its own search-enabled sub-call). No separate search API.
- Confirm current model IDs / web-search tool shape / pricing via the `claude-api` skill at build time.

---

## 12. Cost & latency ballpark (sanity-check only — no caps in the prototype)

Path D (the expensive path), rough:

- Static prefix ~2–3k tokens (re-sent each round — no caching in slice 1); history grows to
  ~4–6k input tokens/round; ~11–13 rounds; ~300–600 output tokens/round.
- Plus 2 web-search sub-calls, ~3–8k tokens each.
- **~60–100k input + ~5–8k output tokens per full turn → roughly $0.25–0.40 per full issue.**
  Triage / needs-info paths ≈ $0.02–0.05.
- Latency ~15–40s, dominated by the web-search sub-calls.

Log token/cost per turn for review. No anomaly flags or caps for the prototype.

---

## 13. Design notes — alternatives parked

Decisions made for the prototype that may change for the real architecture:

- **Termination model — dedicated terminal tools (Option 3).** Instead of one overloaded
  `pause(reason)`, have `await_tenant_info(msg)`, `submit_for_approval()`, `escalate(reason)`.
  Same typed-signal benefit; each terminal tool enforces its own preconditions naturally; reads
  clearly in a trace. **Flagged as a likely better fit for the ultimate architecture** — adopt if
  a single overloaded `pause` gets misused. Prototype uses Option 1 for simplicity.
- **Loop guards** — stall / no-progress guard, duplicate-call guard, malformed-call 3-strike,
  `pause` precondition validation. All parked until traces show which failures actually occur.
- **Eval layers 1, 4, 6** — single-step decision harness, task-success labelling, formal regression
  baseline. Parked.
- **Domain-state projection tables** (Issue / CostEstimate / Quote / Contractor / Shortlist /
  DraftMessage as first-class rows, per the parent design's data-model sketch). The append-only
  `issue_artifacts` log is the state store for now; building the projection is a later slice.
- **Multi-turn resume** — tenant reply / rejection re-entering the loop as a new turn with reloaded
  history. The clarification sub-loop depends on this. Deferred.
- **Approval-gate policy** — which proposed action types auto-proceed vs. need sign-off. Slice 1
  requires manual `approve` for everything.
- **Idempotency & prompt caching** — deferred. Two cheap forward-compatible concessions kept:
  stable issue IDs from creation, and an idempotency key (`issue_id` + draft `seq`) on the
  comms-stub POST that the stub dedupes on.
- **`get_property_profile()` read tool** — the real-system form of property grounding; prototype
  injects `property.yaml` into the system prompt instead.
- **Dedicated search API** (Brave / Tavily) instead of Anthropic `web_search` — swap is local to
  the two research tools if needed.

---

## 14. Open questions

- Few-shot example count and exact content for the prompt (2 vs 3; which paths).
- JSONL trace line schema — settle when the pretty-printer is built.
- Whether the agent needs an explicit trade-classification step or free reasoning suffices
  (start free; revisit on evidence).
- How noisy Path-D path-selection is without a few-shot example for it — informs whether the
  prompt moves toward option (a) or (b).
- Comms-stub payload shape (what a "sent message" record needs to carry).
