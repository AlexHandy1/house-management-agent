# Work Summary — 09 September 2026

Distinct session from 08 Sep (which built the first hand-rolled loop + OpenRouter cost
comparison). Today: extended the happy path from cost estimate to a full loop —
contractors, drafted message, and a human-in-the-loop landlord approval step — then
discussed how that approval step should be designed against the spec's `pause(reason)`
model before building it. All work under `prototypes/` (untracked, gitignored).

## What was built

- **`prototypes/happy_path_contractor_message_prototype.py`** — extends
  `cost_estimate_agent_openrouter_prototype.py`'s loop with two more tools:
  `find_contractors()` and `draft_message()`, alongside the existing `research_cost()`.
  Single model (`inception/mercury-2.5`), no cost/token instrumentation (stripped out to
  start with, per this session's brief). `MAX_ROUNDS=20`. System prompt lists all three
  tools and lets the model decide order/necessity itself (see decisions below).
- **`prototypes/happy_path_contractor_message_hitl_prototype.py`** — fresh, fully
  self-contained copy of the above (no imports from other project scripts) plus two new
  tools: `request_approval(message)` (blocks on a real terminal `y/n` prompt, no side
  effect, returns the landlord's decision as text) and `send_message(message)` (mock
  send — just prints to stdout). The two are deliberately separate tools/steps rather
  than one gated tool, so the model itself decides whether to call `send_message` after
  seeing `request_approval`'s outcome. Argument passing: the model's tool-call arguments
  arrive as a raw JSON string (`tc.function.arguments`), parsed once in `call_tool()` via
  `json.loads(arguments_json or "{}")`, then routed by tool name — `MESSAGE_ARG_TOOLS`
  dict dispatch for the two message-argument tools, `TOOL_FUNCTIONS` dict dispatch for the
  three no-argument tools (which ignore whatever the model put in `arguments`). Not yet
  run end-to-end (built, reviewed line-by-line with the user, but no live trace taken).

## What was explored / learnt

- **Parallel tool calls are automatic OpenAI-compatible API behaviour, not something the
  loop opts into.** When multiple tools are independent (as `research_cost`,
  `find_contractors`, `draft_message` are — none take arguments or depend on another's
  output), a single model response can return several `tool_calls` in one round. The loop
  still executes them **sequentially in Python** (`for tc in message.tool_calls: ...`),
  not concurrently — worth revisiting if/when latency matters more than at prototype
  stage. Observed first run: all three tools fired in round 1, round 2 had zero tool
  calls and was the model's single required synthesis turn (not a repeat/bug) — 2
  rounds / 4 model calls total for that run.
- **Read the spec's `pause(reason)` design in full**
  (`docs/specs/maintenance-agent-slice1-full-prototype.md` §4-6) before building the
  approval step. Spec's actual model: `pause(reason)` ends a turn (typed, one of
  `AWAITING_TENANT_INFO`/`AWAITING_LANDLORD_APPROVAL`/`NEEDS_HUMAN_REVIEW`); the agent has
  **no send tool at all** — Invariant 1 (§6) is "never send," and the actual send is
  performed by a separate `approve` CLI command, "a human action outside the loop... not
  an agent tool" (§4). This structurally prevents the agent from ever sending, rather than
  relying on it behaving well after a decline.
- **User explicitly wants to explore beyond the spec's split for this prototype** — spec
  is "intentionally limited," and the interest now is testing `send_message` as an
  agent-triggered tool, gated by a `request_approval` tool answered live in the terminal.
  Chosen over both a single gated `send_message` (conflates ask+send, doesn't transfer to
  a real async approval flow) and a loop-level enforced interrupt (correct long-run shape,
  but premature before observing whether the model even needs enforcing).

## Decisions and trade-offs

- **Decision:** Strip cost/token instrumentation from both new happy-path scripts (no
  `record_usage`/`print_totals`/generation-record fetch). **Why:** user wants the simplest
  possible extension focused on capability/latency/cost sense-check, not per-call cost
  granularity, for this slice. **Trade-off:** no per-run cost breakdown from these scripts
  directly — cost visibility for this path would need to be re-added later or read off
  OpenRouter's dashboard.
- **Decision:** Single model only (`inception/mercury-2.5`), no `MODEL`-swapping block.
  **Why:** mercury was the only model that confirmed `web=5` (live search) in the prior
  session; narrows the variable set for this sense-check. **Trade-off:** no fresh
  comparison against Luna/glm on this longer path.
