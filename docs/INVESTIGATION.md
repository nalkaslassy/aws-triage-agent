# Investigation behavior and limits

## Reliability

Imported evidence validates fields by kind. Booleans cannot masquerade as counts or concurrency zero. Strings, negative values, non-finite values, and values above `1e18` are rejected for numeric fields. Log counts and concurrency must be integers. Metadata, timestamps, evidence IDs, and source URLs have explicit constraints. This validates a contract, not the truth of imported evidence.

A later log-page failure preserves earlier signals/sample references with `partial` status. A first-page failure is `unavailable`. Lambda/API metrics retain successful fields when other queries fail. Missing fields are null, not zero. Partial metric groups are not used for rates or baseline comparisons.

Log collection uses a fixed error-keyword OR filter and at most three pages of one hundred candidates per group. Empty pages with continuation tokens are followed. Stalled pagination, exhausted budgets, and query failures are disclosed. Signal counts are not application-wide error totals.

Structured `dependency_failure`/`application_exception` events and supported error-level text can produce hypotheses. Bare/informational/warning keyword mentions do not. Error-level records can still be misleading or handled; unusual log formats may be missed. No pattern match alone proves root cause.

## Customer-facing REST API metrics

Each configured REST API specifies its API ID, exact ASCII metric name, and stage. Up to two can be collected. Queries use `ApiName`/`Stage` dimensions in `AWS/ApiGateway`; API-name uniqueness must be established by the operator. These dimensions do not isolate endpoints or users. HTTP API metrics use a different schema and are not supported here.

| Value | Calculation across the window |
| --- | --- |
| Requests | `Count`: sum of `SampleCount` |
| Server errors | `5XXError`: sum of `Sum` |
| Client errors | `4XXError`: sum of `Sum` |
| Mean API latency | `Latency`: total `Sum` / total `SampleCount` |
| Mean integration latency | `IntegrationLatency`: total `Sum` / total `SampleCount` |

API query windows are minute-aligned UTC, at most one hour. The baseline ends at incident start and has equal duration. Rate comparison needs a unique matching baseline, complete query groups, positive request volumes, and consistent counts (server errors no larger than requests). Missing datapoints remain unknown, including absent error metrics.

Positive 4xx/5xx counts are observations, not cause claims. Valid 5xx rates show the preceding baseline and percentage-point change. Delayed telemetry, sparse data, traffic changes, or a prior incident may make that baseline unsuitable.

A mean-latency hypothesis requires at least a twofold increase and twenty requests in each window. This is a screening heuristic, not statistical anomaly detection, tail-latency analysis, or proof of an SLO breach.

## Limited correlation

A table-mismatch explanation cites two sources only when the log group maps to the configured function, a retained missing-resource `PutItem` sample includes a request ID and matching table inside the incident window, and that function's current table differs from the manifest. The manifest can be stale, and current configuration can postdate the request. Effective IAM policy and historical configuration are not evaluated by this check.

## Reports

Findings name their resource and link to an evidence index. The index includes source operation, collection time, status, selected metrics/configuration, and safe sample identifiers. Arbitrary imported messages are excluded; Markdown labels are escaped. Source URLs are restricted to HTTPS AWS console hosts.

Console pointers open the relevant service, not an immutable event permalink. Use resource, stream, event/request ID, and timestamp to locate the original evidence. Retain the original bundle separately. Synthetic local evaluation has no live source links.

## Remaining work

The [bounded adaptive runtime](AGENT.md) now supports opt-in model-selected follow-ups, current IAM simulation, and limited function change lookup. Replay/SDK contracts are tested; live model quality and AWS diagnosis remain unverified. Request/trace topology, full deployment/IAM history, effective authorization reconstruction, network paths, representative client probes, and Datadog ingestion remain pending. These changes configure no cloud resources or production permissions.

References: [API metric definitions](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-metrics-and-dimensions.html), [log filtering and pagination](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_FilterLogEvents.html).
