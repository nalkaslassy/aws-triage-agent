# v0.1.0-alpha — release candidate notes

**Release state:** prepared, not published. No live AWS or Bedrock validation is claimed.

## What this alpha provides

- Offline evidence bundle analysis and evidence-linked Markdown/JSON investigation reports.
- Deterministic triage for selected Lambda, REST API, authorization, and network configuration observations.
- Optional, scoped read-only AWS collector with bounded requests, incident windows, and explicit account checks.
- Experimental bounded adaptive investigation with optional Bedrock Converse model use, requiring explicit opt-in.
- Synthetic replay cases, model-evaluation pilot framework, and disposable AWS sandbox definitions.

## Known limitations

- Live AWS scenario validation and actual Bedrock inference have **not** been completed.
- No measured real-world diagnostic accuracy, performance, or production reliability.
- No Datadog integration, automated alert ingestion, automatic remediation, or complete VPN/network path analysis.
- IAM simulation is not complete effective-authorization proof; current resource configuration is not historical incident-time state.
- SDK collection can expose sensitive configuration in memory; generated evidence contains identifiers. Review before sharing.
- Sandbox probe is separate from the read-only investigator and can write a **synthetic** order when explicitly invoked.
- AI findings are hypotheses requiring human verification. Do not rely on this tool as the sole basis for incident response.

## Installation and offline smoke test

Python 3.11 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
aws-triage analyze examples/permission_failure.json
python -m unittest discover -s tests -v
```

Optional AWS dependencies: `python -m pip install -e '.[aws]'`. The offline example requires no AWS account or model inference. Windows PowerShell activation: `.venv\Scripts\Activate.ps1`.

## Release candidate verification

- [x] Apache-2.0 license file and package metadata added.
- [x] Alpha warning and limitations added to README.
- [x] Multi-version CI and wheel smoke-test workflows committed.
- [ ] CI workflow green on release commit.
- [ ] Clean installation and offline evaluation results independently verified.
- [ ] Full repository and **git history** inspected for secrets, customer telemetry, private links, and copyrighted material not cleared for redistribution.
- [ ] Release commit reviewed and approved by owner.
- [ ] GitHub repository visibility changed deliberately by owner, if desired.
- [ ] `v0.1.0-alpha` Git tag and GitHub prerelease created, after blockers clear.

## Security and reporting

See [SECURITY.md](SECURITY.md) for access limits, data handling, and how to report suspected security issues. Never commit credentials or real incident evidence.

## Release policy

Do not label this as production-ready, claim AWS/Bedrock validation, or publish a model-accuracy percentage from synthetic preflight. Defer the live evaluation to a subsequent milestone.
