"""Write a factual checkpoint report; no diagnosis accuracy is inferred."""
import argparse
import json
from pathlib import Path

from aws_triage.cli import write_private
from aws_triage.pilot import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = summarize(args.runs)
    lines = ['# Recorded pilot execution report', '',
             f"Completed checkpoints: {result['completed_runs']} / {result['planned_runs']}", '',
             '| Arm | Runs | Contract passes | Rejected | Unfinished | Input tokens | Output tokens |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for arm, row in result['arms'].items():
        lines.append(f"| {arm} | {row['runs']} | {row['rubric_passes']} | {row['rejected']} | {row['unfinished']} | "
                     f"{row['tokens']['input_tokens']} | {row['tokens']['output_tokens']} |")
    lines += ['', 'Contract passes are not diagnosis accuracy. Human claim-level review and useful-finding assessment remain required.',
              'A partial run is not a complete paired comparison. Repeated runs are clustered within distinct cases.',
              'This report does not establish live AWS accuracy, model benefit, research novelty, or production readiness.', '',
              'Run export_pilot_review.py and apply pilot/REVIEW.md before making a continuation decision.', '']
    write_private(Path(args.out), '\n'.join(lines))
    print(f'Report written to {args.out}.')


if __name__ == '__main__':
    main()
