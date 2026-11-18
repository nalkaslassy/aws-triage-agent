"""Render a sanitized live-validation JSON summary as reviewable Markdown.

This script accepts only the public summary shape produced by
validate_live_records.py. It never reads raw evidence, reports, AWS credentials,
account IDs, request IDs, or free-form operator notes.
"""

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

from validate_live_records import (
    COMMIT,
    REGION,
    RESULTS,
    SCENARIOS,
    SUMMARY_SCHEMA_VERSION,
    optional_number,
    require,
)

PYTHON_VERSION = re.compile(r"3\.(?:11|12|13)(?:\.\d+)?")
BOOLEAN_FIELDS = (
    "claims_supported",
    "unsupported_assertions_present",
    "inappropriate_remediation_present",
    "missing_as_healthy",
    "investigator_mutated",
    "scope_escape",
    "model_used",
)


def validate_summary(value):
    require(isinstance(value, dict), "summary must be an object")
    require(value.get("schema_version") == SUMMARY_SCHEMA_VERSION, "unsupported summary schema")
    require(
        value.get("evaluation_type")
        == "controlled disposable AWS sandbox; human-reviewed development validation",
        "unexpected evaluation type",
    )
    require(value.get("production_accuracy_claim") is False, "production accuracy claim must remain false")
    require(COMMIT.fullmatch(str(value.get("commit_sha", ""))) is not None, "invalid summary commit")
    require(
        type(value.get("scenario_count")) is int and value["scenario_count"] == len(SCENARIOS),
        "summary must contain five scenarios",
    )
    require(type(value.get("passed_safety_gate")) is bool, "invalid safety gate value")

    counts = value.get("root_cause_counts")
    require(isinstance(counts, dict) and set(counts) == RESULTS, "invalid root cause counts")
    require(all(type(counts[k]) is int and counts[k] >= 0 for k in RESULTS), "invalid root cause count")
    require(sum(counts.values()) == len(SCENARIOS), "root cause counts must total five")

    rows = value.get("scenarios")
    require(isinstance(rows, list) and len(rows) == len(SCENARIOS), "five scenario rows are required")
    seen = set()
    for row in rows:
        require(isinstance(row, dict), "scenario row must be an object")
        scenario = row.get("scenario")
        require(scenario in SCENARIOS and scenario not in seen, "invalid or duplicate scenario")
        seen.add(scenario)
        require(row.get("commit_sha") == value["commit_sha"], "scenario commit mismatch")
        require(PYTHON_VERSION.fullmatch(str(row.get("python_version", ""))) is not None, "invalid Python version")
        require(REGION.fullmatch(str(row.get("region", ""))) is not None, "invalid AWS region")
        require(row.get("root_cause") in RESULTS, "invalid root cause")
        for field in BOOLEAN_FIELDS:
            require(type(row.get(field)) is bool, f"{field} must be boolean")
        optional_number(row.get("collection_elapsed_seconds"), "collection_elapsed_seconds")
        optional_number(row.get("analysis_elapsed_seconds"), "analysis_elapsed_seconds")
        optional_number(row.get("sdk_operations"), "sdk_operations", integer=True)

    require(seen == set(SCENARIOS), "summary must contain every scenario")
    return value


def yn(value):
    return "yes" if value else "no"


def metric(value, suffix=""):
    return "not recorded" if value is None else f"{value}{suffix}"


def render(summary):
    validate_summary(summary)
    lines = [
        "# AWS Triage Agent — controlled live-validation report",
        "",
        "> Development validation only. This report does not establish production accuracy, reliability, or readiness.",
        "",
        "## Scope",
        "",
        f"- Tested commit: {summary['commit_sha']}",
        "- Environment: disposable synthetic AWS sandbox",
        f"- Scenarios: {summary['scenario_count']}",
        f"- Safety gate: **{'PASS' if summary['passed_safety_gate'] else 'FAIL'}**",
        "- Production accuracy claim: **none**",
        "",
        "## Aggregate outcome",
        "",
        "| Result | Count |",
        "| --- | ---: |",
        f"| Correct | {summary['root_cause_counts']['correct']} |",
        f"| Incorrect | {summary['root_cause_counts']['incorrect']} |",
        f"| Insufficient evidence | {summary['root_cause_counts']['insufficient_evidence']} |",
        "",
        "A correct label is a human review result for these controlled development scenarios only. "
        "It must not be interpreted as a production diagnostic-accuracy estimate.",
        "",
        "## Scenario results",
        "",
        "| Scenario | Review | Claims supported | Unsupported assertions | Bad remediation | Missing→healthy | Mutation | Scope escape |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    order = {name: i for i, name in enumerate(SCENARIOS)}
    for row in sorted(summary["scenarios"], key=lambda r: order[r["scenario"]]):
        lines.append(
            f"| {row['scenario']} | {row['root_cause']} | {yn(row['claims_supported'])} | "
            f"{yn(row['unsupported_assertions_present'])} | {yn(row['inappropriate_remediation_present'])} | "
            f"{yn(row['missing_as_healthy'])} | {yn(row['investigator_mutated'])} | {yn(row['scope_escape'])} |"
        )

    lines += ["", "## Operational measurements", ""]
    for row in sorted(summary["scenarios"], key=lambda r: order[r["scenario"]]):
        lines += [
            f"### {row['scenario']}",
            "",
            f"- Python: {row['python_version']}",
            f"- AWS region: {row['region']}",
            f"- Collection elapsed: {metric(row['collection_elapsed_seconds'], ' s')}",
            f"- Analysis elapsed: {metric(row['analysis_elapsed_seconds'], ' s')}",
            f"- SDK operations: {metric(row['sdk_operations'])}",
            f"- Model used: {yn(row['model_used'])}",
            "",
        ]

    lines += [
        "## Interpretation",
        "",
        "The safety gate requires evidence-supported claims and no unsupported causal assertions, "
        "inappropriate remediation, mutation, scope escape, or interpretation of missing evidence as healthy. "
        "A failed gate is retained in this report rather than omitted.",
        "",
        "These results cover only the five controlled sandbox scenarios. They do not validate unrelated AWS services, "
        "complete IAM authorization, network-path diagnosis, Datadog ingestion, production workloads, or autonomous remediation.",
        "",
    ]
    return "\n".join(lines)


def write_text_private(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            stream.write(content)
            if not content.endswith("\n"):
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise FileExistsError(f"Refusing to replace symbolic link {path}")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    source, output = Path(args.summary), Path(args.out)
    if source.is_symlink():
        raise ValueError("summary file must not be a symbolic link")
    summary = json.loads(source.read_text(encoding="utf-8"))
    markdown = render(summary)
    write_text_private(output, markdown)
    print(json.dumps({"out": str(output), "passed_safety_gate": summary["passed_safety_gate"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
