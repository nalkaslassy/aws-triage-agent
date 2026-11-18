# v0.1.0-alpha — public alpha notes

**Release state:** repository is public as an experimental alpha. Offline engineering and publication-safety checks passed; no live AWS or Bedrock validation is claimed.

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

## Alpha release verification

- [x] Apache-2.0 license file and package metadata added.
- [x] Alpha warning and limitations added to README.
- [x] Multi-version CI and wheel smoke-test workflows committed.
- [x] Release-candidate CI passed on Python 3.11, 3.12, and 3.13, including offline evaluation, infrastructure lint, build, and isolated wheel smoke test.
- [x] Clean wheel installation and offline evaluation results verified in GitHub-hosted runners.
- [x] Repository source and reachable history were inspected for common secrets, private-key material, personal identifiers, real telemetry, and suspicious credential-like content; only synthetic fixtures were found.
- [x] Owner approved preparation for public v0.1.0-alpha release.
- [x] GitHub repository visibility changed deliberately by owner.
- [ ] Confirm the `v0.1.0-alpha` Git tag/GitHub prerelease state in GitHub if a formal release artifact is desired; repository publication itself is complete.

## Security and reporting

See [SECURITY.md](SECURITY.md) for access limits, data handling, and how to report suspected security issues. Never commit credentials or real incident evidence.

## Release policy

Do not label this as production-ready, claim AWS/Bedrock validation, or publish a model-accuracy percentage from synthetic preflight. Live evaluation is the active v0.2.0 milestone. See [LIVE_VALIDATION_GATE.md](LIVE_VALIDATION_GATE.md) and [V0.2_RELEASE_CRITERIA.md](V0.2_RELEASE_CRITERIA.md).
