# Milestones

## 0.1 — Investigation foundation (implemented locally)

Offline evidence analysis, initial AWS collectors, reproducible examples, bounded access, explicit gaps, and behavioral tests. Live AWS verification remains pending.

## 0.2 — First complete application investigation

Status: deployment preparation implemented; live AWS validation pending. The Orders API template, structured error logs, five local scenarios, configuration/concurrency checks, sandbox manifest creation, and one-request IAM-signed operator probe are available. See [the lab guide](../sandbox/README.md). These are local contracts, not measured real-incident diagnosis results.

The next increment adds typed evidence validation, partial-result retention, failure-context log classification, REST API incident/baseline metrics, evidence-index reports, and limited same-function table-target correlation. See [behavior and limits](INVESTIGATION.md). Broader trace/change/IAM/network investigation is still pending.

- Deploy a small Orders API in a sandbox using infrastructure as code.
- Add traces, deployment/change history, and scoped permission evidence.
- Exercise permission removal, code exception, throttling, wrong dependency configuration, and a healthy baseline.
- Correlate a failure to its request, principal, action, target, and time.
- Verify the collector against the real sandbox; preserve a sanitized evidence bundle.

Acceptance: evidence supports the explanation; no failing permission check becomes a healthy result; no broad permission grant is recommended as a default fix.

## 0.3 — Connectivity investigation

- Explicit destination hostname, IP/port, source network, and relevant VPN endpoint.
- Compare affected and unaffected cohorts where identity access is authorized.
- Add relevant routes, network ACLs, VPN connection logs, and flow-log evidence.
- Evaluate supported AWS paths; handle analysis permissions and costs explicitly.
- Use controlled probes from representative locations for DNS, TCP, TLS, and HTTP.
- Test missing route, blocked port, missing VPN destination authorization, DNS failure, and an external/client failure with incomplete visibility.

Acceptance: distinguish VPN authentication, destination authorization, DNS, transport, TLS, and application failures; name an exact blocking control only when evidence supports it.

## 0.4 — Datadog and model-driven investigation

- Normalize an alert to a service/environment/time window; authenticated webhook ingestion with duplicate suppression.
- Read scoped Datadog metrics, logs, and traces through a provider adapter.
- Add a model behind an explicit data-sharing boundary and allowlisted tool interface.
- Enforce a tool/time budget; validate evidence citations; record investigation actions.
- Rank competing hypotheses with evidence for/against, and update findings as evidence changes.
- Test misleading log instructions, irrelevant historical errors, missing sources, and contradictory observations.

Acceptance: compare against deterministic triage and existing investigation options; measure time to useful finding, diagnosis accuracy, unsupported claims, abstention, coverage, and cost. Model integration must improve something measurable before expanding scope.

## Later

Ticket/channel integration, application onboarding, multi-account support, and additional stacks after the initial workflow works. Human-reviewed recommendations remain the default; production auto-remediation is not part of these milestones.
