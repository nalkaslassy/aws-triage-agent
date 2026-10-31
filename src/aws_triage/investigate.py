"""Deterministic first-pass triage. Telemetry never becomes executable instructions."""

from .model import Bundle, Finding, Report, utc_time
from .api_findings import api_findings
from datetime import datetime, timezone
import html
import re


def investigate(bundle: Bundle) -> Report:
    report = Report(bundle.application, bundle.start, bundle.end)
    for item in bundle.evidence:
        if item.status != "observed":
            report.gaps.append(
                f"{item.id}: {item.kind} for {item.resource}: {item.status}. "
                + item.data.get("reason", "Collection is incomplete.")
            )
        # Partial metric counts are unsafe denominators. Partial log samples can
        # still establish that a particular error was seen, never its frequency.
        if item.status not in {"observed", "partial"}:
            continue
        if item.kind == "lambda_metrics" and item.status == "observed":
            for metric, title, explanation, steps in [
                ("Errors", "Lambda execution errors observed",
                 "Failed executions occurred in the incident window. The count alone does not establish an outage or its cause.",
                 ["Correlate failed request IDs with application logs and downstream traces.",
                  "Compare error rate and traffic with a matched baseline before declaring a spike."]),
                ("Throttles", "Lambda throttling observed",
                 "Some invocation attempts were throttled. The binding limit and customer impact remain unverified.",
                 ["Check function concurrency, reserved concurrency, account limits, and event-source limits.",
                  "Compare affected request timing and retry behavior before recommending a capacity change."]),
            ]:
                value = item.data.get(metric)
                if value is not None and value > 0:
                    report.findings.append(Finding(title, "confirmed_observation", explanation,
                                                   [item.id], steps, "Application / platform team"))
            missing = [m for m in ("Errors", "Invocations", "Throttles") if item.data.get(m) is None]
            if missing:
                report.gaps.append(f"{item.id}: No datapoints for {', '.join(missing)}; missing data is not zero.")
        if item.kind == "log_signals":
            report.gaps.append(f"{item.id}: Log selection is bounded and format-dependent; sampled counts are not application-wide error totals.")
            if item.data.get("unverified_mentions", 0):
                report.gaps.append(f"{item.id}: Keyword mentions without failure context were excluded from diagnosis.")
            for signal, title, reason, steps, owner in [
                ("access_denied", "Authorization failure appears in application logs",
                 "A permissions problem is a candidate cause. A log message does not identify the responsible policy layer or prove causality.",
                 ["Verify the failing request's actual principal, action, resource, and timestamp.",
                  "Inspect relevant identity/resource policies, explicit denies, boundaries, organization controls, and endpoint/KMS policies as applicable."],
                 "Application / IAM team"),
                ("timeout", "Timeout appears in application logs",
                 "A timeout can originate in networking, dependency latency, or application behavior; the cause is unresolved.",
                 ["Correlate request traces with downstream timing.",
                  "Check DNS, destination port, routing in both directions, and access controls from the affected network."],
                 "Application / network team"),
                ("exception", "Application exception appears in logs",
                 "An exception was sampled. A deployment regression is possible but has not been established.",
                 ["Inspect the original exception and request ID in the logging system.",
                  "Compare deployment timing and a working version before proposing a rollback."],
                 "Application team"),
                ("resource_missing", "A dependency reports a missing resource",
                 "A dependency returned ResourceNotFoundException. A wrong target name, region, or missing resource is possible; the exact cause remains unverified.",
                 ["Compare the request's actual dependency name and region against the intended configuration.",
                  "Check whether the intended resource exists before changing permissions."],
                 "Application / platform team"),
            ]:
                if item.data.get(signal) is not None and item.data[signal] > 0:
                    report.findings.append(Finding(title, "hypothesis", reason, [item.id], steps, owner))
        if item.kind == "vpn_connections":
            report.gaps.append(
                f"{item.id}: VPN sessions are a current snapshot, not historical proof of user reachability. "
                "Compare affected and working cohorts using authorized identity and client-side evidence."
            )
        if item.kind == "lambda_configuration" and item.status == "observed":
            actual, expected = item.data.get("orders_table"), item.data.get("expected_table")
            if actual and expected and actual != expected:
                report.findings.append(Finding(
                    "Configured table differs from the application manifest", "confirmed_observation",
                    "The current ORDERS_TABLE setting differs from the manifest's intended target. "
                    "The manifest may be stale; this snapshot does not prove which configuration was active at incident onset.",
                    [item.id], ["Verify the intended target with the application owner.",
                                "Correlate the mismatch with failing dependency requests and deployment timing."],
                    "Application / platform team"))
        if item.kind == "lambda_concurrency" and item.status == "observed":
            if item.data.get("reserved_concurrency") == 0:
                report.findings.append(Finding(
                    "Function reserved concurrency is currently zero", "confirmed_observation",
                    "The current configuration prevents this function from processing invocations. "
                    "This may be intentional; historical configuration and the cause of the change remain unverified.",
                    [item.id], ["Confirm whether disabling invocation was intentional.",
                                "Correlate throttles and incident timing before restoring the intended concurrency configuration."],
                    "Application / platform team"))
        if item.kind in {"lambda_configuration", "lambda_concurrency", "security_group_configuration", "vpn_routes", "vpn_authorization"}:
            report.gaps.append(f"{item.id}: Current configuration snapshot; it does not establish historical incident-time configuration.")
    api_findings(bundle, report)
    correlate_targets(bundle, report)
    by_id = {item.id: item for item in bundle.evidence}
    for finding in report.findings:
        if not finding.resource:
            finding.resource = ", ".join(dict.fromkeys(by_id[i].resource for i in finding.evidence_ids))
    report.evidence = [evidence_reference(item) for item in bundle.evidence]
    if not report.findings:
        report.gaps.append("No supported failure explanation was established. This does not establish application or network health.")
    report.gaps.append(
        "Client/corporate VPN, DNS, and firewall behavior is unverified unless evidence from that location is supplied. "
        "Requests blocked before reaching the application may leave no application error."
    )
    return report


