# Public beta release gate (v0.1.0-beta)

**Status: BLOCKED.** This is a checklist, not a claim that testing or publication has occurred.

## Product scope

The first beta is a local CLI for bounded, evidence-first investigation of explicitly configured AWS application resources. It can analyze offline synthetic bundles and optionally collect AWS evidence with an existing authorized profile. Bedrock investigation is experimental and opt-in. It never auto-remediates. Datadog, automatic alert triggers, complete network path analysis, and effective IAM authorization analysis are not included.

## Must pass before making repository public

- [ ] GitHub Actions regression, sandbox offline evaluation, infrastructure lint and distribution build all pass on the intended release commit.
- [ ] Confirm the newly added CI workflow actually executes in the private repository. A committed workflow alone is not a green build.
- [ ] Review the full source, git history, examples, and generated assets for secrets, personal data, customer telemetry, and unsafe instructions. Remove any exposures and rotate credentials if necessary.
- [ ] Choose and add an explicit open-source license with the owner's approval; currently none is selected.
- [ ] Validate installation from a built distribution in a clean environment and run the documented offline examples.
- [ ] Complete the five controlled AWS scenarios, preserve outcomes and ground truth separately, verify safe cleanup. See docs/LIVE_VALIDATION_GATE.md.
- [ ] Complete a paid Bedrock smoke test with explicit authorization, inspect outputs and cost. If not completed, label Bedrock unvalidated and exclude it from claims of proven functionality.
- [ ] Manually review incident explanations for unsupported causal claims, missing evidence, and inappropriate remediation suggestions.
- [ ] Confirm no deployment, model inference, or account permission changes happen during installation or offline use.
- [ ] Ensure docs describe required IAM access, telemetry sensitivity, charges, limitations, and the non-production nature of the beta.
- [ ] Create a version tag and GitHub prerelease only after the above review.

## Beta release evidence record

Record: tested commit SHA, workflow run links and conclusions, Python versions, package hashes, AWS scenario results, evaluator and review date, observed model usage/cost (if tested), known issues, and cleanup confirmation.

## Non-goals

Do not require Datadog, automatic remediation, multi-account orchestration, or complete VPN diagnosis for this first beta. Do not claim production readiness, measured model accuracy, or research novelty from synthetic preflight alone.

## Go/no-go

**NO-GO** if CI fails, a secret or private telemetry is exposed, a scope escape or mutation is found, live scenario evidence is missing for advertised live functionality, or claims exceed the evaluation. A limited offline-only preview can be considered separately if accurately labeled and approved.
