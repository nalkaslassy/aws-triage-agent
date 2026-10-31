"""Bounded investigation runtime with application-enforced scope and citations."""

import copy
import json
import time
from dataclasses import replace

from .collect import validate_manifest, AWSCollector
from .followups import CHECKS
from .investigate import evidence_reference, investigate
from .model import Bundle, Evidence, Finding, text_field, utc_time
from datetime import datetime, timezone
from .planner import CAUSES, NEXT_STEPS

KINDS = {"lambda_metrics", "lambda_configuration", "lambda_concurrency", "log_signals", "api_metrics",
         "permission_simulation", "change_history", "followup_failure"}
TITLES = {"authorization": "Authorization-related failure warrants investigation",
          "configuration": "Application configuration warrants investigation",
          "application": "Application exception warrants investigation",
          "capacity": "Concurrency or capacity restriction warrants investigation",
          "network": "Network or dependency connectivity warrants investigation"}


def in_scope(item, manifest, function):
    if item.kind not in KINDS:
        return False
    if item.kind == "log_signals":
        return item.resource == "/aws/lambda/" + function and item.resource in manifest.get("log_groups", [])
    if item.kind == "api_metrics":
        return item.resource in {f"{a['api_name']}/{a['stage']} ({a['api_id']})" for a in manifest.get("rest_apis", [])}
    return item.resource == function


def supports(cause, item, start, end):
    if item.status not in {"observed", "partial"}:
        return False
    data = item.data
    if item.kind == "log_signals":
        key = {"authorization": "access_denied", "application": "exception", "network": "timeout"}.get(cause)
        return bool(key and data.get(key) and data[key] > 0 and any(
            s.get("signal") == key and s.get("event_id") and s.get("timestamp") is not None
            and utc_time(start).timestamp() * 1000 <= s["timestamp"] < utc_time(end).timestamp() * 1000
            for s in data.get("samples", [])))
    if cause == "authorization" and item.kind == "permission_simulation":
        return item.status == "observed" and not data.get("missing_context") and data.get("decision") in {"explicitDeny", "implicitDeny"}
    if cause == "configuration" and item.kind == "lambda_configuration":
        return item.status == "observed" and bool(data.get("orders_table") and data.get("expected_table") and data["orders_table"] != data["expected_table"])
    if cause == "capacity":
        return (item.kind == "lambda_concurrency" and item.status == "observed" and data.get("reserved_concurrency") == 0
                or item.kind == "lambda_metrics" and item.status == "observed" and bool(data.get("Throttles") and data["Throttles"] > 0))
    return False


