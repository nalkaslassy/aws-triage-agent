"""Request binding and concise, application-generated incident handoffs."""

import re
import html

from .model import utc_time


def request_samples(item, start, end, signal=None):
    if item.kind != "log_signals" or item.status not in {"observed", "partial"}:
        return []
    rows = []
    for sample in item.data.get("samples", []):
        if signal and sample.get("signal") != signal:
            continue
        if (not sample.get("event_id") or sample.get("timestamp") is None
                or not utc_time(start).timestamp() * 1000 <= sample["timestamp"] < utc_time(end).timestamp() * 1000):
            continue
        if not isinstance(sample.get("request_id"), str) or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", sample["request_id"]):
            continue
        rows.append(sample)
    return rows


def authorization_samples(item, start, end):
    return [s for s in request_samples(item, start, end, "access_denied")
            if s.get("operation") == "PutItem" and isinstance(s.get("target"), str)
            and re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", s["target"])]


def simulation_matches(simulation, sample):
    data = simulation.data
    target = data.get("target")
    return (data.get("action") == "dynamodb:" + sample["operation"]
            and isinstance(target, str)
            and re.fullmatch(r"arn:aws:dynamodb:[a-z0-9-]+:\d{12}:table/" + re.escape(sample["target"]), target) is not None)


def incident_summary(bundle, function, symptom, candidates, journal, next_steps):
    by_id = {e.id: e for e in bundle.evidence}
    correlations = {}
    for item in bundle.evidence:
        for sample in request_samples(item, bundle.start, bundle.end):
            # A shared request ID groups observations within the same function;
            # a trace ID is a navigation hint, not proof of a full service path.
            identity = sample["request_id"]
            row = correlations.setdefault(identity, {"request_id": identity, "trace_ids": [], "evidence_ids": [],
                                                      "event_ids": [], "operations": [], "targets": [], "signals": []})
            for source, destination in (("trace_id", "trace_ids"), ("event_id", "event_ids"), ("operation", "operations"),
                                        ("target", "targets"), ("signal", "signals")):
                value = sample.get(source)
                if value and value not in row[destination]:
                    row[destination].append(value)
            if item.id not in row["evidence_ids"]:
                row["evidence_ids"].append(item.id)
    leading = None
    verification = next_steps[0]
    if candidates:
        candidate = candidates[0]
        leading = {"category": candidate["cause"], "supporting_evidence_ids": candidate["supporting"],
                   "counterevidence_ids": candidate["contradicting"],
                   "explanation": "The selected category has supporting observations; the incident's exact cause remains unconfirmed."}
        if candidate["cause"] == "authorization":
            sample = next(s for ref in candidate["supporting"] for s in authorization_samples(by_id[ref], bundle.start, bundle.end))
            leading["explanation"] = (f"Request {sample['request_id']} recorded an authorization failure for dynamodb:PutItem "
                                      f"on table {sample['target']} inside the incident window.")
            simulations = [by_id[r] for r in candidate["supporting"] if by_id[r].kind == "permission_simulation"]
            if simulations:
                leading["explanation"] += " A cited current-role simulation matches that action and target; it does not establish the actual caller or historical authorization."
            verification = (f"Ask the IAM/application owner to verify the actual principal for request {sample['request_id']}, "
                            f"dynamodb:PutItem, table {sample['target']}, and its incident-time policy/session context.")
    latest = {j["check"]: j for j in journal if j.get("action") == "check" and j.get("status") != "cached"}
    unavailable = [{"check": j["check"], "outcome": j["status"], "evidence_ids": j["new_evidence_ids"]}
                   for j in latest.values() if j["status"] in {"partial", "unavailable", "no_evidence"}]
    policy_observations = [{"evidence_id": e.id, "role": e.data.get("role"), "action": e.data.get("action"),
                            "target": e.data.get("target"), "decision": e.data.get("decision")}
                           for e in bundle.evidence if e.kind == "permission_simulation" and e.status in {"observed", "partial"}]
    return {"application": bundle.application, "function": function, "symptom": symptom,
            "start": bundle.start, "end": bundle.end, "leading_candidate": leading,
            "next_verification": verification, "incomplete_checks": unavailable,
            "policy_observations": policy_observations, "request_correlations": list(correlations.values())[:20],
            "limits": "Request/trace identifiers correlate recorded observations, not a complete distributed trace or verified network path."}


def summary_markdown(summary):
    def safe(value):
        value = html.escape(str(value).replace("\n", " ").replace("\r", " "), quote=False)
        return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", value)
    lines = ["## Incident handoff", "", f"Function: {safe(summary['function'])}", "",
             f"Reported symptom: {safe(summary['symptom'])}", ""]
    leading = summary["leading_candidate"]
    lines += [safe(leading["explanation"]) if leading else "No incident explanation was accepted from the available evidence.", "",
              "Next verification: " + safe(summary["next_verification"]), ""]
    for check in summary["incomplete_checks"]:
        lines.append(f"- Incomplete check: {safe(check['check'])} ({safe(check['outcome'])}); evidence: {safe(', '.join(check['evidence_ids']))}")
    if summary["request_correlations"]:
        lines += ["", "Request correlations (trace identifiers are not retrieved traces):", ""]
        for row in summary["request_correlations"]:
            lines.append(f"- Request {safe(row['request_id'])}; trace IDs: {safe(', '.join(row['trace_ids']) or 'unavailable')}; "
                         f"operations: {safe(', '.join(row['operations']) or 'unavailable')}; targets: {safe(', '.join(row['targets']) or 'unavailable')}")
    return "\n".join(lines) + "\n\n"
