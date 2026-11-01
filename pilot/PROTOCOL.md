# Development pilot protocol v0.1

Freeze the input, rubric, prompts, code hashes, model/version or inference profile, region, and run plan before collecting real-model results. Register any changes in a new run directory. Do not tune against an evaluation set and subsequently call it held out.

## Question and scope

Can evidence qualification and an uncertainty-oriented prompt reduce unsupported diagnosis categories while preserving useful incident investigation? Output consists of ranked categories, evidence references, and predefined next steps. The present interface does not test unrestricted narrative explanations, exact IAM policy identification, full network root causes, or responder time saved.

The treatment combines a stronger prompt and a runtime validator. Any observed difference is attributable to this package. Separate prompt-only and validator-only arms would be needed to distinguish their contributions. Production validation remains unchanged; the relaxed comparator exists only in a recorded-only research runner.

## Development cases

| Case | Observation or challenge | Permitted interpretation |
| --- | --- | --- |
| 01 | In-window denied PutItem plus current denial | Authorization candidate, actual historical principal still unverified |
| 02 | Failed request; simulator unavailable | Authorization symptom or useful uncertainty; disclose missing visibility |
| 03 | Historical request denial; current simulation allows | Current allow does not erase the failure; cite counterevidence |
| 04 | Informational noise | No supported failure category |
| 05 | Connectivity report and current denied policy, no failed request | Simulation alone cannot explain the reported outage |
| 06 | Configured table differs from intended table | Configuration candidate; compare target and intended state |
| 07 | Incident-time application exception | Application candidate, exact code defect unverified |
| 08 | Throttles and current reserved concurrency zero | Capacity candidate; historical cause/intent still need verification |
| 09 | Denied event predates incident | Historical error alone cannot explain this incident |
| 10 | Connectivity complaint; logs unreadable | Visibility gap; exact VPN/firewall block unknown |
| 11 | Dependency timeout | Connectivity hypothesis; no exact blocking rule or VPN claim |
| 12 | Nearby deployment; no failed-request evidence | A change alone does not establish an incident explanation |

Cases 01–05 were reused from the existing development suite. Cases 06–12 are newly authored synthetic variations, not live incident records. There are only 12 distinct cases; 72 repeated arm runs do not create 72 independent incidents. The input cases are deliberately simple and single-application. Incident categories and fixed next-step text constrain what can be measured.

## Comparisons

Both model arms use the same model and available recorded checks, with six planning calls maximum and a 60-second cooperative deadline per investigation. Use the same region and inference settings. Record returned token usage and failures. Seeded execution order mixes arms/cases; provider stochasticity is not controlled by that seed.

Rules get two descriptive baselines: initial observations only, and every recorded check up front. The latter is a coverage reference with privileged up-front availability; it is not an equal-cost adaptive competitor. Do not claim adaptive superiority from having more observations than the initial-only rules. Human reviewers assess actual useful findings and evidence, not exact title matches.

## Outcomes

Primary exploratory outcome: human-reviewed unsupported accepted category counts, by arm and distinct case. Also score unsupported raw proposals; a validator blocking its own prohibited output is not proof that the model reasoned better.

Tradeoffs: supported useful categories retained, missed useful categories, appropriate uncertainty, useful next checks, invalid/unfinished runs, provider errors, check attempts, token usage, and elapsed wall time. Deadline-stopped and rejected runs remain in the denominator. Do not score every empty result as a success. Counterevidence and citations require human review; automatic rubric passes are only structural/category checks.

Aggregate repeats within each case and show paired case results. Report counts and denominators, including ties and failures. This small development pilot does not justify population-level confidence or statistical significance claims. Token costs require the selected model's applicable rates; timings on recorded checks do not measure live AWS latency or human incident-resolution time.

## Provisional continuation gate

Choose the following gate before real inference, and retain it even if the results disappoint:

- All local contracts pass; live healthy and permission-failure collection is subsequently verified.
- Human review shows fewer unsupported accepted categories in the constrained arm on at least two distinct cases, without losing useful supported categories on more than one distinct case. Define each case outcome by the majority of its three repeats; report raw repeat counts too.
- Useful uncertainty is not achieved by universally returning empty or rejected answers. Inspect supported positive cases individually.
- If basic produces no unsupported categories, this pilot cannot demonstrate reduction. Do not worsen the baseline or rewrite cases to manufacture an effect.
- Related-work review identifies a defensible contribution and a feasible next evaluation. Novelty is currently unassessed.

This gate chooses whether to spend on a larger evaluation; it is not a paper acceptance threshold. If promising, freeze the method and create additional independently authored/collected cases without tuning on their outputs. Include more than one application and realistic missing/contradictory telemetry before general claims. Retain any null/negative findings.

## Paper status

No model benefit, live accuracy, production readiness, or novelty has been established. A paper outline can be drafted now, but results and claims wait for actual evidence. A useful engineering project can remain worthwhile if research novelty is insufficient.
