"""Interpret API observations without promoting correlation to root cause."""

from .model import Finding, utc_time


def error_rate(item):
    if item.status != "observed":
        return None
    requests, errors = item.data.get("requests"), item.data.get("server_errors")
    if requests is None or errors is None or requests <= 0 or errors > requests:
        return None
    return errors / requests


def api_findings(bundle, report):
    items = [e for e in bundle.evidence if e.kind == "api_metrics"]
    for item in items:
        if item.data["window"] != "incident" or item.status not in {"observed", "partial"}:
            continue
        if (utc_time(item.data["start"]) != utc_time(bundle.start)
                or utc_time(item.data["end"]) != utc_time(bundle.end)):
            report.gaps.append(f"{item.id}: API incident window differs from this investigation; comparison skipped.")
            continue
        duration = utc_time(item.data["end"]) - utc_time(item.data["start"])
        baselines = [e for e in items if e.resource == item.resource and e.data["window"] == "baseline"
                     and utc_time(e.data["end"]) == utc_time(item.data["start"])
                     and utc_time(e.data["end"]) - utc_time(e.data["start"]) == duration]
        baseline = baselines[0] if len(baselines) == 1 else None
        rate, before = error_rate(item), error_rate(baseline) if baseline else None
        errors = item.data.get("server_errors")
        client_errors = item.data.get("client_errors")
        references = [item.id]
        comparison = ""
        if rate is not None:
            comparison = f" Observed 5xx rate: {rate:.2%} ({errors:g}/{item.data['requests']:g} requests)."
        else:
            report.gaps.append(f"{item.id}: A reliable API error rate could not be calculated; counts may be missing, inconsistent, zero-volume, or partial.")
        if before is not None and rate is not None:
            comparison += f" Preceding equal-length baseline: {before:.2%}; change {(rate - before) * 100:+.2f} percentage points."
            references.append(baseline.id)
        else:
            report.gaps.append(f"{item.id}: A complete, unique, adjacent baseline with a valid error rate is unavailable.")
        if errors is not None and errors > 0:
            report.findings.append(Finding(
                "API server-side errors observed", "confirmed_observation",
                f"The API stage recorded {errors:g} server-side errors.{comparison} "
                "These are API responses, not Lambda execution errors; cause and affected user population remain unresolved.",
                references, ["Correlate failed API requests with application logs and dependency traces.",
                             "Verify that this stage and baseline represent the reported impact."],
                "Application / platform team", item.resource))
        if client_errors is not None and client_errors > 0:
            report.findings.append(Finding(
                "API client-side errors observed", "confirmed_observation",
                f"The API stage recorded {client_errors:g} client-side errors. These may include authorization, routing, validation, or expected client failures; no specific cause is established.",
                [item.id], ["Inspect the failed response codes and affected request paths before attributing the failures to IAM or networking."],
                "Application / platform team", item.resource))
        if baseline and item.status == baseline.status == "observed":
            now, old = item.data.get("latency_ms"), baseline.data.get("latency_ms")
            volume, previous_volume = item.data.get("requests"), baseline.data.get("requests")
            if (now is not None and old is not None and old > 0 and now >= 2 * old
                    and volume is not None and previous_volume is not None and min(volume, previous_volume) >= 20):
                report.findings.append(Finding(
                    "API mean latency increased against the adjacent baseline", "hypothesis",
                    f"Mean latency rose from {old:g} ms to {now:g} ms. "
                    "This uses a twofold-increase heuristic with at least twenty requests in both windows; "
                    "it is not a statistical anomaly test or proof of an outage. Traffic mix and baseline suitability are unverified.",
                    [item.id, baseline.id], ["Compare API latency with integration latency, traffic volume, and downstream traces."],
                    "Application / platform team", item.resource))
        report.gaps.append(f"{item.id}: API metrics use ApiName/Stage dimensions; name uniqueness and affected endpoints/users are unverified. The adjacent baseline may not represent normal behavior.")
