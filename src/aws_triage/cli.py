"""Offline analysis and opt-in AWS collection entry points."""

import argparse
import json
import os
import sys
from pathlib import Path

from .collect import AWSCollector
from .investigate import investigate, markdown
from .model import Bundle


def write_private(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Refuse accidental replacement, and avoid following an existing symlink.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidence-first AWS incident triage (prototype)")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Analyze an evidence bundle without network access")
    analyze.add_argument("bundle")
    analyze.add_argument("--format", choices=["markdown", "json"], default="markdown")
    analyze.add_argument("--out")
    collect = commands.add_parser("collect", help="Read explicitly configured AWS telemetry using your existing credentials")
    collect.add_argument("--manifest", required=True)
    collect.add_argument("--start", required=True)
    collect.add_argument("--end", required=True)
    collect.add_argument("--profile")
    collect.add_argument("--out", required=True)
    agent = commands.add_parser("agent", help="Bounded follow-up investigation; model inference is opt-in")
    agent_modes = agent.add_subparsers(dest="agent_mode", required=True)
    replay = agent_modes.add_parser("replay", help="Run a scripted local case without AWS or model calls")
    replay.add_argument("case")
    live = agent_modes.add_parser("run", help="Use Bedrock and scoped read-only AWS follow-ups")
    live.add_argument("bundle")
    live.add_argument("--manifest", required=True)
    live.add_argument("--function", required=True)
    live.add_argument("--symptom", required=True)
    live.add_argument("--profile")
    live.add_argument("--model-id", required=True)
    live.add_argument("--model-region")
    live.add_argument("--allow-model-data", action="store_true", help="Permit curated telemetry/identifiers to be sent to the selected Bedrock model")
    for mode in (replay, live):
        mode.add_argument("--max-steps", type=int, default=6)
        mode.add_argument("--seconds", type=int, default=60)
        mode.add_argument("--format", choices=["json", "markdown"], default="json")
        mode.add_argument("--out", required=True)
    sandbox = commands.add_parser("sandbox", help="Operator tools for the disposable sandbox; probe writes one synthetic order")
    sandbox_commands = sandbox.add_subparsers(dest="sandbox_command", required=True)
    manifest_cmd = sandbox_commands.add_parser("manifest", help="Create a manifest from sandbox stack outputs")
    manifest_cmd.add_argument("--outputs", required=True)
    manifest_cmd.add_argument("--out", required=True)
    probe_cmd = sandbox_commands.add_parser("probe", help="POST one synthetic order to the verified sandbox API")
    probe_cmd.add_argument("--manifest", required=True)
    probe_cmd.add_argument("--profile")
    probe_cmd.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "agent":
            from .agent import run_agent, agent_markdown
            from .followups import AWSFollowups, ReplayFollowups
            from .planner import BedrockPlanner, ReplayPlanner
            if Path(args.out).exists() or Path(args.out).is_symlink():
                raise FileExistsError("Output already exists")
            if type(args.max_steps) is not int or not 1 <= args.max_steps <= 10 or not 1 <= args.seconds <= 120:
                raise ValueError("Invalid investigation budget")
            if args.agent_mode == "replay":
                case = json.loads(Path(args.case).read_text())
                bundle = Bundle.from_dict(case["bundle"])
                manifest, function, symptom = case["manifest"], case["function"], case["symptom"]
                planner, backend = ReplayPlanner(case["decisions"]), ReplayFollowups(case["followups"])
            else:
                if not args.allow_model_data:
                    raise ValueError("Model data opt-in is required")
                import boto3
                from botocore.config import Config
                bundle = Bundle.from_dict(json.loads(Path(args.bundle).read_text()))
                manifest = json.loads(Path(args.manifest).read_text())
                function, symptom = args.function, args.symptom
                session = boto3.Session(profile_name=args.profile)
                backend = AWSFollowups(session, manifest, bundle, function, args.seconds)
                client = session.client("bedrock-runtime", region_name=args.model_region or manifest["region"],
                                        config=Config(connect_timeout=5, read_timeout=20, retries={"total_max_attempts": 1}))
                planner = BedrockPlanner(client, args.model_id, allow_model_data=True)
            result = run_agent(bundle, manifest, function, symptom, planner, backend, args.max_steps, args.seconds)
            value = agent_markdown(result) if args.format == "markdown" else json.dumps(result, indent=2) + "\n"
            write_private(args.out, value)
            print(f"Investigation written to {args.out}; stop reason: {result['stop_reason']}.")
        elif args.command == "sandbox":
            from .sandbox import manifest_from_stack, probe
            # Validate the output path before a request with side effects.
            if Path(args.out).exists() or Path(args.out).is_symlink():
                raise FileExistsError("Output already exists")
            if args.sandbox_command == "manifest":
                value = manifest_from_stack(json.loads(Path(args.outputs).read_text()))
            else:
                import boto3
                manifest = json.loads(Path(args.manifest).read_text())
                value = probe(boto3.Session(profile_name=args.profile), manifest)
            write_private(args.out, json.dumps(value, indent=2) + "\n")
            print(f"Sandbox result written to {args.out}.")
        elif args.command == "collect":
            import boto3
            manifest = json.loads(Path(args.manifest).read_text())
            bundle = AWSCollector(boto3.Session(profile_name=args.profile), manifest, args.start, args.end).collect()
            write_private(args.out, json.dumps(bundle.to_dict(), indent=2, default=str) + "\n")
            print(f"Evidence written to {args.out}. Treat it as sensitive operational data.")
        else:
            bundle = Bundle.from_dict(json.loads(Path(args.bundle).read_text()))
            report = investigate(bundle)
            value = markdown(report) if args.format == "markdown" else json.dumps(report.to_dict(), indent=2) + "\n"
            if args.out:
                write_private(args.out, value)
            else:
                print(value, end="")
        return 0
    except Exception as error:
        print(f"Unable to complete triage ({type(error).__name__}). Check input schema, output path, and optional AWS dependencies.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
