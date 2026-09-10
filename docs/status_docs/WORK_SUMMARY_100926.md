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
