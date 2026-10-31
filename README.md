# AWS Triage Agent

Evidence-based incident triage for AWS applications, permissions, VPN, and network connectivity.

The intended workflow is monitoring alert → scoped evidence collection → investigation → findings and next steps for the responder. Customer reports can provide additional symptoms. A successful investigation can also be an explicit handoff explaining what was checked, what remains unknown, and which team should check it next.

## Current milestone: runnable investigation foundation

This is an early prototype, not a production incident response system or a completed autonomous AI agent. The first milestone implements deterministic first-pass triage so evidence handling can be tested before adding a model.

Implemented:

- Offline evidence-bundle analysis with Markdown or JSON reports.
- Findings that reference evidence IDs and distinguish observed failures from hypotheses.
- Suggested verification steps, responsible teams, and explicit visibility gaps.
- Optional AWS collection of Lambda metrics, bounded log samples, explicitly named security group configuration, and Client VPN route/authorization/session snapshots.
- Current Lambda table configuration and concurrency snapshots, with checks for intended-target mismatch and concurrency disabled at zero.
- REST API request/error counts, weighted mean latency, and an adjacent equal-length baseline.
- Evidence-linked reports with resource names, collection times, sampled identifiers, and AWS console pointers.
- Strict numeric/type checks, partial-evidence retention, and failure-context log classification.
- Limited correlation between a failed table request and the matching function's current table mismatch.
- A [disposable Orders API sandbox](sandbox/README.md) with infrastructure as code, five local scenarios, and an operator-only signed request helper.
- Account verification, explicit region/resource scope, limited collection windows and API calls.
- No infrastructure changes by the investigator, shell execution, Secrets Manager/SSM secret reads, or model data transmission. The separate sandbox probe can write one synthetic order when explicitly run by an operator.

Not implemented yet: Datadog ingestion, automatic alert triggers, traces, IAM policy evaluation, change correlation, DNS/client diagnostics, active connectivity testing, network path evaluation, ranked competing hypotheses, and model-driven follow-up checks. Collected security group and VPN configuration is retained as evidence, but this milestone does not automatically evaluate the complete network path or users' effective VPN authorization. Each is tracked in [the roadmap](docs/ROADMAP.md).

## Run the demo

Python 3.11+ is required. The offline core has no third-party runtime dependencies.

```bash
PYTHONPATH=src python -m aws_triage.cli analyze examples/permission_failure.json
PYTHONPATH=src python -m aws_triage.cli analyze examples/network_unknown.json --format json
PYTHONPATH=src python -m aws_triage.cli analyze examples/api_http_failure.json
PYTHONPATH=src python -m unittest discover -s tests -v
```

All example bundles contain synthetic data. They do not represent customer incidents or validated diagnoses.

The [API failure report example](examples/api_failure_report.md) shows API errors despite zero Lambda execution errors. Findings link to an evidence index. Live collector reports include console pointers that open the relevant AWS service, not an immutable event permalink.

To install the command locally:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
aws-triage analyze examples/permission_failure.json
```

## Optional AWS collection

Use a sandbox account for initial validation. No AWS resources have been deployed as part of creating this repository, and live AWS collection has not been verified against an account yet.

```bash
python -m pip install -e '.[aws]'
cp examples/application.json application.local.json
# Edit account_id, region, and resource names to match an authorized application.
aws-triage collect --manifest application.local.json --profile your-existing-profile \
  --start 2026-10-30T12:00:00Z --end 2026-10-30T12:15:00Z \
  --out evidence/incident.json
aws-triage analyze evidence/incident.json --out reports/incident.md
```

Supply your actual incident window (at most one hour). Output files are created with owner-only permissions and refuse overwrite. Telemetry files can still contain sensitive resource identifiers and network configuration; keep them out of Git. Do not put credentials in manifests or source code.

The collector uses existing boto3 credentials and checks the account before reading telemetry. It does not create roles, grant access, run probes, query arbitrary resources, or deploy anything. A manifest is a collection boundary, not an IAM security boundary; enforce the permitted resources and actions using your role policy. See [security and access](docs/SECURITY.md).

Raw log messages are processed locally, then discarded. A bounded error-keyword query selects candidates; structured failure events and supported error-level context determine which signals become hypotheses. Informational and bare keyword mentions are excluded. Some formats and failures logged at other levels can be missed. No raw messages are sent to an LLM.

For REST API collection, add `rest_apis` entries with `api_id`, `api_name`, and `stage` (maximum two). API windows require minute-aligned UTC boundaries and include a preceding equal-length baseline. Queries use `ApiName`/`Stage` dimensions; ensure API names are unique in the account/region. Missing datapoints remain unknown. See [investigation behavior](docs/INVESTIGATION.md) for calculations and limits.

## Investigation principles

1. Error counts identify symptoms; logs, traces, configuration, and changes help explain causes.
2. Missing data is unknown, not healthy or zero.
3. Requests blocked before reaching an application may produce no application error.
4. VPN session establishment does not prove application reachability.
5. A timeout does not establish a VPN problem. A flow-log rejection does not alone identify the blocking rule.
6. A report should document evidence, uncertainty, suggested checks, and a useful owner handoff.
7. Recommendations require engineer review; automated remediation is outside the initial scope.

AWS already offers incident investigation through DevOps Agent and CloudWatch investigations. This project's intended value is a focused, inspectable workflow with explicit coverage limits and repeatable evaluation. Novelty or superiority is not claimed.

## Project layout

- `src/aws_triage/`: evidence contracts, AWS collector, triage logic, report renderer, CLI.
- `examples/`: synthetic incident bundles and a collection manifest.
- `tests/`: offline behavioral and collection-boundary tests.
- `docs/`: architecture, access model, evaluation, and milestones.

No open-source license has been selected yet. Keep the repository private while the prototype is being developed.

## Next step: live sandbox validation

The sandbox deployment code and local scenario checks are available. No AWS resources have been deployed and live diagnosis remains unverified. Start with [the sandbox guide](sandbox/README.md): validate/build the template, review the deployment in your sandbox account, send a normal request, and collect its evidence before injecting a fault.