def validate_decision(decision, evidence, start, end):
    if not isinstance(decision, dict):
        raise ValueError("Decision must be an object")
    if decision.get("action") == "check":
        if set(decision) != {"action", "check"} or decision["check"] not in CHECKS:
            raise ValueError("Unsupported check proposal")
        return
    if decision.get("action") != "finish" or set(decision) != {"action", "candidates", "next_steps"}:
        raise ValueError("Invalid finish proposal")
    steps, candidates = decision["next_steps"], decision["candidates"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 4 or any(not isinstance(s, str) or s not in NEXT_STEPS for s in steps):
        raise ValueError("Invalid next steps")
    if not isinstance(candidates, list) or len(candidates) > 3:
        raise ValueError("Invalid candidate list")
    by_id, seen = {e.id: e for e in evidence}, set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != {"cause", "supporting", "contradicting"}:
            raise ValueError("Invalid candidate")
        cause = candidate["cause"]
        if not isinstance(cause, str) or cause not in CAUSES or cause in seen:
            raise ValueError("Invalid or repeated cause")
        seen.add(cause)
        for key in ("supporting", "contradicting"):
            refs = candidate[key]
            if not isinstance(refs, list) or len(refs) > 5 or any(not isinstance(r, str) for r in refs) or len(refs) != len(set(refs)):
                raise ValueError("Invalid evidence references")
            if any(r not in by_id or by_id[r].status not in {"observed", "partial"} for r in refs):
                raise ValueError("Unknown or unavailable evidence reference")
        if set(candidate["supporting"]) & set(candidate["contradicting"]):
            raise ValueError("Evidence cannot both support and contradict a candidate")
        if not candidate["supporting"] or not any(supports(cause, by_id[r], start, end) for r in candidate["supporting"]):
            raise ValueError("Candidate lacks a qualifying observation")


def run_agent(bundle, manifest, function, symptom, planner, backend, max_steps=6, seconds=60):
    validate_manifest(manifest)
    if bundle.application != manifest["application"] or function not in manifest.get("lambda_functions", []):
        raise ValueError("Incident application/function must match the manifest")
    text_field(symptom, "symptom", 500)
    if type(max_steps) is not int or not 1 <= max_steps <= 10 or type(seconds) is not int or not 1 <= seconds <= 120:
        raise ValueError("Invalid investigation budget")
    # Copy imported mutable data before analysis; model output never mutates it.
    evidence = copy.deepcopy([e for e in bundle.evidence if in_scope(e, manifest, function)])
    journal, completed, serial, planner_turns = [], set(), 0, 0
    started = time.monotonic()
    finish, stop = None, "step_budget"
    for _ in range(max_steps):
        if time.monotonic() - started >= seconds:
            stop = "deadline"
            break
        state = {"application": bundle.application, "function": function, "symptom": symptom,
                 "start": bundle.start, "end": bundle.end,
                 "evidence": [evidence_reference(e) for e in evidence],
                 "completed_checks": sorted(completed), "journal": journal,
                 "remaining_steps": max_steps - len(journal)}
        try:
            planner_turns += 1
            decision = planner.next(copy.deepcopy(state))
        except Exception as error:
            stop = "planner_unavailable"
            journal.append({"action": "planner_error", "code": AWSCollector.error_code(error)})
            break
        try:
            validate_decision(decision, evidence, bundle.start, bundle.end)
        except (ValueError, TypeError, KeyError):
            stop = "invalid_decision"
            journal.append({"action": "rejected", "reason": "Proposal violated check, scope, candidate, or evidence rules."})
            break
        if time.monotonic() - started >= seconds:
            stop = "deadline"
            break
        if decision["action"] == "finish":
            finish, stop = decision, "finished"
            break
        check = decision["check"]
        if check in completed:
            journal.append({"action": "check", "check": check, "status": "cached", "new_evidence_ids": []})
            continue
        completed.add(check)
        try:
            additions = backend.run(check)
            if not isinstance(additions, list) or len(additions) > 20 or any(not isinstance(e, Evidence) or not in_scope(e, manifest, function) for e in additions):
                raise ValueError("Backend returned out-of-scope evidence")
        except Exception:
            additions = [Evidence("Failure", "followup_failure", function, check, "unavailable",
                                  {"reason": "Follow-up could not be completed; no health conclusion is supported."}, datetime.now(timezone.utc).isoformat())]
        ids = []
        for item in additions:
            while True:
                serial += 1
                identity = f"F{serial:03}"
                if identity not in {e.id for e in evidence}:
                    break
            evidence.append(replace(item, id=identity))
            ids.append(identity)
        journal.append({"action": "check", "check": check, "status": "completed" if additions else "no_evidence", "new_evidence_ids": ids})
    collected = Bundle(bundle.application, bundle.start, bundle.end, evidence)
    report = investigate(collected)
    report.mode = "bounded adaptive"
    candidates = finish["candidates"] if finish else []
    next_steps = finish["next_steps"] if finish else ["collect_missing"]
    for rank, candidate in enumerate(candidates, 1):
        report.findings.append(Finding(
            f"Candidate {rank}: {TITLES[candidate['cause']]}", "hypothesis",
            "The planner selected this category using qualifying observations. Candidate order is not a calibrated confidence score. "
            "Supporting references do not prove incident causality. Potential counterevidence to review: "
            + (", ".join(candidate["contradicting"]) or "none supplied; absence is not proof"),
            candidate["supporting"], [NEXT_STEPS[k] for k in next_steps], "On-call engineer", function))
    report.gaps += ["Current policy simulations and configuration do not establish the actual failing principal or historical effective permissions.",
                    "Evidence references and qualifying observation categories are validated; semantic causality is not automatically verified."]
    if stop != "finished":
        report.gaps.append(f"Adaptive investigation stopped: {stop}. Deterministic findings remain available; no planner assessment was accepted.")
    return {"planner": type(planner).__name__, "stop_reason": stop,
            "assessment": {"status": "hypotheses" if candidates else "insufficient_evidence",
                           "candidates": candidates, "next_steps": [NEXT_STEPS[k] for k in next_steps]},
            "journal": journal, "model_usage": getattr(planner, "usage", None),
            "metrics": {"planner_turns": planner_turns, "executed_checks": len(completed),
                        "sdk_operations": backend.collector.calls if hasattr(backend, "collector") else None,
                        "elapsed_seconds": round(time.monotonic() - started, 6)},
            "report": report.to_dict(), "evidence_bundle": collected.to_dict()}


def agent_markdown(result):
    from .model import Report
    from .investigate import markdown
    data = result["report"]
    report = Report(**{**data, "findings": [Finding(**f) for f in data["findings"]]})
    header = (f"Planner: {result['planner']}\n\nStop reason: {result['stop_reason']}\n\n"
              f"Assessment: {result['assessment']['status']}\n\n")
    metrics = result["metrics"]
    header += (f"Planner turns: {metrics['planner_turns']}; executed checks: {metrics['executed_checks']}; "
               f"elapsed: {metrics['elapsed_seconds']} seconds.\n\n")
    if result["planner"] == "ReplayPlanner":
        header += "Synthetic/scripted replay; no model inference or live AWS validation.\n\n"
    text = header + markdown(report) + "\n## Investigation journal\n\n"
    for entry in result["journal"]:
        text += "- " + json.dumps(entry) + "\n"
    text += "\n## Recommended next steps\n\n"
    text += "\n".join("- " + step for step in result["assessment"]["next_steps"]) + "\n"
    return text
