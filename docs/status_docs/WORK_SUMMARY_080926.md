# Work Summary — 08 September 2026

Distinct session from 07 Sep (which produced the spec). Today: built the first working
hand-rolled ReAct loop for the maintenance cost-estimate use case, then forked it to
OpenRouter to compare model costs. All work under `prototypes/` (untracked, gitignored).

## What was built

- **`prototypes/cost_estimate_agent_search_prototype.py`** — simplest framework-free ReAct
  loop, raw Anthropic SDK, native tool calling. One read tool `research_cost()` that makes
  its own `web_search_20250305`-backed sub-call; loop stops when the model returns no
  `tool_use` block; `MAX_ROUNDS=10` backstop. No pause tool, no persistence, stdout trace.
  Model `claude-haiku-4-5-20251001`. Runs end-to-end (est. £80–£180, ~$0.05/run).
- **`prototypes/cost_estimate_agent_openrouter_prototype.py`** — exact replica of the loop
  via OpenRouter's OpenAI-compatible API (`base_url=https://openrouter.ai/api/v1`, `openai`
  SDK). `MODEL` is a single swappable constant. Web search = OpenRouter `web` plugin
  (`extra_body={"plugins":[{"id":"web","max_results":5}]}`). Cost instrumentation:
  `extra_body={"usage":{"include":true}}` + `GET /api/v1/generation` via stdlib `urllib`,
  `record_usage()` per call, `print_totals()` table in a `try/finally`. Ran against
  `inception/mercury-2.5`, `z-ai/glm-5.3-flash`, `openai/gpt-5.6-luna`.
- **`prototypes/cost_estimate_search_rough_cost_trace_comparison_080926.md`** — run costs,
  estimate ranges, per-call token/cost tables, observations and open questions.
- **`prototypes/requirements.txt`** — now `anthropic`, `openai`, `python-dotenv` (dropped
  `claude-agent-sdk`).

## What was explored / learnt

- **Abandoned the `claude-agent-sdk` stub** (`query()`): the Agent SDK owns its own loop,
  so hand-writing a ReAct loop on top fights the abstraction and hides the iterations.
  Spec §11 already mandates raw `anthropic` SDK + native `tool_use`. Confirmed by doing it.
- **Stripped the loop repeatedly** on the "simplest" push: removed the `pause_turn` branch
  (dead code — no server-side tools at the top level; web search is inside the sub-call),
  folded the `end_turn` check into `if not tool_uses: return`, dropped the `Unknown tool`
  else. Final loop: call → no tool calls ⇒ stop → append assistant turn → run tools →
  append results → repeat, with the round cap.
- **`research_cost` argument:** had `issue_summary` as a tool param to make the agent's
  query reformulation visible/gradable; removed it — the reformulation happens in the
  sub-call / `web_search` anyway, and grading it is a premature §9 concern. Where the
  reasoning is visible: only `block.input` (the result) and any pre-call `text` block; not
  the deliberation unless thinking is enabled or a rationale field is forced.
- **`.env` not loading:** `os.environ.get("OPENROUTER_API_KEY")` was `None`. Diagnosed with
  `dotenv_values()` (keys only) — `prototypes/.env` held *only* `ANTHROPIC_API_KEY`; the
  OpenRouter key was in some other file/buffer. Hardened with
  `load_dotenv(Path(__file__).with_name(".env"))` (bare `load_dotenv()` searches up from
  CWD). User then added the key.
