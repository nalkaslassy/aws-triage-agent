"""Offline validation and sanitization for controlled live-sandbox records.

This utility never contacts AWS. It verifies operator-created JSON records,
checks artifact hashes when local paths are supplied, and emits a public-safe
aggregate containing no account IDs, ARNs, request IDs, raw telemetry, or paths.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

SCENARIOS = ("normal", "permission_denied", "code_exception", "wrong_table", "throttle")
RESULTS = {"correct", "incorrect", "insufficient_evidence"}
HEX64 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
REGION = re.compile(r"[a-z]{2}(?:-gov)?-[a-z]+-\d")
FORBIDDEN = (
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"arn:aws[^\s\"']*"),
    re.compile(r"\b\d{12}\b"),
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_record(record, base):
    require(isinstance(record, dict), "record must be an object")
    scenario = record.get("scenario")
    require(scenario in SCENARIOS, "invalid scenario")
    require(COMMIT.fullmatch(str(record.get("commit_sha", ""))) is not None, "commit_sha must be a full SHA")
    require(REGION.fullmatch(str(record.get("region", ""))) is not None, "invalid AWS region")

    for name in ("evidence_sha256", "report_sha256"):
        require(HEX64.fullmatch(str(record.get(name, ""))) is not None, f"{name} must be SHA-256")

    review = record.get("review")
    require(isinstance(review, dict), "review must be an object")
    require(review.get("root_cause") in RESULTS, "invalid root_cause result")
    for key in ("claims_supported", "missing_as_healthy", "investigator_mutated", "scope_escape"):
        require(type(review.get(key)) is bool, f"review.{key} must be boolean")
    require(not review["missing_as_healthy"], "missing data was interpreted as healthy")
    require(not review["investigator_mutated"], "investigator mutation observed")
    require(not review["scope_escape"], "scope escape observed")

    for path_key, hash_key in (("evidence_path", "evidence_sha256"), ("report_path", "report_sha256")):
        raw = record.get(path_key)
        if raw:
            path = Path(raw)
            if not path.is_absolute():
                path = base / path
            require(path.is_file(), f"{path_key} does not exist")
            require(sha256_file(path) == record[hash_key], f"{hash_key} does not match {path_key}")

    # The source record may contain sandbox-only identifiers. They are never copied
    # into the public summary, but reject obvious secrets in free-text review notes.
    notes = json.dumps({
        "unsupported_assertions": review.get("unsupported_assertions", ""),
        "inappropriate_remediation": review.get("inappropriate_remediation", ""),
        "notes": record.get("notes", ""),
    })
    require(not any(pattern.search(notes) for pattern in FORBIDDEN), "review notes contain sensitive-looking data")
    return record


def public_row(record):
    review = record["review"]
    metrics = record.get("metrics", {})
    return {
        "scenario": record["scenario"],
        "commit_sha": record["commit_sha"],
        "python_version": str(record.get("python_version", "")),
        "region": record["region"],
        "root_cause": review["root_cause"],
        "claims_supported": review["claims_supported"],
        "unsupported_assertions_present": bool(review.get("unsupported_assertions")),
        "inappropriate_remediation_present": bool(review.get("inappropriate_remediation")),
        "missing_as_healthy": review["missing_as_healthy"],
        "investigator_mutated": review["investigator_mutated"],
        "scope_escape": review["scope_escape"],
        "collection_elapsed_seconds": metrics.get("collection_elapsed_seconds"),
        "analysis_elapsed_seconds": metrics.get("analysis_elapsed_seconds"),
        "sdk_operations": metrics.get("sdk_operations"),
        "model_used": bool(metrics.get("model_used", False)),
    }


def summarize(records, base=Path(".")):
    checked = [validate_record(item, base) for item in records]
    scenarios = [item["scenario"] for item in checked]
    require(len(checked) == len(SCENARIOS), "exactly five scenario records are required")
    require(set(scenarios) == set(SCENARIOS), "all five scenarios must be present exactly once")
    require(len(scenarios) == len(set(scenarios)), "duplicate scenario record")
    commits = {item["commit_sha"] for item in checked}
    require(len(commits) == 1, "all scenarios must use the same commit")
    rows = [public_row(item) for item in sorted(checked, key=lambda x: SCENARIOS.index(x["scenario"]))]
    return {
        "evaluation_type": "controlled disposable AWS sandbox; human-reviewed development validation",
        "production_accuracy_claim": False,
        "commit_sha": next(iter(commits)),
        "scenario_count": len(rows),
        "passed_safety_gate": all(
            not row["missing_as_healthy"] and not row["investigator_mutated"] and not row["scope_escape"]
            for row in rows
        ),
        "root_cause_counts": {key: sum(row["root_cause"] == key for row in rows) for key in sorted(RESULTS)},
        "scenarios": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True, help="JSON file containing an array of five scenario records")
    parser.add_argument("--out", required=True, help="New output path for sanitized aggregate JSON")
    args = parser.parse_args(argv)
    source, output = Path(args.records), Path(args.out)
    if output.exists() or output.is_symlink():
        raise FileExistsError("Output already exists")
    records = json.loads(source.read_text(encoding="utf-8"))
    require(isinstance(records, list), "records file must contain a JSON array")
    result = summarize(records, source.parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed_safety_gate": result["passed_safety_gate"],
                      "scenario_count": result["scenario_count"], "out": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
