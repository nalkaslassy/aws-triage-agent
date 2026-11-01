# AWS triage pilot

Status: prepared and locally tested. No actual model inference or live AWS deployment has been run. All 12 input packets are synthetic development cases, including five reused from `evaluation/`. They are not independent held-out incidents. See [protocol](PROTOCOL.md), [review instructions](REVIEW.md), and [live validation](LIVE_VALIDATION.md).

The question is whether request-linked evidence requirements reduce unsupported diagnosis categories without discarding useful investigation. This pilot is a development decision, not a publication benchmark.

## What is ready

- Twelve packets and a separate expected-answer rubric.
- Initial-only rules and an all-recorded-observation rules coverage reference.
- Basic and constrained model arms using identical tool schemas, curated observations, six-turn/60-second budgets, context/output limits, caching, and retry logic in a common recorded-only runner.
- Raw proposals, accepted assessments, evidence, check outcomes, elapsed time, and reported token usage.
- Seeded mixed execution order, input/prompt/code/rubric hashes, checkpoints, and exact-configuration resume.
- An arm-blinded review export and blank CSV scoring sheet. Human scoring is not fabricated or replaced by category rubric checks.

The basic arm keeps scope, schema, reference availability, read-only tools, and budgets. It omits the extra request/action/target qualification and uses a simpler diagnosis prompt. It never disables production runtime validation. This is a joint prompt-and-validator comparison, not an isolated causal test of either component.

## 1. Local preflight: no credentials, no inference

From the repository root with Python 3.11+:

```bash
PYTHONPATH=src python -m unittest discover -s tests -q
PYTHONPATH=src python sandbox/run_pilot.py \
  --limit 12 --repeat 3 --out reports/pilot-preflight
```

Use a new output directory. Preflight validates packets, hashes them, creates the 72-job plan, and runs deterministic baselines. It makes zero model/AWS calls and produces no model-quality score. A small [checked-in status](preflight-status.json) records that distinction.

## 2. Small real-model smoke test (explicit paid inference)

Use an existing authorized AWS profile and a Bedrock model supporting Converse tools and forced tool choice. No credentials belong in source or chat. Install the existing AWS extra:

```bash
python -m pip install -e '.[aws]'
PYTHONPATH=src python sandbox/run_pilot.py \
  --run-bedrock --allow-model-data --model-id YOUR_COMPATIBLE_MODEL_ID \
  --profile your-profile --region us-east-1 \
  --limit 1 --repeat 1 --out reports/pilot-smoke
```

This runs both arms on one case: at most 12 model calls. Only synthetic curated observations are transmitted. Inspect outputs before expansion. A provider/response-format failure stops the batch, preserves the failed record, and does not automatically retry it on resume. Fix setup first; use a new directory for a deliberate retry and retain the earlier failure.

## 3. Full recorded development pilot

After the smoke test works:

```bash
PYTHONPATH=src python sandbox/run_pilot.py \
  --run-bedrock --allow-model-data --model-id YOUR_COMPATIBLE_MODEL_ID \
  --profile your-profile --region us-east-1 \
  --limit 12 --repeat 3 --out reports/pilot-model-run
```

This schedules 72 investigations, at most 432 model calls. It can take many minutes. There is no dollar cap: calculate a budget using the chosen model's rates and smoke-test token usage before proceeding. Do not interpret the earlier small smoke-test cost estimate as this full pilot's estimate. No AWS application resources are created by this runner; follow-ups always replay recorded evidence.

Re-run the exact command to resume completed checkpoints. Model ID, region, source code, rubric, seed, case count, repeats, and packet hashes must match. An interrupted in-flight call can still incur provider charges before a checkpoint is saved. A partial run must not be reported as a complete paired comparison.

## 4. Export and review

```bash
PYTHONPATH=src python sandbox/export_pilot_review.py \
  --runs reports/pilot-model-run --out reports/pilot-review
```

For a factual execution report (contract counts, failures, and tokens):

```bash
PYTHONPATH=src python sandbox/summarize_pilot.py \
  --runs reports/pilot-model-run --out reports/pilot-execution.md
```

Read [REVIEW.md](REVIEW.md) before scoring. Keep `PRIVATE-key.json` separate from the reviewer. The export hides arm/case names, not every possible behavioral clue. Use the expected-answer rubric only after reviewing evidence, and record disagreement. We can perform the review together, but an independent second reviewer is preferable before publication.

The console summary contains limited contract counts, not unsupported-claim accuracy. Actual inference, independent human scoring, related-work assessment, live collection validation, and held-out evaluation remain outstanding.
