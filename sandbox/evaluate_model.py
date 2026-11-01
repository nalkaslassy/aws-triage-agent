"""Default preflight makes no model calls. Explicit flags enable paid Bedrock evaluation."""

import argparse
import json
from pathlib import Path

from aws_triage.cli import write_private
from aws_triage.evaluation import load_suite, evaluate_suite


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--run-bedrock", action="store_true")
    parser.add_argument("--allow-model-data", action="store_true")
    parser.add_argument("--model-id")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--profile")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args(argv)
    if Path(args.out).exists() or Path(args.out).is_symlink():
        raise FileExistsError("Evaluation output already exists")
    directory = Path(__file__).resolve().parents[1] / "evaluation"
    packets, _ = load_suite(directory)
    if not 1 <= args.limit <= 5 or not 1 <= args.repeat <= 3:
        raise ValueError("Invalid evaluation run limit")
    if not args.run_bedrock:
        result = {"model_evaluation": "not_run", "model_calls": 0, "cases_validated": len(packets),
                  "input_hashes": {identity: digest for identity, _, digest in packets},
                  "note": "Preflight only. No model quality score or live AWS validation is available."}
    else:
        if not args.allow_model_data or not args.model_id:
            raise ValueError("Bedrock evaluation requires model ID and explicit data opt-in")
        import boto3
        from botocore.config import Config
        from aws_triage.planner import BedrockPlanner
        client = boto3.Session(profile_name=args.profile).client(
            "bedrock-runtime", region_name=args.region,
            config=Config(connect_timeout=5, read_timeout=20, retries={"total_max_attempts": 1}))
        result = evaluate_suite(directory, lambda: BedrockPlanner(client, args.model_id, True), args.limit, args.repeat)
        result["model_id"] = args.model_id
        result["region"] = args.region
    write_private(args.out, json.dumps(result, indent=2) + "\n")
    print(f"Evaluation output written to {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
