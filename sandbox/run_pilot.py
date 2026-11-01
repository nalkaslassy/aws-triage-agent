"""Prepare or explicitly execute a recorded Bedrock comparison; no AWS deployment."""
import argparse
import json
from pathlib import Path

from aws_triage.cli import write_private
from aws_triage.pilot import BasicBedrockPlanner, digest, execute_plan, run_plan, rules_baselines
from aws_triage.planner import BedrockPlanner
from aws_triage.evaluation import load_suite


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='New or matching resumable run directory')
    parser.add_argument('--run-bedrock', action='store_true')
    parser.add_argument('--allow-model-data', action='store_true')
    parser.add_argument('--model-id')
    parser.add_argument('--profile')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--limit', type=int, default=1)
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--seed', type=int, default=20261101)
    args = parser.parse_args(argv)
    suite = Path(__file__).resolve().parents[1] / 'pilot'
    plan = run_plan(suite, args.limit, args.repeat, args.seed)
    packets, rubric = load_suite(suite)
    code = {p.name: digest(p.read_text()) for p in (suite.parent / 'src/aws_triage').glob('*.py')}
    config = {'plan': plan, 'model_id': args.model_id, 'region': args.region,
              'inference_enabled': args.run_bedrock, 'rubric_sha256': digest(rubric), 'code_hashes': code,
              'basic_prompt_sha256': digest(BasicBedrockPlanner.system_prompt),
              'constrained_prompt_sha256': digest(BedrockPlanner.system_prompt)}
    if args.run_bedrock:
        if not args.allow_model_data or not args.model_id:
            raise ValueError('Actual inference requires model ID and explicit data opt-in')
        import boto3
        from botocore.config import Config
        client = boto3.Session(profile_name=args.profile).client('bedrock-runtime', region_name=args.region,
                    config=Config(connect_timeout=5, read_timeout=20, retries={'total_max_attempts': 1}))
        result = execute_plan(suite, args.out, config,
                    lambda arm: (BasicBedrockPlanner if arm == 'basic' else BedrockPlanner)(client, args.model_id, True))
    else:
        output = Path(args.out)
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        result = {'plan': plan, 'model_calls': 0, 'model_evaluation': 'not_run',
                  'rules_baselines': {identity: rules_baselines(packet) for identity, packet, _ in packets[:args.limit]},
                  'note': 'Synthetic development cases only; no model quality or live AWS results.'}
        write_private(output / 'preflight.json', json.dumps(result, indent=2) + '\n')
    print(json.dumps({'planned_runs': len(plan['jobs']), 'max_model_calls': plan['max_model_calls'],
                      'inference_enabled': args.run_bedrock, 'completed_runs': result.get('completed_runs', 0),
                      'out': args.out}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
