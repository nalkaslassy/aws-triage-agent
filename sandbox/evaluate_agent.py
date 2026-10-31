"""Compare deterministic initial triage with scripted follow-up contracts.

No LLM or AWS is called. This cannot measure AI diagnosis quality or benefit.
"""

import json
from pathlib import Path

from aws_triage.agent import run_agent
from aws_triage.followups import ReplayFollowups
from aws_triage.investigate import investigate
from aws_triage.model import Bundle
from aws_triage.planner import ReplayPlanner


def evaluate():
    rows = []
    root = Path(__file__).resolve().parents[1] / "examples" / "agent"
    for path in sorted(root.glob("*.json")):
        case = json.loads(path.read_text())
        bundle = Bundle.from_dict(case["bundle"])
        initial = investigate(bundle)
        backend = ReplayFollowups(case["followups"])
        result = run_agent(bundle, case["manifest"], case["function"], case["symptom"],
                           ReplayPlanner(case["decisions"]), backend)
        actual = {"stop_reason": result["stop_reason"],
                  "causes": [candidate["cause"] for candidate in result["assessment"]["candidates"]]}
        rows.append({"case": path.stem, "passed": actual == case["expected"],
                     "initial_rule_findings": len(initial.findings),
                     "followup_checks": backend.calls, "accepted_candidates": actual["causes"],
                     "stop_reason": result["stop_reason"],
                     "additional_evidence_items": len(result["evidence_bundle"]["evidence"]) - len(bundle.evidence)})
    return {"evaluation_type": "scripted replay contracts; no model inference or live AWS calls",
            "model_vs_rules_quality": "not measured", "passed": bool(rows) and all(r["passed"] for r in rows), "cases": rows}


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
