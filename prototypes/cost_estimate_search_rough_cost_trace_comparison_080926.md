# Cost estimate search loop — rough model / cost / trace comparison (08 Sep 2026)

Rough capture from an afternoon of poking at the simplest search loop. Not a
controlled benchmark — single run per model, `max_results=5`, no repeats.

## Setup

- **Loop:** hand-rolled ReAct, one tool (`research_cost()` → its own web-search-backed
  sub-call), stop when the model emits no tool call, `MAX_ROUNDS` backstop. No pause tool,
  no persistence.
- **Scripts:** `cost_estimate_agent_search_prototype.py` (Anthropic) /
  `cost_estimate_agent_openrouter_prototype.py` (OpenRouter, OpenAI-compatible API).
- **Web search:** Anthropic server-side `web_search_20250305` (haiku run) vs OpenRouter
  `web` plugin, `max_results=5` (all OpenRouter runs).
- **Issue:** "hobs release gas but don't ignite… one burner stopped releasing gas
  completely, possibly blocked with debris." Property: Beech Range, Levenshulme, Manchester.
- **Instrumentation (OpenRouter only):** per-call tokens + cost pulled from OpenRouter's
  `GET /api/v1/generation` record; per-run table printed at the end.

## Summary

| Model | Run cost (instrumented) | Estimate range | Notes |
|---|---:|---|---|
| Claude Haiku 4.5 (Anthropic `web_search`) | ~$0.05 (uninstrumented) | **£80–£180** | no per-call token breakdown |
| OpenAI GPT-5.6 Luna (OpenRouter + `web`) | **$0.0265** | **£100–£250** | cost is ~all **output tokens** — `research_cost` hit the `max_tokens=2000` cap (1,996 completion tok ≈ $0.026). Earlier "~$0.08" was an uninstrumented run. |
| inception/mercury-2.5 (OpenRouter + `web`) | **$0.0077** | (final text not captured) | `research_cost` = $0.0074 of it; only OpenRouter model that logged `web=5` |
| z-ai/glm-5.3-flash (OpenRouter + `web`) | **$0.0078** | **£100–£250** | `research_cost` logged `web=0` |

## Key observations

1. **Revised spread: ~3–5×, not 10×.** Instrumented: Luna $0.0265 vs mercury $0.0077 /
   glm $0.0078. Haiku ~$0.05 but uninstrumented (includes Anthropic search fees).
2. **Luna's extra cost is output tokens, full stop.** Its `research_cost` call:
   prompt 112, **completion 1,996** (hit the 2,000 cap), reasoning 849, `web=0`, $0.02583.
   Almost the entire run cost is Luna generating a long answer at a high output $/M
   (implied ~$9–13/M). Not web scraping, not reasoning volume, not plugin fees. This
   confirms the "output pricing is the challenge" hypothesis for Luna specifically.
3. **The `web` plugin behaved inconsistently.** `web=5` on mercury's `research_cost`;
   `web=0` on Luna's and glm's — despite the plugin being configured identically. And the
   earlier standalone isolation test (`max_results=3`) *did* inject ~53k tokens of scraped
   page content, which none of the in-script runs did (`research_cost` prompt ≈ 112–3,000
   tokens across all three). So the plugin is not firing reliably inside the loop, and the
   53k-token scare was a one-off from the isolation test, not representative.
4. **Earlier cost theories corrected:**
   - The 53k prompt tokens were *not* representative — in-script `research_cost` prompts are
     ~100–3,000 tokens.
   - The `web` plugin fee is *not* a dominant line item at this scale — mercury's
     `research_cost` with `web=5` cost $0.0074, glm's with `web=0` cost $0.0075.
5. **The task cost sits in the `research_cost` call**, not the loop turns. Loop rounds are
   $0.0001–0.0006 each; `research_cost` is 90–97% of every run.
6. **Reasoning-token volume varies wildly:** mercury 2,693 total, Luna 910, glm 379.
7. **Substance is broadly consistent.** All four land in a £80–£300 band, all flag Gas Safe
   engineer + call-out + possible parts. No model is obviously wrong on the domain; the
   choice is cost/latency, not answer quality (on this one issue).

## Open questions

- Why is the `web` plugin logging `web=0` for Luna and glm but `web=5` for mercury? Is it
  failing silently, or is `num_search_results` just not populated for some providers? If the
  search isn't running, those "findings" are model priors, not live data.
- Break down the ~$0.0075 per `research_cost` call for mercury/glm (token vs plugin split —
  pull `cost_details` / `native_tokens_*` from the generation record).
