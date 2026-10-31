# Investigation: synthetic-orders-demo

Window: 2026-10-30T12:00:00Z to 2026-10-30T12:15:00Z

Status: first-pass triage; remediation requires engineer review.

## API server-side errors observed

Classification: confirmed_observation; evidence: [E002](#e002), [E003](#e003)

The API stage recorded 35 server-side errors. Observed 5xx rate: 35.00% (35/100 requests). Preceding equal-length baseline: 1.00%; change +34.00 percentage points. These are API responses, not Lambda execution errors; cause and affected user population remain unresolved.

Suggested owner: Application / platform team

Affected resource: orders-api/sandbox \(abc123def4\)

- Correlate failed API requests with application logs and dependency traces.
- Verify that this stage and baseline represent the reported impact.

## API mean latency increased against the adjacent baseline

Classification: hypothesis; evidence: [E002](#e002), [E003](#e003)

Mean latency rose from 150 ms to 500 ms. This uses a twofold-increase heuristic with at least twenty requests in both windows; it is not a statistical anomaly test or proof of an outage. Traffic mix and baseline suitability are unverified.

Suggested owner: Application / platform team

Affected resource: orders-api/sandbox \(abc123def4\)

- Compare API latency with integration latency, traffic volume, and downstream traces.

## Visibility gaps and remaining questions

- E002: API metrics use ApiName/Stage dimensions; name uniqueness and affected endpoints/users are unverified. The adjacent baseline may not represent normal behavior.
- Client/corporate VPN, DNS, and firewall behavior is unverified unless evidence from that location is supplied. Requests blocked before reaching the application may leave no application error.

## Evidence index

Console links open the relevant AWS service. Use the listed resource, time, and request identifiers to locate the evidence; these links do not pin an individual event.

### E001

Resource: orders-function
Source: synthetic fixture; status: observed; collected: 2026-10-30T12:16:00Z

- Errors: 0
- Invocations: 100
- Throttles: 0

### E002

Resource: orders-api/sandbox \(abc123def4\)
Source: synthetic fixture; status: observed; collected: 2026-10-30T12:16:00Z

- window: incident
- start: 2026-10-30T12:00:00Z
- end: 2026-10-30T12:15:00Z
- requests: 100
- server\_errors: 35
- client\_errors: 0
- latency\_ms: 500
- integration\_latency\_ms: 450

### E003

Resource: orders-api/sandbox \(abc123def4\)
Source: synthetic fixture; status: observed; collected: 2026-10-30T12:16:00Z

- window: baseline
- start: 2026-10-30T11:45:00Z
- end: 2026-10-30T12:00:00Z
- requests: 100
- server\_errors: 1
- client\_errors: 0
- latency\_ms: 150
- integration\_latency\_ms: 120

