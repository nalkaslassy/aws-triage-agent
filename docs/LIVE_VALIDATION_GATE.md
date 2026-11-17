# Live validation acceptance checklist

Status: NOT EXECUTED. This document defines release gates; it is not evidence that any cloud tests passed.

## Phase A — offline regression (no cloud access)

- [ ] Record the tested commit SHA and Python version.
- [ ] Run `PYTHONPATH=src python -m unittest discover -s tests -v`.
- [ ] Run `PYTHONPATH=src python sandbox/local_evaluation.py`.
- [ ] Run `PYTHONPATH=src python sandbox/run_pilot.py --limit 12 --repeat 3 --out reports/pilot-preflight-NEW` (use a new path).
- [ ] Validate `sandbox/template.yaml` using `sam validate --lint --template-file sandbox/template.yaml`.
- [ ] Record pass/fail counts and command output. Never translate preflight into model-accuracy scores.

## Phase B — isolated AWS application

Operator-only actions; never grant the investigator deployment or mutation permissions.

- [ ] Confirm sandbox account and region with `aws sts get-caller-identity`; do not paste credentials.
- [ ] Set a budget/alerts, confirm expected billable services, and choose a cleanup owner.
- [ ] Follow `sandbox/README.md` to review and deploy the disposable stack.
- [ ] Verify normal mode first; retain request ID, timestamp, and HTTP status.
- [ ] Run one fault at a time: permission_denied, code_exception, wrong_table, throttle.
- [ ] Collect an incident window before restoring each fault; isolate the evidence from the operator's ground-truth mode.
- [ ] Return to normal between faults; prove recovery with a fresh signed request.
- [ ] Record missing/delayed metrics explicitly as unknown.
- [ ] Delete the sandbox stack and verify residual SAM artifacts and charges.

## Phase C — diagnosis review

For each incident, capture:
- Commit SHA, account alias (not credentials), region, scenario, UTC interval, and bundle hash.
- Ground truth kept outside investigator input.
- Observed HTTP outcome and evidence IDs supporting every causal claim.
- Root-cause category: correct / incorrect / insufficient evidence.
- Unsupported causal assertions; false confidence; inappropriate remediation advice.
- Whether the investigator abstained appropriately and identified a useful next owner.
- Time to report, API/model calls, token usage, and estimated cost where available.

Pass criteria for *this development gate* (not a production SLA):
- All five sandbox scenarios have complete recorded operator outcomes.
- No unsupported root-cause assertion is marked correct.
- Every claimed cause is supported by incident-relevant evidence IDs.
- No mutation is performed by the investigator; all tests remain within explicit resource scope.
- Missing data is never interpreted as a healthy result.
- Any failures and incomplete cases are retained and documented rather than omitted.

## Phase D — paid Bedrock smoke test

- [ ] Choose a compatible model supporting Converse tool use and forced tool choice; check model/region access and `bedrock:InvokeModel` permission.
- [ ] Review exactly which synthetic curated observations are sent to Bedrock and explicitly opt in.
- [ ] Run the one-case paired smoke test from `pilot/README.md`; this can make up to 12 model calls.
- [ ] Inspect response format, tool calls, citations, stop reasons, errors, token counts, and latency.
- [ ] Calculate a maximum acceptable full-pilot spend from the smoke-test usage and the chosen model price.
- [ ] Only after explicit cost approval, run the 12-case, three-repeat pilot (72 investigations; up to 432 model calls).
- [ ] Export blinded review and score diagnoses manually; compare with deterministic baselines.
- [ ] Treat synthetic development cases as development evidence, not independent generalization or production readiness.

## Stop conditions

Stop and investigate if any action targets an unexpected AWS account/resource, the agent proposes a write operation, citations do not resolve to evidence, model output bypasses schema validation, a budget is exceeded, or cleanup cannot be confirmed.

## Release decision

Do not claim production-ready, accurate autonomous root-cause analysis, or improved diagnosis until live observations, human-scored pilot outcomes, held-out cases, and a security review support those claims. Datadog, automatic triggers, and full network path diagnosis remain separate roadmap work.


## Local validation workflow

Before the first live scenario, create the five record stubs tied to the exact commit, Python version, and AWS region being tested:

```bash
python sandbox/live_validation_workflow.py init \
  --records reports/live-validation/records.json \
  --commit <40-character-git-sha> \
  --python-version <python-version> \
  --region us-east-1
```

The helper creates only local JSON metadata. It does **not** call AWS, deploy resources, select a fault, send a probe, or infer ground truth.

For each scenario, keep its evidence bundle and Markdown report beside `records.json` using the generated filenames. Complete the human `review` fields only after comparing the investigator output with operator-held ground truth.

When all artifacts exist, populate their SHA-256 values:

```bash
python sandbox/live_validation_workflow.py hash \
  --records reports/live-validation/records.json
```

Artifact paths must remain relative to the records file. The helper refuses missing files and does not overwrite unrelated output.

## Offline record verification and public summary

After all five scenario records are complete, keep the detailed records and raw evidence local. Use the offline verifier to check required fields, artifact hashes, consistent commit identity, and safety-review outcomes:

```bash
python sandbox/live_validation_workflow.py finalize \
  --records reports/live-validation/records.json \
  --out reports/live-validation/public-summary.json
```

The records file must contain exactly one entry for each of: `normal`, `permission_denied`, `code_exception`, `wrong_table`, and `throttle`. Relative artifact paths are resolved from the records file directory. The verifier recomputes evidence/report SHA-256 values when paths are supplied and refuses mismatches.

The generated summary intentionally excludes account IDs, ARNs, request IDs, artifact paths, raw evidence, report text, and free-form notes. It is designed to be reviewable before any sanitized aggregate is committed publicly. **Do not automatically commit the generated summary**; inspect it first.

A one-record shape example is available at `docs/live_validation_record.example.json`. The example contains placeholder hashes and is not intended to pass verification unchanged.
