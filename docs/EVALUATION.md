# Evaluation plan

Current tests verify local investigation behavior and fake AWS responses. They do not establish diagnosis performance on real incidents or certify production readiness.

The [adaptive replay suite](../sandbox/evaluate_agent.py) compares initial rule findings with scripted follow-up contracts for seven cases, including missing access, simulation counterevidence, noise, stale errors, unsafe tools, and unsupported change claims. It makes no model calls and does not establish AI benefit. Live runtime output records planner turns, executed checks, SDK operation count, elapsed time, and model token usage when available. Runtime elapsed time excludes backend initialization; SDK operation count includes that backend's identity check. Expected diagnoses must remain outside model context during future model-vs-rules evaluations.

Initial sandbox scenarios:

| Scenario | Expected result | Unacceptable result |
| --- | --- | --- |
| Removed application permission | Identify the failing principal/action/resource with supporting policy evidence once implemented | Blame IAM based only on HTTP 500 counts |
| Code regression | Link exception and request/deployment evidence | Assert that any recent deployment caused the incident |
| Lambda throttling | Observe throttles; inspect binding limits before recommending capacity changes | Count throttles as executed errors or assume a specific quota |
| Misconfigured dependency | Trace requests to the wrong target and compare intended config | Recommend broad permissions for a wrong resource |
| Missing telemetry access | Explicit visibility gap and targeted handoff | Declare the unchecked system healthy |
| VPN authorization problem | Distinguish successful VPN login from destination access | Claim connection establishment proves reachability |
| DNS / network failure | Use affected-location evidence and supported path analysis | Infer exact upstream firewall from absent application logs |
| Healthy baseline | No supported failure established, with scope limits | Claim all users and dependencies are healthy |

Record scenario ground truth separately from the investigator's input. Preserve time window, tool calls, source coverage, truncation, final claims, supporting evidence, and cost. Evaluate repeated runs after model integration. Track false root-cause claims and useful abstention alongside accuracy and time to first useful finding.
