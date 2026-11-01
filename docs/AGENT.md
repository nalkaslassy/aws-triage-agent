# Bounded investigation loop

The runtime supports scoped follow-up investigation with an opt-in Bedrock Converse adapter. Local replay and real SDK request/response models have been tested using stubbed responses. Live Bedrock inference and AWS diagnosis quality have not been evaluated.

## Local demonstration

```bash
PYTHONPATH=src python -m aws_triage.cli agent replay examples/agent/permission_denied.json \
  --format markdown --out reports/permission-replay.md
PYTHONPATH=src python sandbox/evaluate_agent.py
```

Replay makes no model or AWS calls. Its explicit scripted decisions exercise the same validation/runtime used by the live adapter. See [the example report](../examples/agent/permission_report.md) and [contract results](../sandbox/agent-contract-results.json). Expected outcomes remain outside investigator input. Passing these cases is not evidence of model diagnosis quality.

## Live use after sandbox deployment

Deploy and validate the [Orders sandbox](../sandbox/README.md), then collect an actual evidence bundle. Use an existing read profile authorized for the configured resources. The runtime creates no permissions or infrastructure.

The example below uses the default sandbox stack's function name. Choose an available Bedrock model that supports Converse tools and forced tool choice; this project hardcodes no model ID.

```bash
aws-triage agent run evidence/incident.json --manifest application.local.json \
  --function triage-sandbox-orders-orders \
  --symptom 'Order creation fails during the incident window' \
  --profile your-read-profile --model-id YOUR_COMPATIBLE_MODEL_ID \
  --allow-model-data --max-steps 6 --seconds 60 \
  --out reports/adaptive-investigation.json
```

Use `--format markdown` for a readable report. Output files have owner-only permissions and refuse overwrite. Optional `--model-region` selects the Bedrock client region; otherwise it uses the manifest region. Inference profiles can route according to AWS's profile configuration.

`--allow-model-data` permits sending curated operational data to the selected model. The projection includes the symptom, scoped resource identifiers, selected metrics/configuration, sampled log identifiers/targets, simulation results, and change-event metadata. It excludes arbitrary raw log messages, full Lambda environments, policy documents, usernames/access keys, and CloudTrail request bodies. Review the source bundle and these allowed fields before opting in. Unknown fields in imported data can remain in the private local `evidence_bundle` output; they are not automatically sent to the model.

Inference incurs the chosen model's charges. The runtime limits turns and context size, not dollar spending. Use synthetic sandbox data for initial inference tests.

## Named checks

The operator selects one function from the manifest. Initial evidence is restricted to that function, its configured log group, and configured API stages. Every model proposal is validated by application code, independently of the model's tool schema.

| Check | Implementation | Limit |
| --- | --- | --- |
| `logs` | Bounded filtered Lambda log collection | Selected formats/samples can miss failures |
| `configuration` | Current Lambda configuration and reserved concurrency | Current state is not incident-time state |
| `permissions` | Bind the current execution role and manifest table, then simulate `dynamodb:PutItem` | Skip mismatching targets or unbound/cross-account roles; not full live authorization evaluation |
| `changes` | One ResourceName-filtered CloudTrail page from 30 minutes before incident start through incident end | Regional function metadata, not complete deployment/IAM history |

The model cannot choose arbitrary AWS operations, roles, target ARNs, commands, URLs, or remediation text. Finish proposals use enumerated candidate categories, supporting/counterevidence IDs, and approved next-step keys. User-facing candidate explanations and suggested actions use application templates rather than free-form model prose.

Simulation records the role/action/target, decision, and missing context keys. A function's current execution role does not establish the principal used by a particular dependency request. Simulated allow does not disprove a recorded AccessDenied. Resource/endpoint policies, session context, role chaining, and historical state may differ. These are candidate explanations requiring engineer review; no fix is executed.

