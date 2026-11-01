# Recorded model evaluation

Five curated synthetic cases cover a denied dependency request, unavailable permission evidence, a historical denial with current allow, informational noise, and a connectivity report with no observed request failure. They are a small development suite, not a representative incident benchmark.

`inputs/` contains only scoped manifests, incident evidence, symptoms, and recorded follow-up observations. `rubric.json` contains expected categories and contract requirements. The runner keeps the rubric, case identifiers, and scripted decisions out of model context. Input hashes make runs comparable. These fixtures contain no customer telemetry.

## Preflight (no inference)

```bash
PYTHONPATH=src python sandbox/evaluate_model.py --out reports/model-preflight.json
```

This validates all five packets and writes hashes. It makes zero model/AWS calls, needs no SDK, and produces no quality score. The checked-in `preflight.json` records this outcome. CI runs preflight only.

## Explicit paid model run

After selecting a compatible Bedrock model and existing authorized profile:

```bash
PYTHONPATH=src python sandbox/evaluate_model.py \
  --run-bedrock --allow-model-data --model-id YOUR_COMPATIBLE_MODEL_ID \
  --profile your-profile --region us-east-1 --limit 1 --repeat 1 \
  --out reports/model-eval.json
```

This sends curated synthetic observations to the selected model and incurs inference charges. Follow-ups use recorded observations; it does not diagnose a live AWS application. Output is owner-private and refuses overwrite. Defaults allow one case/run with at most six planning calls; maximum settings allow five cases repeated three times, at most 90 planning calls. These bounds are not a dollar cap.

Each run records initial deterministic findings, adaptive result, input hash, tool/check attempts, elapsed time, and returned token usage. Rubric checks cover completion, permitted candidate categories or abstention, required checks, and counterevidence where applicable. Review claims, citations, competing explanations, and useful next steps manually. A rubric pass does not establish causality or general accuracy. Actual model quality and live AWS behavior have not been measured.
