# Prototypes

Throwaway experiments on the maintenance cost-estimate reasoning loop. Expected to be
rewritten. Spec: `../docs/specs/maintenance-agent-slice1-full-prototype.md`.

## Contents

- `cost_estimate_agent_search_prototype.py` — simplest hand-rolled ReAct loop, raw
  Anthropic SDK, native tool calling. One tool (`research_cost()` → web-search-backed
  sub-call). Stops when the model emits no `tool_use`; `MAX_ROUNDS` backstop. Model
  `claude-haiku-4-5`.
- `cost_estimate_agent_openrouter_prototype.py` — same loop via OpenRouter's
  OpenAI-compatible API, swappable `MODEL`, `web` plugin for search, per-call
  token/cost instrumentation.
- `cost_estimate_search_rough_cost_trace_comparison_080926.md` — rough model/cost/trace
  comparison (Haiku, GPT-5.6 Luna, mercury-2.5, glm-5.3-flash).

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# put ANTHROPIC_API_KEY / OPENROUTER_API_KEY in prototypes/.env
python cost_estimate_agent_search_prototype.py
```