- **`httpx` absent from the venv** (the `openai` install didn't pull it) → replaced the
  generation-record fetch with stdlib `urllib.request`.
- **Cost structure findings** (instrumented OpenRouter runs):
  - **Instrumented totals:** Luna **$0.0265**, mercury **$0.0077**, glm **$0.0078**.
    Haiku ~$0.05 uninstrumented. Spread is ~3–5×, not the 10× first assumed.
  - **Luna's cost is output tokens, full stop.** Its `research_cost` call: prompt 112,
    completion **1,996** (hit the `max_tokens=2000` cap), reasoning 849, `web=0`, $0.02583.
    Confirms the "output pricing is the challenge" hypothesis for Luna.
  - **The `web` plugin fired inconsistently:** `web=5` on mercury's `research_cost`,
    `web=0` on Luna's and glm's, same config. The earlier standalone isolation test
    (`max_results=3`) injected ~53k tokens of scraped content; no in-script run did
    (`research_cost` prompts ≈ 100–3,000 tokens). So the 53k scare was a one-off, not
    representative, and the plugin is not reliably running inside the loop.
  - **The `web` plugin fee is not a dominant line item** at this scale: mercury
    `research_cost` with `web=5` = $0.0074; glm with `web=0` = $0.0075. The earlier
    "$0.004/result dominates" hand-wave does not hold.
  - **The task cost is the `research_cost` call** (90–97% of every run); loop turns are
    $0.0001–0.0006 each.
  - All four models produced estimates in a consistent £80–£300 band — no visible quality
    difference on this one issue; the choice is cost/latency.

## Decisions and trade-offs

- **Decision:** No `pause` tool in the first version; stop on absence of `tool_use`.
  **Why:** simplest thing that answers "can a hand-rolled loop get a grounded estimate".
  **Trade-off:** untyped termination — the outer system can't tell *why* it stopped.
  Spec §5's `pause(reason)` deferred to a later slice.
- **Decision:** `research_cost()` takes no arguments; the sub-call reads the threaded
  `ISSUE`/`PROPERTY_LOCATION`. **Why:** query reformulation happens in the sub-call anyway;
  a param only earns its place if we're grading query formulation, which is premature.
  **Trade-off:** trade-classification reasoning is not a distinct observable step.
- **Decision:** `ISSUE`, `PROPERTY_LOCATION`, `SYSTEM_PROMPT_TEMPLATE` threaded as function
  parameters, kept in `UPPER_CASE`. **Why:** user wants the "config passed in from outer
  scope, threaded throughout" pattern visible from the start. **Trade-off:** non-idiomatic
  Python (params normally lower_snake).
- **Decision:** OpenRouter variant is a separate script, not a flag. **Why:** different
  SDK, tool-call shape, web-search mechanism, and stop signal (`message.tool_calls` empty
  vs no `tool_use` block); side-by-side keeps the differences legible. **Trade-off:** two
  files to keep in sync.
- **Decision:** Instrument via the generation-record fetch, not just inline `usage`.
  **Why:** inline numbers didn't explain the cost; needed the
  prompt/completion/reasoning/web/cost split to compare models honestly. **Trade-off:** an
  extra HTTP GET per call with a retry loop for the 1–4s indexing lag.

## Blockers

- **`web` plugin logs `web=0` for Luna and glm** (but `web=5` for mercury), same config. If
  the search isn't actually running, those "findings" are model priors, not live data —
  which undermines the whole point of `research_cost`. Unresolved: silent failure vs
  `num_search_results` not populated for some providers.
- **`openai/gpt-5.6-luna` slug unverified** — guessed from the naming pattern; confirm on
  its OpenRouter page.
- **~$0.0075/`research_cost` call for mercury/glm not broken down** — need `cost_details` /
  `native_tokens_*` from the generation record to see the token-vs-plugin split.

## Next steps

1. **Port the loop to LangChain / LangGraph** — use it as a hands-on intro to those
   frameworks. Compare against the hand-rolled version on basic functionality and
   interfaces (tool defs, loop control, tracing/observability, stop conditions) and on
   cost/token overhead for the same run.
2. **Grow mercury-2.5 into the working baseline** (it's the only OpenRouter model that
   confirmed `web=5`; reconsider Haiku or glm only once the `web=0` issue is understood).
   On that baseline, add tools toward a full loop: `propose_cost_estimate` (propose/write
   the committed estimate), `find_contractors`, `get_preferred_contractors`, then the
   `draft_message` / `shortlist_contractor` artifacts and `pause(reason)` per spec §3–§5.
3. Resolve the `web=0` question (does the plugin actually run for Luna/glm; is the data
   live?). Capture mercury-2.5's final estimate text.
4. Pull `cost_details` from the generation record so the comparison has a real breakdown.
5. Try `max_results=1` and re-compare across all models.
6. Re-run each model 3–5× — single runs are non-deterministic; report distribution.
7. Decide whether the OpenRouter cost delta justifies a non-Anthropic model in the loop, or
   whether this was purely a costing experiment. Record the call.
8. Add the JSONL trace + pretty-printer and the 30-round cap semantics per spec §5.
9. Create a project `README.md` with real content; update `ARCHITECTURE.md` once the loop
   stabilises (both still placeholders).
