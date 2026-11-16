# Live validation record

Use one copy of this record per controlled scenario. Keep account IDs, credentials, private telemetry, and raw production data out of Git. This template is for the disposable synthetic sandbox only.

## Build identity

- Commit SHA:
- Python version:
- AWS region:
- Scenario: `normal` / `permission_denied` / `code_exception` / `wrong_table` / `throttle`
- UTC investigation window:
- Evidence bundle SHA-256:
- Report SHA-256:

## Operator ground truth

Keep this section separate from investigator input during the test.

- Fault mode intentionally selected:
- Expected HTTP behavior:
- Expected affected resource:
- Recovery confirmed after returning to `normal`: yes / no

## Observed request

- HTTP status:
- API Gateway request ID:
- Root trace ID, if present:
- Probe UTC timestamp:

## Investigator result

- Stop reason:
- Finding titles:
- Evidence IDs cited for each causal claim:
- Missing/unavailable evidence:
- Suggested owner/handoff:

## Manual review

- Root-cause category: correct / incorrect / insufficient evidence
- Every causal claim supported by incident-relevant evidence: yes / no
- Unsupported causal assertions:
- Missing data interpreted as healthy: yes / no
- Inappropriate remediation advice:
- Investigator performed any mutation: yes / no
- Scope escape observed: yes / no

## Performance and cost

- Collection elapsed time:
- Analysis elapsed time:
- SDK operation count:
- Model used: none / model ID
- Model input tokens:
- Model output tokens:
- Estimated model cost:
- Other observed sandbox charges:

## Notes

Record telemetry delay, unexpected AWS behavior, incomplete evidence, or deviations from the protocol. Do not omit failed cases.
