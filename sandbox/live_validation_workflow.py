"""Prepare and finalize controlled live-validation records without AWS access.

This helper never contacts AWS and never changes sandbox state. It manages local
record files around the operator-run validation protocol:
  1. init: create five scenario record stubs tied to one commit/region.
  2. hash: populate evidence/report SHA-256 values for completed local artifacts.
  3. finalize: run the existing verifier and write a sanitized public summary.

Operator ground truth and human review remain manual.
"""

import argparse
import json
import sys
from pathlib import Path

from validate_live_records import (
    RECORD_SCHEMA_VERSION,
    SCENARIOS,
    artifact_path,
    sha256_file,
    summarize,
    write_json_private,
)


def refuse_existing(path):
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite {path}")


def new_record(scenario, commit_sha, python_version, region):
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "scenario": scenario,
        "commit_sha": commit_sha,
        "python_version": python_version,
        "region": region,
        "evidence_path": f"{scenario}-evidence.json",
        "evidence_sha256": "",
        "report_path": f"{scenario}-report.md",
        "report_sha256": "",
        "review": {
            "root_cause": "",
            "claims_supported": False,
            "unsupported_assertions": "",
            "missing_as_healthy": False,
            "inappropriate_remediation": "",
            "investigator_mutated": False,
            "scope_escape": False,
        },
        "metrics": {
            "collection_elapsed_seconds": None,
            "analysis_elapsed_seconds": None,
            "sdk_operations": None,
            "model_used": False,
        },
        "notes": "",
    }


def init_records(output, commit_sha, python_version, region):
    refuse_existing(output)
    records = [new_record(s, commit_sha, python_version, region) for s in SCENARIOS]
    write_json_private(output, records)
    return records


def load_records(path):
    if path.is_symlink():
        raise ValueError("records file must not be a symbolic link")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("records file must contain a JSON array")
    return value


def populate_hashes(path):
    records = load_records(path)
    base = path.parent
    for record in records:
        for path_key, hash_key in (("evidence_path", "evidence_sha256"), ("report_path", "report_sha256")):
            artifact = artifact_path(base, record.get(path_key), path_key)
            record[hash_key] = sha256_file(artifact)
    write_json_private(path, records, overwrite=True)
    return records


def finalize(records_path, output):
    refuse_existing(output)
    records = load_records(records_path)
    result = summarize(records, records_path.parent)
    write_json_private(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create five local scenario record stubs")
    init.add_argument("--records", required=True)
    init.add_argument("--commit", required=True)
    init.add_argument("--python-version", required=True)
    init.add_argument("--region", required=True)

    hashes = commands.add_parser("hash", help="Hash completed local evidence/report artifacts into the records file")
    hashes.add_argument("--records", required=True)

    finish = commands.add_parser("finalize", help="Verify records and write sanitized public summary")
    finish.add_argument("--records", required=True)
    finish.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    records_path = Path(args.records)

    if args.command == "init":
        records = init_records(records_path, args.commit, args.python_version, args.region)
        print(json.dumps({"created": str(records_path), "scenario_count": len(records)}, indent=2))
    elif args.command == "hash":
        records = populate_hashes(records_path)
        print(json.dumps({"updated": str(records_path), "scenario_count": len(records)}, indent=2))
    else:
        result = finalize(records_path, Path(args.out))
        print(json.dumps({
            "passed_safety_gate": result["passed_safety_gate"],
            "scenario_count": result["scenario_count"],
            "out": args.out,
        }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        print(f"Unable to complete live-validation workflow: {error}", file=sys.stderr)
        raise SystemExit(2)
