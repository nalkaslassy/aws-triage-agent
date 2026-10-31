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
        if args.command == "sandbox":
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
