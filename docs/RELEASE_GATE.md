# Public alpha release gate (v0.1.0-alpha)

**Status: PUBLIC ALPHA RELEASED.** Offline engineering and publication-safety gates were exercised before publication. Live AWS and Bedrock validation remain uncompleted and must stay labeled unvalidated.

## Product scope

The first alpha is a local CLI for bounded, evidence-first investigation of explicitly configured AWS application resources. It can analyze offline synthetic bundles and optionally collect AWS evidence with an existing authorized profile. Bedrock investigation is experimental and opt-in. It never auto-remediates. Datadog, automatic alert triggers, complete network path analysis, and effective IAM authorization analysis are not included.

## Alpha publication record

- [x] GitHub Actions regression, sandbox offline evaluation, infrastructure lint and distribution build passed on the evaluated release candidate across Python 3.11, 3.12, and 3.13.
- [x] Confirmed both repository workflows executed successfully on the release-evaluation candidate.
- [x] Reviewed repository source and reachable history for common provider secrets, private-key material, personal identifiers, real telemetry, and suspicious credential-like content. Only synthetic fixtures were found.
- [x] Apache License 2.0 selected by the owner and added to the repository/package metadata.
- [x] Built distribution validated; wheel installed in an isolated environment and CLI smoke test passed. Offline unit/evaluation suites passed.
- [ ] For a later validated beta: complete the five controlled AWS scenarios, preserve outcomes and ground truth separately, verify safe cleanup. See docs/LIVE_VALIDATION_GATE.md. This is not an alpha blocker if live functionality is explicitly unvalidated.
- [ ] For a later validated beta: complete a paid Bedrock smoke test with explicit authorization, inspect outputs and cost. Until then label Bedrock unvalidated and exclude it from claims of proven functionality.
- [ ] Manually review incident explanations for unsupported causal claims, missing evidence, and inappropriate remediation suggestions.
- [ ] Confirm no deployment, model inference, or account permission changes happen during installation or offline use.
- [x] Docs describe IAM requirements, telemetry sensitivity, possible charges, alpha limitations, and non-production status.
- [x] Repository was deliberately made public after the publication-safety review.

## Historical alpha release evidence record

Record: tested commit SHA, workflow run links and conclusions, Python versions, package hashes, AWS scenario results, evaluator and review date, observed model usage/cost (if tested), known issues, and cleanup confirmation.

## Non-goals

Do not require Datadog, automatic remediation, multi-account orchestration, or complete VPN diagnosis for this first alpha. Do not claim production readiness, measured model accuracy, or research novelty from synthetic preflight alone.

## Go/no-go

Future releases remain **NO-GO** if CI fails, a secret or private telemetry is exposed, a scope escape or mutation is found, or claims exceed the evaluation. The current alpha must not claim tested live functionality. The active v0.2.0 gate is defined in [V0.2_RELEASE_CRITERIA.md](V0.2_RELEASE_CRITERIA.md).
