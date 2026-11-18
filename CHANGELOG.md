# Changelog

All notable public changes to AWS Triage Agent are documented here.

## Unreleased

### Added

- Hardened live-validation record workflow with schema validation, artifact hashing, path confinement, symlink rejection, and owner-only atomic writes.
- Sanitized aggregate JSON generation that retains valid negative outcomes instead of hiding failed cases.
- Human-readable sanitized Markdown validation report rendering.
- Explicit v0.2.0 release criteria for controlled live AWS sandbox validation.
- Contributor guidance, issue/PR templates, and public security reporting guidance.

### Changed

- README and roadmap now identify controlled live AWS sandbox validation as the active milestone.
- Public documentation distinguishes alpha publication evidence from the current v0.2 validation gate.

### Validation

- Full CI continues to pass across Python 3.11, 3.12, and 3.13, including AWS contract tests, infrastructure lint, package build/install checks, offline sandbox evaluation, agent evaluation, and pilot preflight.


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
