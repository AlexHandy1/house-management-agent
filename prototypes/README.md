# Prototypes

Throwaway experiments on the maintenance reasoning loop. Expected to be rewritten.
Spec: `../docs/specs/maintenance-agent-slice1-full-prototype.md`.
Session notes: `../docs/status_docs/WORK_SUMMARY_*.md`.

## Contents

### Cost-estimate loop (one tool)

- `cost_estimate_agent_search_prototype.py` — simplest hand-rolled ReAct loop, raw
  Anthropic SDK, native tool calling. One tool (`research_cost()` → web-search-backed
  sub-call). Stops when the model emits no `tool_use`; `MAX_ROUNDS` backstop. Model
  `claude-haiku-4-5`.
- `cost_estimate_agent_openrouter_prototype.py` — same loop via OpenRouter's
  OpenAI-compatible API, swappable `MODEL`, `web` plugin for search, per-call
  token/cost instrumentation.
- `cost_estimate_search_rough_cost_trace_comparison_080926.md` — rough model/cost/trace
  comparison (Haiku, GPT-5.6 Luna, mercury-2.5, glm-5.3-flash).

### Happy path: cost + contractors + drafted message + human-in-the-loop

All use `inception/mercury-2.5` via OpenRouter and share the same 5 tools
(`research_cost`, `find_contractors`, `draft_message`, `request_approval`, `send_message`)
and the same model-facing prompts. `request_approval` and `send_message` are deliberately
separate steps with nothing enforcing the landlord's decision — see each file's docstring.

- `happy_path_contractor_message_prototype.py` — extends the cost-estimate loop with
  `find_contractors()` and `draft_message()`. No HITL.
- `happy_path_contractor_message_hitl_prototype.py` — adds `request_approval()` (blocks on
  a terminal `y/n` prompt) and a mock `send_message()`. Hand-rolled `while` loop, raw
  `openai` client. **Baseline** for the framework comparison.
- `happy_path_contractor_message_hitl_langchain_prototype.py` — same behaviour via
  LangChain 1.x `create_agent`. HITL through langgraph `interrupt()` + `InMemorySaver` +
  `Command(resume=...)`. Model-facing strings copied verbatim into `*_PROMPT` / `*_DESC`
  constants; `@tool(description=..., args_schema=...)` holds schema parity with the
  baseline. Contains a temporary `_invoke_text()` sub-call instrumentation helper.
- `happy_path_contractor_message_hitl_langgraph_prototype.py` — same behaviour via an
  explicit `StateGraph` (`call_model` node + `ToolNode` + conditional edge). Same
  verbatim string constants; self-contained.

Comparison and findings: `../docs/status_docs/WORK_SUMMARY_100926.md`.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# put ANTHROPIC_API_KEY / OPENROUTER_API_KEY in prototypes/.env
python cost_estimate_agent_search_prototype.py
```
