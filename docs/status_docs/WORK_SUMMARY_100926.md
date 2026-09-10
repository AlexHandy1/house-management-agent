# Work Summary — 10 September 2026

Session goal: the parked "port the HITL loop to LangChain/LangGraph" item from 09 Sep —
build both ports side by side, work out what (if anything) the frameworks buy us, and
sense-check how prompt caching would be done under each option.

## What was built

- **`prototypes/happy_path_contractor_message_hitl_langchain_prototype.py`** — LangChain
  1.x `create_agent` port of `happy_path_contractor_message_hitl_prototype.py`. Same 5
  tools, same model (`inception/mercury-2.5` via OpenRouter through `ChatOpenAI` with a
  `base_url` override), same "`request_approval` and `send_message` are separate, nothing
  enforces the outcome" design. Every model-facing string (system prompt, user message,
  the 3 sub-call prompts, 5 tool descriptions, 2 message-arg descriptions, tool-result
  strings) copied **verbatim** into clearly-marked constants (`SYSTEM_PROMPT_TEMPLATE`,
  `*_PROMPT`, `*_DESC`, `*_RESULT`). HITL via langgraph's `interrupt()` + `InMemorySaver`
  checkpointer + `Command(resume=...)`. `@tool(description=..., args_schema=...)` used to
  stop LangChain reformatting docstrings / dropping param descriptions. Contains a
  temporary `_invoke_text()` instrumentation helper on the sub-calls.
- **`prototypes/happy_path_contractor_message_hitl_langgraph_prototype.py`** — explicit
  `StateGraph` port: `call_model` node + `ToolNode` + one conditional edge, `InMemorySaver`,
  same `interrupt()` HITL, same verbatim string constants. Fully self-contained (no imports
  from the other prototype variants, per existing project convention).
- **`prototypes/requirements.txt`** — added `langchain`, `langchain-openai`, `langgraph`.
  Installed into `prototypes/.venv`: langchain 1.4.0, langchain-core 1.6.2,
  langchain-openai 1.6.2, langgraph 1.2.11, langgraph-prebuilt 1.1.0.
- Both new scripts run end-to-end successfully after the `max_tokens` fix below.

## What was explored / learnt

### Truncation bug (latent in every prototype, surfaced by the LangChain run)

First LangChain run: `research_cost` and `draft_message` sub-calls returned empty
`.content`; the tools handed back their fallback strings; the agent produced a final
answer with no cost estimate and never reached `request_approval` / `send_message`.

Instrumentation (`_invoke_text`) showed the cause: `max_tokens` is a **combined budget for
reasoning tokens + visible content**. `inception/mercury-2.5` emits reasoning tokens; on
these calls it spent the *entire* budget on reasoning —
`output_tokens: 1923, output_token_details: {reasoning: 1923}`, `finish_reason='length'` —
and got cut off before writing any `content`. `find_contractors` (identical code path)
only "worked" because that run's reasoning happened to fit.

- Not a LangChain-specific bug: the raw-SDK originals use the same model and the same
  `max_tokens` (2000 / 1000) and carry the identical latent risk. It just hadn't triggered
  on the one prior run of the original.
- **Fix applied (new prototypes only):** `research_cost` / `find_contractors`
  `max_tokens` 2000 → **6000**; `draft_message` 1000 → **4000**. Main ReAct-loop model
  left at 4000. Raising the cap costs nothing unless the tokens are actually generated.
- Raw-SDK originals (`happy_path_contractor_message_hitl_prototype.py`,
  `happy_path_contractor_message_prototype.py`, `cost_estimate_*`) left unchanged — user's
  call to keep the change scoped.

### Reasoning token pricing (answers an open question from 09 Sep)

OpenRouter docs: *"Reasoning tokens are considered output tokens and charged
accordingly."* No separate price tier — billed at the model's normal **output** rate, and
they show up as `native_tokens_reasoning` (a subset of completion tokens) on the
generation detail. `reasoning.exclude: true` hides them from the response but **still
charges** — the model still generates them. So last session's "are output tokens driving
the higher-than-expected cost" → **yes, reasoning tokens are** (~1900 billed output tokens
on a simple cost lookup).

Fine-grained reasoning controls don't reliably apply to mercury: `reasoning.effort` is
OpenAI/Grok only, `reasoning.max_tokens` is Gemini/Anthropic/Qwen only. For mercury the
only reliable lever is the overall `max_tokens`.

### OpenRouter "cache hit" metric