def markdown(report: Report) -> str:
    def safe(value):
        value = html.escape(str(value).replace("\n", " ").replace("\r", " "), quote=False)
        return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", value)

    lines = [f"# Investigation: {safe(report.application)}", "",
             f"Window: {safe(report.start)} to {safe(report.end)}", "",
             "Status: first-pass triage; remediation requires engineer review.", ""]
    for finding in report.findings:
        references = ", ".join(f"[{safe(i)}](#{i.lower()})" for i in finding.evidence_ids)
        lines += [f"## {safe(finding.title)}", "",
                  f"Classification: {finding.classification}; evidence: {references}", "",
                  finding.explanation, "", f"Suggested owner: {finding.owner}", ""]
        lines += [f"Affected resource: {safe(finding.resource)}", ""]
        lines += [f"- {step}" for step in finding.next_steps]
        lines.append("")
    lines += ["## Visibility gaps and remaining questions", ""]
    lines += [f"- {safe(gap)}" for gap in report.gaps]
    lines += ["", "## Evidence index", "",
              "Console links open the relevant AWS service. Use the listed resource, time, and request identifiers to locate the evidence; these links do not pin an individual event.", ""]
    for item in report.evidence:
        lines += [f"### {safe(item['id'])}", "", f"Resource: {safe(item['resource'])}",
                  f"Source: {safe(item['source'])}; status: {safe(item['status'])}; collected: {safe(item['collected_at'])}", ""]
        if item.get("source_url"):
            url = item["source_url"].replace("(", "%28").replace(")", "%29")
            lines += [f"[Open AWS console]({url})", ""]
        for key, value in item["details"].items():
            lines.append(f"- {safe(key)}: {safe(value)}")
        lines.append("")
    return "\n".join(lines) + "\n"


def evidence_reference(item):
    """Expose only useful, bounded context, never arbitrary imported messages."""
    fields = {
        "lambda_metrics": ("Errors", "Invocations", "Throttles"),
        "lambda_configuration": ("orders_table", "expected_table", "Role", "LastModified"),
        "lambda_concurrency": ("reserved_concurrency",),
        "api_metrics": ("window", "start", "end", "requests", "server_errors", "client_errors", "latency_ms", "integration_latency_ms"),
        "log_signals": ("access_denied", "timeout", "exception", "resource_missing", "unverified_mentions"),
    }.get(item.kind, ())
    details = {key: item.data[key] for key in fields if key in item.data}
    if item.kind == "log_signals":
        for i, sample in enumerate(item.data.get("samples", []), 1):
            parts = [f"{key}={sample[key]}" for key in ("signal", "event_id", "stream", "request_id", "operation", "target", "error_code")
                     if sample.get(key) is not None]
            if sample.get("timestamp") is not None:
                try:
                    parts.append("UTC=" + datetime.fromtimestamp(sample["timestamp"] / 1000, timezone.utc).isoformat())
                except (OverflowError, OSError, ValueError):
                    parts.append("timestamp outside supported calendar range")
            details[f"sample {i}"] = "; ".join(parts)
    return {"id": item.id, "kind": item.kind, "resource": item.resource, "source": item.source,
            "collected_at": item.collected_at, "status": item.status, "source_url": item.source_url, "details": details}


def correlate_targets(bundle, report):
    for config in bundle.evidence:
        if config.kind != "lambda_configuration" or config.status != "observed":
            continue
        actual, expected = config.data.get("orders_table"), config.data.get("expected_table")
        if not actual or not expected or actual == expected:
            continue
        for log in bundle.evidence:
            if (log.kind != "log_signals" or log.status not in {"observed", "partial"}
                    or log.data.get("function_name") != config.resource):
                continue
            samples = [s for s in log.data.get("samples", []) if s.get("signal") == "resource_missing"
                       and s.get("operation") == "PutItem" and s.get("target") == actual
                       and s.get("request_id") and s.get("timestamp") is not None
                       and int(utc_time(bundle.start).timestamp() * 1000)
                       <= s["timestamp"] < int(utc_time(bundle.end).timestamp() * 1000)]
            if samples:
                report.findings.append(Finding(
                    "Table mismatch may explain the recorded dependency failure", "hypothesis",
                    "A failed PutItem request targets the same table that currently differs from the manifest, for the same function and incident window. "
                    "This links two observations; a stale manifest or a configuration change after the failure could still explain the mismatch.",
                    [config.id, log.id], ["Verify the intended table and incident-time configuration before proposing a correction."],
                    "Application / platform team", config.resource))
