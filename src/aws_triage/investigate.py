"""Deterministic first-pass triage. Telemetry never becomes executable instructions."""

from .model import Bundle, Finding, Report


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
            ]:
                if item.data.get(signal, 0) > 0:
                    report.findings.append(Finding(title, "hypothesis", reason, [item.id], steps, owner))
        if item.kind == "vpn_connections":
            report.gaps.append(
                f"{item.id}: VPN sessions are a current snapshot, not historical proof of user reachability. "
                "Compare affected and working cohorts using authorized identity and client-side evidence."
            )
    if not report.findings:
        report.gaps.append("No supported failure explanation was established. This does not establish application or network health.")
    report.gaps.append(
        "Client/corporate VPN, DNS, and firewall behavior is unverified unless evidence from that location is supplied. "
        "Requests blocked before reaching the application may leave no application error."
    )
    return report


def markdown(report: Report) -> str:
    def safe(value):
        # Keep untrusted resource labels from creating extra report sections.
        return str(value).replace("\n", " ").replace("\r", " ").replace("`", "'").replace("<", "&lt;").replace(">", "&gt;")

    lines = [f"# Investigation: {safe(report.application)}", "",
             f"Window: {safe(report.start)} to {safe(report.end)}", "",
             "Status: first-pass triage; remediation requires engineer review.", ""]
    for finding in report.findings:
        lines += [f"## {safe(finding.title)}", "",
                  f"Classification: {finding.classification}; evidence: {', '.join(finding.evidence_ids)}", "",
                  finding.explanation, "", f"Suggested owner: {finding.owner}", ""]
        lines += [f"- {step}" for step in finding.next_steps]
        lines.append("")
    lines += ["## Visibility gaps and remaining questions", ""]
    lines += [f"- {safe(gap)}" for gap in report.gaps]
    return "\n".join(lines) + "\n"
