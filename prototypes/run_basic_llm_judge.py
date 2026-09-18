"""Basic LLM judge (Claude Haiku) for a basic_eval_harness_prototype.py run.

Judges ONLY the final response the agent gave for an issue — not its intermediate
reasoning or tool calls — against three binary Y/N criteria from
prototype_agent_behaviour_spec.md:
  1. cost_estimate_evidenced — an evidenced cost estimate + range, grounded in the
     research_cost findings the agent actually saw (not invented).
  2. contractors_evidenced   — relevant contractor(s) for the issue's trade, with contact
     details, and evidence for why each was selected (from a credible web source, or the
     preferred whitelist).
  3. concise                 — free of unnecessary narrative beyond what the task needs.

Input is the JSONL trace basic_eval_harness_prototype.py already writes (one file per
issue) — nothing else is read. The judge only needs what's IN the trace: the issue text
(written to `run_start` as of 18 Sep), the research/find_contractors findings (so it can
check the final answer is actually grounded in them), and the final `model_message`.

Needs ANTHROPIC_API_KEY in prototypes/.env
Run:
  ./.venv/bin/python run_basic_llm_judge.py logs/<run_id>/<issue_id>.jsonl   # one trace
  ./.venv/bin/python run_basic_llm_judge.py logs/<run_id>/                  # every trace in a run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

MODEL = "claude-haiku-4-5-20251001"
HERE = Path(__file__).parent

client = anthropic.Anthropic()

JUDGE_CRITERIA = ["cost_estimate_evidenced", "contractors_evidenced", "concise"]

JUDGE_PROMPT_TEMPLATE = """\
You are a strict QA judge. You are reviewing ONLY the FINAL response an AI lettings-\
maintenance assistant gave for one reported issue — not its intermediate reasoning or \
tool calls — exactly as a landlord reading it would see it.

Issue reported:
{issue_text}

Web research the assistant had available before writing its final response (use this to \
check its claims are actually grounded in real findings, not invented):
--- research_cost findings ---
{research_findings}
--- find_contractors findings ---
{contractor_findings}
--- other tool findings (e.g. a generic web_search tool) ---
{other_findings}

Final response to judge:
---
{final_text}
---

Answer all three with exactly "Y" or "N". A response that correctly recognised it didn't \
have enough information and asked a clarifying question instead of estimating/sourcing \
contractors should get "N" on criteria 1/2 (explain why in notes — that is a legitimate \
outcome, not necessarily a bad one, but it did not meet the criterion itself).

1. cost_estimate_evidenced: Does the final response give a cost estimate for the issue, as \
a range, that is actually grounded in the cost-research findings above — research_cost or \
a generic web_search — (not invented or contradicted by them)?
2. contractors_evidenced: Does the final response list contractor(s) relevant to this \
issue's trade, with contact details, and evidence for why each was selected (either from \
the contractor-search findings above — find_contractors or a generic web_search — or \
because they are an explicitly preferred/whitelisted contractor)?
3. concise: Is the final response free of unnecessary narrative or padding beyond what's \
needed to convey the estimate, contractors, and rationale?

Respond with ONLY a JSON object, no other text, no markdown fences:
{{"cost_estimate_evidenced": "Y or N", "contractors_evidenced": "Y or N", \
"concise": "Y or N", "notes": "<=2 sentences, only explaining any N"}}
"""


def load_trace(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_judge_input(events: list[dict]) -> dict:
    run_start = next((e for e in events if e["kind"] == "run_start"), {})
    final_message = next(
        (e for e in reversed(events) if e["kind"] == "model_message" and e.get("content")),
        None)
    tool_results = {"research_cost": [], "find_contractors": [], "other": []}
    for e in events:
        if e["kind"] != "tool_result":
            continue
        bucket = e["name"] if e["name"] in ("research_cost", "find_contractors") else "other"
        entry = e["result"] if bucket != "other" else f"[{e['name']}] {e['result']}"
        tool_results[bucket].append(entry)

    return {
        "issue_id": run_start.get("issue_id", "?"),
        "issue_text": run_start.get("issue_text", "(not recorded in this trace)"),
        "final_text": final_message["content"] if final_message else "(no final response found)",
        "research_findings": "\n\n".join(tool_results["research_cost"]) or "(not called)",
        "contractor_findings": "\n\n".join(tool_results["find_contractors"]) or "(not called)",
        "other_findings": "\n\n".join(tool_results["other"]) or "(none)",
    }


def judge_trace(path: Path) -> dict:
    events = load_trace(path)
    judge_input = build_judge_input(events)
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        issue_text=judge_input["issue_text"],
        research_findings=judge_input["research_findings"],
        contractor_findings=judge_input["contractor_findings"],
        other_findings=judge_input["other_findings"],
        final_text=judge_input["final_text"],
    )

    resp = client.messages.create(
        model=MODEL, max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text").strip()
    # Haiku sometimes wraps the JSON in a ```json fence despite being told not to.
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError:
        verdict = {c: "N" for c in JUDGE_CRITERIA} | {
            "notes": f"judge did not return valid JSON: {raw[:300]!r}"}

    return {"issue_id": judge_input["issue_id"], "trace_path": str(path), **verdict}


def print_verdict(v: dict) -> None:
    marks = " ".join(f"{c}={v.get(c, '?')}" for c in JUDGE_CRITERIA)
    print(f"[{v['issue_id']}] {marks}")
    if v.get("notes"):
        print(f"    notes: {v['notes']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="basic LLM judge for a harness trace")
    ap.add_argument("path", type=Path, help="a trace .jsonl file, or a run's log directory")
    args = ap.parse_args()

    if not args.path.exists():
        raise SystemExit(f"No such path: {args.path}")

    trace_paths = (
        sorted(args.path.glob("*.jsonl")) if args.path.is_dir() else [args.path])
    if not trace_paths:
        raise SystemExit(f"No .jsonl traces found in {args.path}")

    verdicts = []
    for p in trace_paths:
        v = judge_trace(p)
        print_verdict(v)
        verdicts.append(v)

    if len(verdicts) > 1:
        out_path = (args.path if args.path.is_dir() else args.path.parent) / "judge_results.csv"
        import csv
        with out_path.open("w", newline="") as f:
            fields = ["issue_id", "trace_path", *JUDGE_CRITERIA, "notes"]
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(verdicts)
        print(f"\n[csv] {out_path}  ({len(verdicts)} rows)")


if __name__ == "__main__":
    main()
