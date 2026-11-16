# Changelog

All notable public changes to AWS Triage Agent are documented here.

## [0.1.0-alpha] - 2026-11-16

Initial public alpha.

### Added

- Evidence-first offline AWS incident analysis with Markdown and JSON reports.
- Scoped AWS collection for selected Lambda, API Gateway, logs, security-group, and Client VPN evidence.
- Explicit evidence IDs, visibility gaps, ownership handoffs, and hypothesis/observation separation.
- Bounded adaptive investigation runtime with opt-in Bedrock Converse support.
- Read-only follow-up checks, decision validation, retry limits, and model-data opt-in.
- Synthetic replay/evaluation suites and a 12-case pilot preflight.
- Disposable Orders API sandbox with controlled normal, permission, code, configuration, and throttling scenarios.
- Multi-version CI for Python 3.11, 3.12, and 3.13.
- Distribution build, isolated wheel smoke test, CloudFormation lint, security policy, and Apache-2.0 license.

### Known limitations

- Live AWS diagnosis has not yet been validated against the disposable sandbox.
- Real Bedrock inference quality has not yet been measured.
- No production diagnostic accuracy or reliability claim is made.
- Datadog ingestion, automatic alerts, complete network-path diagnosis, and automatic remediation are not included.
