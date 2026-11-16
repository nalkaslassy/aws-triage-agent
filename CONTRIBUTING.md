# Contributing

Thanks for helping improve AWS Triage Agent.

This project is an experimental alpha focused on bounded, evidence-first AWS incident investigation. Contributions should preserve three principles:

1. **Evidence before conclusions.** Missing data is unknown, not healthy. Findings must distinguish observations from hypotheses.
2. **Read-only investigation by default.** Do not add infrastructure mutation or automatic remediation to the investigator.
3. **Explicit scope and privacy.** Do not commit credentials, production telemetry, customer data, private incident evidence, or generated local reports.

## Development setup

Python 3.11+ is supported.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[aws]'
python -m unittest discover -s tests -v
python sandbox/local_evaluation.py
python sandbox/evaluate_agent.py
python sandbox/run_pilot.py --limit 12 --repeat 3 --out reports/pilot-preflight
```

Before submitting infrastructure changes:

```bash
python -m pip install 'cfn-lint>=1,<2'
cfn-lint sandbox/template.yaml
```

## Pull requests

Keep changes focused. Add or update tests for behavior changes. Do not weaken validation, resource scope, evidence citation requirements, model-data opt-in, or the no-auto-remediation boundary without a clearly documented security rationale.

A pull request should explain:
- the problem being solved;
- why the change is in scope;
- tests or evaluation performed;
- new AWS permissions, model data, network access, costs, or side effects, if any;
- documentation changes needed.

## Security-sensitive changes

Changes involving credentials, IAM, model tool use, HTTP requests, generated files, parsing untrusted telemetry, or cloud resource scope should include negative tests. Prefer fail-closed behavior.

Do not open a public issue containing a vulnerability, credential, production telemetry, or customer data. See [SECURITY.md](SECURITY.md).

## Live AWS validation

Do not claim live AWS correctness from mocked or synthetic tests. Follow [docs/LIVE_VALIDATION_GATE.md](docs/LIVE_VALIDATION_GATE.md) for controlled sandbox validation.

## License

By contributing, you agree that your contribution is licensed under the repository's Apache License 2.0.
