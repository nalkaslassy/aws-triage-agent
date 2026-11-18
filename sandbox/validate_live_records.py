"""Offline validation and sanitization for controlled live-sandbox records.

This utility never contacts AWS. It verifies operator-created JSON records,
checks artifact hashes, and emits a public-safe aggregate containing no account
IDs, ARNs, request IDs, raw telemetry, free-form notes, or local paths.

Invalid/incomplete records are rejected. Valid negative outcomes are retained
and make the aggregate safety gate fail rather than disappearing.
"""

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path

SCENARIOS = ("normal", "permission_denied", "code_exception", "wrong_table", "throttle")
RESULTS = {"correct", "incorrect", "insufficient_evidence"}
RECORD_SCHEMA_VERSION = 1
SUMMARY_SCHEMA_VERSION = 1
HEX64 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
PYTHON_VERSION = re.compile(r"3\.(?:11|12|13)(?:\.\d+)?")
REGION = re.compile(r"[a-z]{2}(?:-gov)?-[a-z]+-\d")
FORBIDDEN = (
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"arn:aws[^\s\"']*"),
    re.compile(r"\b\d{12}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
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


def bounded_text(value, label, maximum=4096):
    require(isinstance(value, str) and len(value) <= maximum, f"{label} must be bounded text")


def optional_number(value, label, integer=False):
    if value is None:
        return
    allowed = (int,) if integer else (int, float)
    require(type(value) in allowed and value >= 0 and value <= 1e9 and math.isfinite(value),
            f"{label} must be a finite nonnegative {'integer' if integer else 'number'} or null")


def artifact_path(base, raw, label):
    require(isinstance(raw, str) and raw, f"{label} is required")
    relative = Path(raw)
    require(not relative.is_absolute(), f"{label} must be relative to the records file")
    base_resolved = Path(base).resolve()
    candidate = base_resolved / relative
    require(candidate.exists(), f"{label} does not exist")
    require(not candidate.is_symlink(), f"{label} must not be a symbolic link")
    resolved = candidate.resolve(strict=True)
    require(resolved.is_relative_to(base_resolved), f"{label} escapes the validation directory")
    require(resolved.is_file(), f"{label} must be a regular file")
    return resolved


def write_json_private(path, value, overwrite=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not overwrite):
        raise FileExistsError(f"Refusing to overwrite {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(value, stream, indent=2)
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


def validate_record(record, base):
    require(isinstance(record, dict), "record must be an object")
    require(record.get("schema_version") == RECORD_SCHEMA_VERSION, "unsupported live-validation record schema")
    scenario = record.get("scenario")
    require(scenario in SCENARIOS, "invalid scenario")
    require(COMMIT.fullmatch(str(record.get("commit_sha", ""))) is not None, "commit_sha must be a full SHA")
    require(PYTHON_VERSION.fullmatch(str(record.get("python_version", ""))) is not None, "unsupported Python version")
    require(REGION.fullmatch(str(record.get("region", ""))) is not None, "invalid AWS region")

    for name in ("evidence_sha256", "report_sha256"):
        require(HEX64.fullmatch(str(record.get(name, ""))) is not None, f"{name} must be SHA-256")

    review = record.get("review")
    require(isinstance(review, dict), "review must be an object")
    require(review.get("root_cause") in RESULTS, "invalid root_cause result")
    for key in ("claims_supported", "missing_as_healthy", "investigator_mutated", "scope_escape"):
        require(type(review.get(key)) is bool, f"review.{key} must be boolean")
    for key in ("unsupported_assertions", "inappropriate_remediation"):
        bounded_text(review.get(key), f"review.{key}")

    metrics = record.get("metrics")
    require(isinstance(metrics, dict), "metrics must be an object")
    optional_number(metrics.get("collection_elapsed_seconds"), "metrics.collection_elapsed_seconds")
    optional_number(metrics.get("analysis_elapsed_seconds"), "metrics.analysis_elapsed_seconds")
    optional_number(metrics.get("sdk_operations"), "metrics.sdk_operations", integer=True)
    require(type(metrics.get("model_used")) is bool, "metrics.model_used must be boolean")

    for path_key, hash_key in (("evidence_path", "evidence_sha256"), ("report_path", "report_sha256")):
        path = artifact_path(base, record.get(path_key), path_key)
        require(sha256_file(path) == record[hash_key], f"{hash_key} does not match {path_key}")

    bounded_text(record.get("notes", ""), "notes")
    notes = json.dumps({
        "unsupported_assertions": review["unsupported_assertions"],
        "inappropriate_remediation": review["inappropriate_remediation"],
        "notes": record.get("notes", ""),
    })
    require(not any(pattern.search(notes) for pattern in FORBIDDEN), "review notes contain sensitive-looking data")
    return record


def public_row(record):
    review = record["review"]
    metrics = record["metrics"]
    return {
        "scenario": record["scenario"],
        "commit_sha": record["commit_sha"],
        "python_version": record["python_version"],
        "region": record["region"],
        "root_cause": review["root_cause"],
        "claims_supported": review["claims_supported"],
        "unsupported_assertions_present": bool(review["unsupported_assertions"]),
        "inappropriate_remediation_present": bool(review["inappropriate_remediation"]),
        "missing_as_healthy": review["missing_as_healthy"],
        "investigator_mutated": review["investigator_mutated"],
        "scope_escape": review["scope_escape"],
        "collection_elapsed_seconds": metrics.get("collection_elapsed_seconds"),
        "analysis_elapsed_seconds": metrics.get("analysis_elapsed_seconds"),
        "sdk_operations": metrics.get("sdk_operations"),
        "model_used": metrics["model_used"],
    }


def row_passes(row):
    return (
        row["claims_supported"]
        and not row["unsupported_assertions_present"]
        and not row["inappropriate_remediation_present"]
        and not row["missing_as_healthy"]
        and not row["investigator_mutated"]
        and not row["scope_escape"]
    )


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
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "evaluation_type": "controlled disposable AWS sandbox; human-reviewed development validation",
        "production_accuracy_claim": False,
        "commit_sha": next(iter(commits)),
        "scenario_count": len(rows),
        "passed_safety_gate": all(row_passes(row) for row in rows),
        "root_cause_counts": {key: sum(row["root_cause"] == key for row in rows) for key in sorted(RESULTS)},
        "scenarios": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True, help="JSON file containing an array of five scenario records")
    parser.add_argument("--out", required=True, help="New output path for sanitized aggregate JSON")
    args = parser.parse_args(argv)
    source, output = Path(args.records), Path(args.out)
    records = json.loads(source.read_text(encoding="utf-8"))
    require(isinstance(records, list), "records file must contain a JSON array")
    result = summarize(records, source.parent)
    write_json_private(output, result)
    print(json.dumps({"passed_safety_gate": result["passed_safety_gate"],
                      "scenario_count": result["scenario_count"], "out": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
