"""Export arm-blinded review packets, a blank scoring sheet, and a separate key."""
import argparse
import csv
import io
import json
import random
from pathlib import Path

from aws_triage.cli import write_private
from aws_triage.pilot import digest


def export_review(run_directory, out_directory):
    root, output = Path(run_directory), Path(out_directory)
    config = json.loads((root / 'config.json').read_text())
    rows = []
    for identity, iteration, arm in config['plan']['jobs']:
        path = root / f'{identity}-{iteration}-{arm}.json'
        if path.exists():
            row = json.loads(path.read_text())
            if row['config_sha256'] != digest(config):
                raise ValueError('Result/config mismatch')
            rows.append(row)
    if not rows:
        raise ValueError('No model runs to review')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    random.Random(config['plan']['seed'] + 1).shuffle(rows)
    key, packets = {}, []
    sheet = io.StringIO()
    columns = ['review_id', 'reviewer', 'accepted_supported', 'accepted_unsupported', 'missed_useful_categories',
               'raw_unsupported', 'appropriate_uncertainty', 'useful_next_step', 'exact_cause_overclaim', 'notes']
    writer = csv.DictWriter(sheet, fieldnames=columns); writer.writeheader()
    for n, row in enumerate(rows, 1):
        identity = f'review{n:03}'
        key[identity] = {'case': row['case'], 'repeat': row['repeat'], 'arm': row['arm']}
        result = row['result']
        packets.append({'review_id': identity, 'incident': result['incident'], 'evidence_bundle': result['evidence_bundle'],
                        'accepted_assessment': result['assessment'], 'raw_proposals': result['raw_proposals'], 'proposal_contexts': result['proposal_contexts'],
                        'completed': result['stop_reason'] == 'finished'})
        writer.writerow({'review_id': identity})
    write_private(output / 'packets.json', json.dumps(packets, indent=2) + '\n')
    write_private(output / 'scoring.csv', sheet.getvalue())
    write_private(output / 'PRIVATE-key.json', json.dumps(key, indent=2) + '\n')
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(f'Exported {export_review(args.runs, args.out)} review packets; keep PRIVATE-key.json from the reviewer.')


if __name__ == '__main__':
    main()