- Confirm the `openai/gpt-5.6-luna` slug on its OpenRouter page (guessed from naming).
- Capture mercury-2.5's final estimate text (only its totals table was recorded).
- Re-run each model 3–5×; single runs are non-deterministic.
- Try `max_results=1` and re-compare (was the planned next step).

---

## Raw traces (verbatim)

### Claude Haiku ~$0.05

```
[model text]
## Cost Estimate: £80–£180

### Basis:
Two distinct problems: ignition failure on multiple burners, and a completely blocked hob
not releasing gas. Both suggest clogged injectors/burners and possibly a faulty spark
ignition system.

Covers:
- Call-out/diagnosis fee: £50–£65 (typical Manchester; often waived/credited if repair proceeds)
- Labour for ignition repair & cleaning: £60–£120 (~£60 call-out + £22.50/hr, 1–2 hrs)
- Safety inspection: included

Assumptions: debris blockage and/or ignition switch failure (common, minor part / cleaning);
no major parts replacement (spark electrode / gas valve → £250+); Gas Safe engineer;
standard hours. Replacement parts quoted separately, +£20–£100+.
```

### GPT-5.6 Luna — $0.02653

```
[model text]
- Cost estimate: £100–£250
- Basis: normal-hours Gas Safe engineer call-out and labour in Levenshulme,
  inspection/cleaning of a blocked burner or injector, and likely replacement of a spark
  electrode, ignition switch, or ignition module. Lower end = debris or minor ignition
  fault; higher end = replacement gas valve, multiple components, or a return visit.
  Emergency/out-of-hours, branded parts, or full hob replacement would cost more. Do not
  use the hob until inspected; if gas smell, turn off supply if safe and contact emergency
  gas service.

[finish_reason: stop] DONE

==============================================================================
RUN TOTAL  model=openai/gpt-5.6-luna  calls=3
  loop r1          prompt=     322 completion=      4 reasoning=      9 web= 0 $0.00009
  research_cost    prompt=     112 completion=  1,996 reasoning=    849 web= 0 $0.02583
  loop r2          prompt=   1,623 completion=    276 reasoning=     52 web= 0 $0.00062
  ------------------------------------------------------------------
  TOTAL            prompt=   2,057 completion=  2,276 reasoning=    910 web= 0 $0.02653
==============================================================================
```

Earlier uninstrumented Luna runs showed interim estimates £90–£300 then £120–£250, headline ~$0.08.

### inception/mercury-2.5 — $0.00769

```
==============================================================================
RUN TOTAL  model=inception/mercury-2.5  calls=3
  loop r1          prompt=     598 completion=    819 reasoning=    808 web= 0 $0.00015
  research_cost    prompt=   2,995 completion=    305 reasoning=  1,610 web= 5 $0.00741
  loop r2          prompt=     631 completion=    153 reasoning=    275 web= 0 $0.00014
  ------------------------------------------------------------------
  TOTAL            prompt=   4,224 completion=  1,277 reasoning=  2,693 web= 5 $0.00769
==============================================================================
```

### z-ai/glm-5.3-flash — $0.00778

```
[model text]
## Cost estimate: £100–£250

Basis: two faults on a gas hob in Levenshulme, Manchester:
1. Gas flows but no ignition — failed ignition electrode, spark generator module, or
   faulty ignition switch. Parts £15–£120 (electrode £15–£45; spark generator £50–£120),
   plus £50–£130 labour.
2. One burner with no gas flow — if blocked with debris, clean-out usually covered within
   the visit's labour. If the gas valve has failed, pushes toward the higher end.

Assumptions: lower end (~£100–£150) = call-out (£40–£80, often waived/deducted) +
straightforward ignition fix + burner clean-out in one visit; upper end (~£250) = gas
valve or spark generator module replacement + parts markup + safety testing. Manchester
~4% below UK average. Gas hob work is legally not DIY (Gas Safe engineer + gas
tightness/combustion check). Single visit, parts quoted separately.

[finish_reason: stop] DONE

==============================================================================
RUN TOTAL  model=z-ai/glm-5.3-flash  calls=3
  loop r1          prompt=     373 completion=    178 reasoning=    172 web= 0 $0.00007
  research_cost    prompt=   2,810 completion=  1,067 reasoning=     18 web= 0 $0.00748
  loop r2          prompt=   1,321 completion=    625 reasoning=    189 web= 0 $0.00023
  ------------------------------------------------------------------
  TOTAL            prompt=   4,504 completion=  1,870 reasoning=    379 web= 0 $0.00778
==============================================================================
```