Provider-side prompt (prefix) caching: reuse of the computed state for an identical
leading chunk of a request. Automatic for OpenAI / DeepSeek / Z.AI-GLM / Gemini 2.5 /
Grok / Groq / Moonshot; **explicit `cache_control` required** for Anthropic / Qwen.

- The **3.7% cache-hit figure on the mercury model page is a marketplace-wide aggregate**
  across all OpenRouter traffic to that model, not our account.
- Our own runs showed `cache_read: 0` / `cache_creation: 0` on every call — we get zero
  cache hits today.

### Why we saw limited caching benefit even on auto-caching models (OpenAI / GLM)

Caching applies **only to the ReAct loop's own model calls** (the `messages` list re-sent
and growing each round: system prompt + issue + accumulated tool results). It does **not**
apply to the three one-shot LLM calls made *inside* the tools (`research_cost`,
`find_contractors`, `draft_message`) — each is a standalone call with a unique single
prompt, run once, no shared prefix.

Even on the loop calls the benefit is small here because:
1. **Short horizon** — the happy path converges in ~2–4 rounds; caching only helps from
   round 2 on, so 1–3 partial cache reads at most.
2. **Prefix grows late** — round 1 is below the provider threshold (OpenAI caches only
   >1024 tokens); the prefix isn't bulky until a couple of big tool results have landed,
   by which point the loop is nearly done.
3. **Cost is output/reasoning-dominated** — cache discounts apply to *input* tokens only;
   the long research dumps + per-call reasoning are regenerated fresh every time at output
   price.
4. **In-tool sub-calls are uncacheable by construction** and are a large share of spend.
5. **Cross-run TTL expiry** — cache TTLs are ~5 min; prototype runs minutes apart pay full
   price for their early calls anyway.

Caching becomes worthwhile only when the loop is long (many rounds re-sending a large
stable prefix) — not at this stage of the design.

### Dead end

Started a `_check_prompt_parity.py` AST-diff harness to prove the copied strings matched
the original byte-for-byte — rejected as over-engineered. Parity is instead held by
copying the strings into constants under a "copied verbatim — do not edit here" comment in
each file.

## Framework comparison (explicit)

### What the frameworks replaced vs the hand-rolled prototype (~335 lines, raw `openai`)

| Hand-rolled | `create_agent` (LangChain) |
|---|---|
| The whole `run()` while-loop: rounds, `MAX_ROUNDS`, appending the assistant message with `tool_calls`, appending tool results, checking `finish_reason` | one `create_agent(...)` + `.stream()` |
| `TOOLS` list of hand-written JSON-schema dicts | `@tool` on a function (we passed explicit `description=` only to hold prompt parity) |
| `json.loads(arguments_json)`, `.get("message","")`, the `TOOL_FUNCTIONS` / `MESSAGE_ARG_TOOLS` dispatch dicts, `call_tool()` | gone — `ToolNode` parses args, validates against schema, calls, formats the `ToolMessage` |
| `request_approval` blocks on `input()` on the main thread; cannot pause and resume | `interrupt()` + checkpointer: run state is persisted, resumable later, even in another process |
| parallel tool calls executed sequentially in a Python `for` loop | same, for free |

`StateGraph` (LangGraph): we wrote ~15 lines (`call_model`, `route`, node/edge wiring) —
less than the hand-rolled loop, more than `create_agent`, every control point explicit.
For the current **single ReAct loop it buys nothing over `create_agent`**. It earns its
place only when the flow stops being "model ↔ tools": a dedicated approval node,
branching, external-state read/write nodes, parallel sub-agent fan-out, retry sub-loops.

### Middleware not used but relevant to problems already on the list

- `SummarizationMiddleware` — auto-compact history as it grows (cost variance).
- `ModelFallbackMiddleware` — fall back to another model on error (mercury flakiness).
- `HumanInTheLoopMiddleware` — `interrupt_on={"send_message": True}`; would delete
  `request_approval` entirely.
- `ModelCallLimitMiddleware`, streaming, structured output, LangSmith tracing.

### Costs / downsides observed

- **Quieter failures.** The truncation bug gave an empty `.content` with no signal; needed
  `_invoke_text` to pull `finish_reason` / `response_metadata` out. The raw client exposes
  `finish_reason` directly on the response.
- `.content` can silently become a list of content blocks depending on model/provider — a
  failure mode the raw client doesn't have.
- Had to fight the abstraction (explicit `description=` + Pydantic `args_schema`) to keep
  the model-facing tool schema identical to the original.