- **Decision:** `find_contractors()` always does a fresh web search; no existing/preferred
  contractor list or lookup-first step. **Why:** starting point assumes no existing
  contractor data. **Trade-off:** none yet — flagged as a likely next-step gap (see next
  steps: external state).
- **Decision:** `draft_message()`'s sub-call may rephrase/clarify a vague tenant-reported
  issue for a tradesperson audience, "without inventing specifics you're not reasonably
  confident about." **Why:** tenant-reported issues can be poorly described; want to
  observe how the model handles this rather than leaving it undefined. **Trade-off:**
  flagged as a capability that should likely be separated into its own step (e.g. a
  distinct "clarify/normalise issue" tool) as the architecture grows, rather than living
  inside message drafting indefinitely.
- **Decision:** Removed the enumerated 1/2/3 sequential task list from the system prompt;
  now just lists tools and says "decide for yourself which of these are useful and in
  what order." **Why:** the ReAct loop needs future flexibility for issues that don't
  need all three (or a different order); want to test whether the model independently
  converges on the happy path rather than being told to follow it. **Trade-off:** less
  predictable/steerable behaviour per run; not yet observed how much this affects
  consistency across repeated runs.
- **Decision:** For the HITL prototype, went with a variant of "Option B" — separate
  `request_approval` and `send_message` tools, not one tool with approval logic baked in,
  and not a loop-level enforced interrupt. **Why:** matches user's explicit interest in
  testing `send_message` as an agent-triggered tool (diverging from the spec's stricter
  "agent never sends" split on purpose), while keeping the approval step observable in the
  trace. **Trade-off:** nothing in the code stops the model from calling `send_message`
  after a `request_approval` decline — deliberate, to observe whether/how the model
  respects the outcome unenforced, not a gap to fix yet.
- **Decision:** `happy_path_contractor_message_hitl_prototype.py` is a fresh, fully
  self-contained copy rather than importing from
  `happy_path_contractor_message_prototype.py`. **Why:** user does not want cross-script
  dependencies between prototype variants. **Trade-off:** the two files will drift/need
  manual sync if the shared loop logic changes — same trade-off already accepted for the
  cost-estimate vs. OpenRouter prototype pair in the prior session.

## Observations from traces (for future development)

- Noticed significant variance in the cost estimate. Will need to do some focused work
  testing and constraining this.
- `find_contractors()` will need more guidance on search space and what details need to
  be captured. Potentially even a review scope.
- Message drafting will need style guides and more templating to match what we're looking
  for. Will also need to think about how to handle the human-in-the-loop step beyond
  terminal input.
- Even with mercury, costs still seem higher than expected (~$0.02/trace, averaging
  ~$1/M tokens) — for production cases will need to nail down whether output tokens are
  driving this additional cost.

## Next steps

1. Explore what `happy_path_contractor_message_hitl_prototype.py` would look like in
   LangGraph/LangChain — what does it make easier/harder? (Carries forward the prior
   session's parked "port the loop to LangChain/LangGraph" item, now scoped to this
   longer/HITL path specifically.)
2. Explore introducing some basic external state as a new component (e.g. contractors
   from an existing DB the agent reads and writes to), rather than `find_contractors()`
   always searching fresh. 
    - Integrate HITL feedback via terminal or some other simple server setup) and/or other external triggers to test longer horizon performance in more autonomous setting.
3. Explore a mobile-led human interaction shape for the approval step, as an alternative
   to terminal `input()` or server. 
4. Explore a more complete evaluation and observability harness — perhaps to really
   refine one step first (cost estimate), given the variance already observed.
5. Then revisit building a more complete prototype per the slice 1 spec
   (`docs/specs/maintenance-agent-slice1-full-prototype.md`), reconciling the spec's
   `pause(reason)` / no-agent-send design against what's learned from this session's
   agent-triggered `send_message` exploration.
6. Carried over from 08 Sep, still unresolved: the OpenRouter `web` plugin firing
   inconsistently across models (`web=0` for Luna/glm, `web=5` for mercury on identical
   config).
7. Create a project `README.md` with real content; update `ARCHITECTURE.md` once the loop
   stabilises (both still placeholders as of this session).
