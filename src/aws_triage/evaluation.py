"""Rubric-separated evaluation of real planners against recorded follow-ups."""

import hashlib
import json
from pathlib import Path

from .agent import in_scope, run_agent
from .collect import validate_manifest
from .followups import CHECKS, ReplayFollowups
from .model import Bundle, Evidence
from .planner import CAUSES
from .investigate import investigate


def load_suite(directory):
    root = Path(directory)
    rubric = json.loads((root / "rubric.json").read_text())
    packets = []
    for path in sorted((root / "inputs").glob("case*.json")):
        packet = json.loads(path.read_text())
        if set(packet) != {"manifest", "bundle", "function", "symptom", "followups"}:
            raise ValueError("Evaluation packets must contain inputs only")
        validate_manifest(packet["manifest"])
        bundle = Bundle.from_dict(packet["bundle"])
        if packet["function"] not in packet["manifest"].get("lambda_functions", []) or bundle.application != packet["manifest"]["application"]:
            raise ValueError("Evaluation scope mismatch")
        for check, items in packet["followups"].items():
            if check not in CHECKS or not isinstance(items, list) or len(items) > 20:
                raise ValueError("Invalid recorded follow-up")
            if any(not in_scope(Evidence(**e), packet["manifest"], packet["function"]) for e in items):
                raise ValueError("Recorded evidence outside the case scope")
        expected = rubric[path.stem]
        if (set(expected) != {"allowed_causes", "allow_insufficient", "required_checks", "require_counterevidence"}
                or not isinstance(expected["allowed_causes"], list) or any(c not in CAUSES for c in expected["allowed_causes"])
                or type(expected["allow_insufficient"]) is not bool or type(expected["require_counterevidence"]) is not bool
                or not isinstance(expected["required_checks"], list) or any(c not in CHECKS for c in expected["required_checks"])):
            raise ValueError("Invalid evaluation rubric")
        digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
        packets.append((path.stem, packet, digest))
    if not packets or {p[0] for p in packets} != set(rubric):
        raise ValueError("Evaluation inputs and rubric must match exactly")
    return packets, rubric


def grade(result, expected):
    candidates = result["assessment"]["candidates"]
    causes = {c["cause"] for c in candidates}
    executed = {j["check"] for j in result["journal"] if j.get("action") == "check" and j.get("status") != "cached"}
    checks = {"finished": result["stop_reason"] == "finished",
              "category_rubric": bool(causes) and causes <= set(expected["allowed_causes"]) or not causes and expected["allow_insufficient"],
              "required_checks": set(expected["required_checks"]) <= executed,
              "counterevidence": not expected["require_counterevidence"] or not candidates or all(c["contradicting"] for c in candidates)}
    return {"passed": all(checks.values()), "checks": checks,
            "human_review_required": "Category/reference rubrics do not verify the exact causal explanation or usefulness of every handoff."}


def evaluate_suite(directory, planner_factory, limit=1, repeat=1):
    if type(limit) is not int or not 1 <= limit <= 5 or type(repeat) is not int or not 1 <= repeat <= 3:
        raise ValueError("Evaluation limit must be 1..5 and repeat 1..3")
    packets, rubric = load_suite(directory)
    rows = []
    for identity, packet, digest in packets[:limit]:
        for iteration in range(repeat):
            # The factory receives no packet ID, rubric, expected answer, or
            # scripted decisions. The planner sees only run_agent's projection.
            planner = planner_factory()
            initial = investigate(Bundle.from_dict(packet["bundle"]))
            result = run_agent(Bundle.from_dict(packet["bundle"]), packet["manifest"], packet["function"], packet["symptom"],
                               planner, ReplayFollowups(packet["followups"]))
            rows.append({"case": identity, "repeat": iteration + 1, "input_sha256": digest,
                         "deterministic_baseline": [{"title": f.title, "classification": f.classification,
                                                     "evidence_ids": f.evidence_ids} for f in initial.findings],
                         "rubric": grade(result, rubric[identity]), "result": result})
    return {"evaluation_type": "planner evaluation on curated synthetic inputs and recorded follow-ups; no live cloud diagnosis",
            "human_causal_review_required": True, "runs": rows,
            "rubric_passes": sum(r["rubric"]["passed"] for r in rows), "total_runs": len(rows)}