- Dependency weight: `langchain` + `langchain-core` + `langchain-openai` + `langgraph` +
  pydantic vs just `openai`. Young 1.x API (`AgentExecutor` moved to `langchain-classic`).

### Verdict

- **`create_agent`: adopt when the HITL step goes async** (mobile / server approval —
  next-step #3 from 09 Sep). It deletes the loop + arg parsing + dispatch tables, and the
  interrupt/checkpoint HITL is a real capability the hand-rolled version lacks. Not urgent
  while approval is a terminal `input()`.
- **LangGraph: not yet.** Adopt when the flow needs branching / external-state nodes /
  parallel sub-agents (contractors DB — next-step #2 from 09 Sep).
- Strongest single argument for LangChain here: the middleware catalogue maps directly
  onto cost variance and model flakiness, both already logged.

## Prompt caching — how each option would implement it

Applies only to the ReAct loop's own calls (growing stable prefix), **not** the 3
one-shot in-tool sub-calls. And it only pays off if the loop model moves off mercury
(observed `cache_read: 0`) to an auto-caching family or Claude.

| | Auto-caching model (GPT / DeepSeek / GLM / Gemini 2.5) | Claude family |
|---|---|---|
| **Vanilla OpenRouter** (raw `openai`) | Nothing to write. Happens on the wire above the provider threshold; read `usage.prompt_tokens_details.cached_tokens` / `cache_discount` to confirm. | Manual: rebuild `messages` with list-of-blocks content, put `{"cache_control":{"type":"ephemeral"}}` on the system block + the last stable block, advance the breakpoint each round (max 4). |
| **LangChain** (`create_agent`) | Same as vanilla — free, on the wire. | Cleanest: `AnthropicPromptCachingMiddleware()` in `middleware=[...]`, or `model.invoke(msgs, cache_control={"type":"ephemeral"})` (auto-advances the breakpoint). Caveat: these are `ChatAnthropic` features — point `ChatAnthropic` at OpenRouter's `base_url`, not `ChatOpenAI`. Stay on `ChatOpenAI`→OpenRouter for a Claude id and you're back to hand-injecting blocks via `extra_body`. |
| **LangGraph** (`StateGraph`) | Same as vanilla — same model object inside `call_model`. Free. | Same `cache_control=` on the `model.invoke()` inside `call_model`, or `create_agent`+middleware as a subgraph. Extra lever: a node that freezes old tool results into one stable block so the cacheable prefix stays contiguous. |

**Bottom line:** auto-caching loop model → all three identical, zero caching code, verify
via `usage` fields. Claude loop model → LangChain's middleware is meaningfully less code
than the vanilla breakpoint bookkeeping — the one concrete cost win in the framework
column. Neither matters until the loop moves off mercury and gets longer.

## Decisions and trade-offs

- **Decision:** Both frameworks, side by side, as separate self-contained prototype files;
  full 5-tool HITL path; identical model. **Why:** the framework is then the only variable
  in the comparison. **Trade-off:** two more files to keep in sync with the original and
  each other (same trade-off already accepted for the cost-estimate / OpenRouter pair).
- **Decision:** Copy every model-facing string verbatim into named constants rather than
  rely on docstrings / `@tool` defaults. **Why:** LangChain reformats docstrings (via
  `cleandoc`) and drops parameter descriptions → the model-facing tool schema would drift
  from the original, which the user explicitly ruled out. **Trade-off:** more boilerplate
  per tool (`description=`, Pydantic `args_schema`).
- **Decision:** Fix the truncation by raising `max_tokens`, not by disabling reasoning
  (`reasoning.enabled: false`). **Why:** we want the model to reason; the fix is headroom,
  not removal, and a higher cap costs nothing unless used. **Trade-off:** high-variance
  reasoning length could still occasionally clip at 6000 — no hard guarantee.
- **Decision:** Apply the cap fix to the two new prototypes only; leave the raw-SDK
  originals untouched. **Why:** user's call to keep the change scoped. **Trade-off:** the
  originals keep the latent truncation risk.
- **Decision:** Keep `request_approval` as a model-callable tool implemented via
  `interrupt()`, not LangChain's `HumanInTheLoopMiddleware` gate. **Why:** faithful port of
  the original's deliberate "separate ask + send, nothing enforces the outcome" design.
  **Trade-off:** doesn't exercise the middleware path; recorded as the idiomatic
  alternative.
- **Decision:** Dropped the `_check_prompt_parity.py` AST harness. **Why:** over-engineered
  for the need. **Trade-off:** parity now rests on the "do not edit here" comment
  discipline, not an automated check.

## Blockers

None blocking. Note: `_invoke_text()` in the LangChain prototype is temporary (marked
`TEMP`) — decide whether to keep a trimmed version or remove it. The LangGraph prototype
does not have the equivalent instrumentation.

## Next steps

1. Decide whether to adopt `create_agent` for the real build. Trigger is the async HITL
   step (mobile / server approval, 09 Sep next-step #3). LangGraph deferred until the flow
   branches (contractors DB / external state, 09 Sep next-step #2).
2. If keeping the frameworks: fold in `SummarizationMiddleware` and
   `ModelFallbackMiddleware` to address cost variance and mercury flakiness.
3. Apply the `max_tokens` truncation fix to the raw-SDK originals
   (`happy_path_contractor_message_hitl_prototype.py`,
   `happy_path_contractor_message_prototype.py`, `cost_estimate_*`) if they stay in use.
4. Prompt caching: not worth implementing at current loop length; revisit if/when the loop
   model moves off mercury and the round count grows. If moving to Claude, LangChain
   middleware is the cleanest path.
5. Commit the two new prototypes and the `requirements.txt` change (currently untracked);
   update `prototypes/README.md` to list the two new files.
6. Carried from 09 Sep, still open: contractors DB / external state; mobile approval shape;
   eval + observability harness; OpenRouter `web` plugin firing inconsistently across
   models; create a real project `README.md` and update `ARCHITECTURE.md`.

---

# Session 2 — 10 September 2026 (evening)

Distinct piece of work from the LangChain/LangGraph session above. Goal: pick a production
deployment model, then build a prototype that exercises it against a two-flow scenario —
(A) new issue → cost estimate → contractors → drafted quote → landlord approval → send
quote requests; (B) contractor replies with a quote → interpret it → compare to the stored
estimate → advise the landlord.

## What was built

- **`prototypes/state_management_flow_prototype.py`** — a cold-start-per-turn agent over a
  durable SQLite state DB. One CLI invocation = one "turn": wake on an event, rebuild the
  message list purely from DB rows (the issue's `events` log + `issue_artifacts` +
  `contractors`), run a hand-rolled ReAct loop, call `pause(reason)`, exit. Raw `openai`
  client via OpenRouter, `inception/mercury-2.5`, `MAX_ROUNDS=20`.
  - **One system prompt, one tool set** — `research_cost()`, `find_contractors(trade, area)`,
    `record_contractor(...)` (writes the `contractors` table), `write_artifact(kind, data)`
    (single generic durable-write tool — agent picks the kind: `cost_estimate`,
    `draft_message`, `quote`, `landlord_advice`, `note`, …), `send_message(recipient_ref,
    body)` (mock), `pause(reason)` (terminal; reason ∈ AWAITING_LANDLORD_APPROVAL /
    AWAITING_TENANT_INFO / AWAITING_CONTRACTOR_QUOTES / NEEDS_HUMAN_REVIEW / RESOLVED).
    The agent infers the route — it is not told which turn it is on.
  - **Rehydration is a generic log dump** — no per-artifact-kind formatter, no per-trigger
    branching. `rehydrate()` reads the rows, renders `EVENT #n type=… payload=…` /
    `ARTIFACT seq=… kind=… data=…` lines time-ordered, appends "the most recent EVENT woke
    you; decide, then pause".
  - **`classify_inbound()`** is an explicit stub seam: CLI args → a typed `events` row. In
    production this is a thin LLM classifier (intent + issue/contractor correlation); the
    `events` row is its output contract.
  - **Instrumentation:** per-call token/cost via OpenRouter `usage.include` +
    `GET /api/v1/generation` (restored from `cost_estimate_agent_openrouter_prototype.py`),
    written into a JSONL trace `prototypes/logs/{issue_id}/turn_{n}.jsonl` (one line per
    step) plus a per-turn total printed to stdout.
  - CLI: `init-db`, `report-issue --text`, `approve <id> [--note]`, `reject <id> --note`,
    `message --issue N --from contractor|tenant|landlord [--ref] --text`, `event --issue N
    --type T --json '{}'` (generic escape hatch), `show <id>`.
- **`prototypes/property.yaml`** — static property grounding (Beech Range, Levenshulme —
  same fixture as the earlier prototypes). No tenant/personal details (deliberate).
- **`prototypes/requirements.txt`** — added `pyyaml`.
- **`prototypes/README.md`** — added a short "State-management flow" entry.
- **`.gitignore`** — added `.venv/`, `prototypes/logs/`, `prototypes/*.db`.

## What was explored / learnt

### Deployment model — chose "option 1" (cold-start-per-turn, event-sourced state)

Compared five approaches: (1) cold-start per turn + event-sourced domain state; (2)
durable-execution / checkpointed workflow (LangGraph checkpointer, Temporal, DBOS); (3)
always-on single long-lived process with in-memory state; (4) long-context "everything in
the prompt"; (5) hybrid — event-sourced domain DB + a checkpointer scoped to one in-flight
turn. **Picked (1)**, with (5) as the escape hatch. Rationale: every gate in the flow
(landlord approval, waiting on a contractor) is naturally an event that starts a fresh
turn — none need a mid-loop pause, so the checkpointer's headline feature buys little here;
both flows hinge on reading a structured value back (`SELECT` the estimate, compare to the
quote), which rules out (4) and means (2)/(3) need a domain DB anyway; it's a work-item
system with hours/days between steps and typed terminal states already in the spec.

**Consequence:** human approval is a **turn boundary**, not a blocking `input()` or a
LangGraph `interrupt()`. Last session's LangChain/LangGraph HITL ports would need reworking,
not extending, for this model.

### Production ingress ≈ a thin LLM classifier, not a second agent

Ingress in production (WhatsApp-style free-text interaction) is very likely one stateless
LLM call: inbound text + the landlord's open-issue list → typed event `{type, issue_id,
contractor_id?, payload}`. Routes, never decides. Natural home for a low-confidence
confirmation turn. Where prompt-injection defence concentrates. Doesn't change the turn or
state model — the typed `events` row is its output contract. Watch the line where ingress
grows to hold dialogues / status queries / scheduled chasing → then it's a second agent and
that's a deliberate multi-agent decision.

### WhatsApp reality doesn't change what this prototype tests

The cold-start/rehydrate/terminate spine is channel-agnostic. What WhatsApp adds — intent
classification, issue/contractor correlation without IDs, multi-intent messages, debounce —
all sits upstream of the agent turn. The CLI subcommands with explicit `--issue`/`--contractor`
flags are a deliberate stand-in for that ingress layer.

### First design was too rigid — rewritten

Initial build hard-coded the three turns: `TURN1_PROMPT`/`TURN2_PROMPT`/`TURN3_PROMPT`,
per-turn tool subsets in a `TURN_CONFIG`, a `render_artifact()` with an `if kind == …`
branch per artifact type, and a `trigger_text()` per event type. Rejected by review as
un-scalable to the other paths (triage-only, needs-info, whitelist C/D, rejection re-entry)
and as "predicting all the triggers". Rewritten to one prompt / one tool set / generic log
dump / agent-inferred route.

### Route-inference run 1 (issue 1) — diverged

With a bare "decide for yourself" prompt, mercury on turn 1 emitted `find_contractors` +
two `write_artifact` + `pause` **in a single assistant message** — so it drafted and paused
before seeing the contractor results. Never called `research_cost`, never wrote a
`cost_estimate` artifact (stuffed an invented range into the draft body), never
`record_contractor`, addressed the draft to the **landlord** not a contractor. Turn 2
(`approved`) then had nothing sendable and re-drafted another landlord message, pausing
`AWAITING_LANDLORD_APPROVAL` again — a stuck re-ask loop. Same "all tools fire in round 1"
behaviour logged 09 Sep. Traces preserved at `prototypes/logs/1/`.

### Prompt edit — run 2 (issue 2) — clean end-to-end

Edited the system prompt to the earlier prototypes' "middle ground": still order-free
("you decide what a given issue needs") but names the usual shape as numbered steps
(research → `cost_estimate` → find/record contractors → one `draft_message` per contractor
→ pause; on approval → `send_message` each → pause; on a quote reply → `quote` artifact →
compare to `cost_estimate` → `landlord_advice` → pause), plus two explicit rules: "do NOT
call pause in the same step as other tools" and "quote messages go TO contractors, not the
landlord". Result — all three turns for issue 2 ran clean as **separate cold processes**:
  - Turn 1: `cost_estimate` £80–200 grounded in research; 3 contractors recorded (correctly
    skipped "Able Group" = install/disconnect only); 3 contractor-addressed quote-request
    drafts; `pause` isolated in its own round. → `AWAITING_LANDLORD_APPROVAL`
  - Turn 2 (`approve 2`): rehydrated, `send_message` ×3, `sent` artifacts seq 5–7. →
    `AWAITING_CONTRACTOR_QUOTES`
  - Turn 3 (`message --from contractor --ref 2`, realistic Gas-Safe-engineer prose):
    rehydrated, interpreted prose → `quote` artifact (£110–240 merged from base + conditional;
    £75 deductible call-out and parts-availability caveat captured; "earliest Tuesday";
    terms); `landlord_advice` comparing to the estimate ("aligns… upper bound could exceed
    it if the gas tap needs replacing"). → `AWAITING_LANDLORD_APPROVAL`
  - Rehydration verified via growing prompt size (5.6k → 9.8k tokens). ~$0.018 for the run.

## Decisions and trade-offs

- **Decision:** Deployment model = cold-start per turn, event-sourced state; human approval
  is a turn boundary; no checkpointer. **Why:** every gate is naturally an event; both
  flows need structured read-back; smallest thing that faithfully tests the production
  mental model. **Trade-off:** bespoke rehydration code; the agent's within-turn scratchpad
  is lost between turns — anything worth remembering must be written to an artifact.
- **Decision:** Single generic `write_artifact(kind, data)` instead of typed propose tools
  (`propose_cost_estimate`, etc.). **Why:** scales to any path with no new tools. **Trade-off:**
  no schema enforcement — run 1 invented `recipient_type: "landlord"` and skipped
  `cost_estimate` entirely; the prompt now carries the guardrails instead.
- **Decision:** Keep `contractors` as a standalone table the agent reads and writes; drop
  the whitelist / preferred-contractors / Path C-vs-D distinction from this flow. **Why:**
  prove the external read/write contract first; whitelist is a separate later flow.
  **Trade-off:** contractors are issue-scoped only; no cross-issue reuse yet.
- **Decision:** Append-log (`issue_artifacts`) + `contractors` table only; no projection
  tables. **Why:** reading a JSON value out of one row by `kind` doesn't need a projection;
  the log stays small. Matches the spec.
- **Decision:** `classify_inbound()` / CLI flags stub the ingress layer. **Why:** the novel,
  risky part is state across cold turns; hard-code classification + correlation for now.
- **Decision:** Fixed run-1 divergence with a prompt edit only (name the happy-path steps,
  forbid pause-with-tools, force contractor recipients) rather than loop-code guards or a
  model swap. **Why:** smallest change; matches the earlier prototypes' prompt style.
  **Trade-off:** still relies on the model honouring "don't pause in the same step";
  not structurally enforced.
- **Decision:** No tenant/personal details in `property.yaml`. **Why:** user instruction.
- **Decision:** Preserve `prototypes/logs/1/` (diverged run) alongside `logs/2/` rather
  than deleting or archiving. DB kept between runs so issue ids don't collide.

## Blockers

None. Nothing committed — working tree has the new/changed files staged for the user to
commit.

## Next steps

1. Commit: `prototypes/state_management_flow_prototype.py`, `prototypes/property.yaml`,
   `prototypes/README.md`, `prototypes/requirements.txt`, `.gitignore`, this summary.
2. Quality gaps observed in run 2 (not blockers): `quote.confidence` is free text (the
   enum was lost when tools collapsed to `write_artifact`); the "could be a new hob"
   open-ended escalation wasn't captured as a discrete condition; consider whether a few
   typed fields on `write_artifact` for the common kinds are worth the rigidity.
3. Test the deferred paths on the same machinery with no code change: triage-only,
   needs-info (`AWAITING_TENANT_INFO`), landlord `reject` re-entry, a second contractor
   quote arriving (turn 3 re-runs and re-advises).
4. Add the whitelist / preferred-contractors flow (pre-seeded approved contractors,
   `get_preferred_contractors`, the ≥2 decision) as a separate exercise.
5. Prototype the real ingress classifier (inbound text → typed `events` row) as its own
   small piece.
6. Decide if/when to move the loop model to `claude-sonnet-5` (spec's choice) — mercury's
   blind-parallel-tool-call behaviour is a recurring friction.
7. Still open from Session 1 / 09 Sep: mobile approval shape; eval + observability harness;
   OpenRouter `web` plugin inconsistency; real project `README.md`; update `ARCHITECTURE.md`
   (now that there is a state model + deployment decision to describe).