CloudTrail retains event ID/name/source/time for non-read events only. Full event bodies, access keys, usernames, and request parameters are discarded. No returned changes does not establish no deployment or IAM change. The lookup is one page of ten events; continuation is partial.

## Budgets and validation

- Six steps by default; configurable from one to ten, including the final decision. Each named check normally executes once. A check with explicit recognized transient read errors can execute one additional time within the same step/time/SDK budgets. Access denials, scope failures, unknown errors, and deadline failures do not qualify. Other repeat proposals use cached evidence.
- Context is capped at 24,000 serialized characters per model turn; output at 1,024 tokens. Returned token usage is recorded without inferring monetary cost.
- Default cooperative deadline: sixty seconds, configurable from one to 120. Checks occur before/after planning and before AWS calls. In-flight calls can finish after the deadline: SDK reads use ten-second read timeouts; inference uses twenty seconds and one attempt.
- The collector retains its 75-operation budget and bounded retries. Authenticated account identity is verified before application reads. The model has no direct SDK access.
- Final references must exist in scoped, available evidence. Supporting and contradicting IDs must not overlap. Each candidate needs a qualifying observation category.
- Log candidates require a matching sampled event inside the incident window. A nearby change alone cannot support an authorization candidate. Authorization candidates require an in-window failed request with a request ID, PutItem operation, and table target. Every cited simulation must match that request action and target. A simulation alone is a configuration observation, even when it denies access without missing context.
- Category/reference validation does not establish semantic causality. Counterevidence selection and ranking still need evaluation. There are no calibrated confidence scores or confirmed root-cause claims.
- Invalid decisions, unavailable planning, deadlines, or exhausted budgets stop the adaptive assessment while preserving deterministic findings and useful handoffs. Partial reads survive.

The journal distinguishes successful, partial, unavailable, no-evidence, and cached outcomes. It records attempts, retry eligibility, evidence IDs, and safe rejection/error codes. A completed call does not imply successful collection. Earlier evidence is preserved across retries. It excludes raw provider errors and model private reasoning.

## Existing-profile permissions

| Permission | Purpose |
| --- | --- |
| `iam:SimulatePrincipalPolicy` | The bound current execution role; scope the grant to approved role ARNs |
| `cloudtrail:LookupEvents` | Regional change lookup; this API generally needs account/region-level access |
| `bedrock:InvokeModel` | The chosen compatible model/profile and AWS-required associated resources |

Existing Lambda, metrics, and log permissions are also needed. No grants are configured by this code. Simulation can disclose role-permission information; CloudTrail responses can contain sensitive bodies before local filtering.

## Evaluation still needed

Run the real selected model and deterministic baseline against the same recorded incidents. Keep expected diagnoses outside model input. Measure useful additional findings, unsupported categories, missing-evidence handoffs, citation/counterevidence quality, tool calls, elapsed time, and input/output tokens. The checked-in results compare initial rules with scripted follow-ups only and explicitly leave model-vs-rules quality unmeasured.

Then exercise the live sandbox faults and verify actual principal/action/resource, responses, telemetry delay, and collection coverage. Broader network diagnosis, Datadog alert ingestion, resource-policy inspection, and full deployment-history correlation remain pending.

References: [Bedrock tool calling](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-client-side.html), [IAM simulation](https://docs.aws.amazon.com/IAM/latest/APIReference/API_SimulatePrincipalPolicy.html), [CloudTrail lookup](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_LookupEvents.html).

## Incident handoff and evaluation inputs

JSON and Markdown reports include a focused incident summary: leading candidate, exact request/action/target when available, latest incomplete checks, and a suggested owner verification. Request IDs group related samples; valid AWS root trace IDs are retained as identifiers. This does not retrieve X-Ray traces or prove a complete request path. Current-role simulation does not identify the actual historical caller.

The separate [model evaluation guide](../evaluation/README.md) describes five recorded synthetic input packets, private expected-answer rubrics, a no-inference preflight, and explicitly enabled paid Bedrock runs. No actual model quality results have been recorded.
