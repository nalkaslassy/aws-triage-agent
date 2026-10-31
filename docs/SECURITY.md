# Security and access

The collector performs fixed read operations. It cannot modify the investigated infrastructure. Reads can expose sensitive data; use an application-specific role and review evidence before sharing. No production credentials or infrastructure access have been configured by this starter.

## Required operations for the implemented collector

| Operation | Purpose | Scope guidance |
| --- | --- | --- |
| `sts:GetCallerIdentity` | Fail closed on account mismatch | Existing authenticated identity |
| `cloudwatch:GetMetricStatistics` | Lambda Errors, Invocations, Throttles | Region/account role boundary; metric APIs may require `Resource: *` |
| `logs:FilterLogEvents` | Bounded application error samples | Explicit application log-group ARNs |
| `ec2:DescribeSecurityGroups` | Configured security groups only | Region/account boundary; API resource-level restrictions are limited |
| `ec2:DescribeClientVpnConnections` | Current session status snapshot | Optional; region/account boundary |
| `ec2:DescribeClientVpnRoutes` | VPN destination route snapshot | Optional; region/account boundary |
| `ec2:DescribeClientVpnAuthorizationRules` | VPN destination authorization snapshot | Optional; region/account boundary |

This table is an implementation inventory, not a deployable IAM policy. Do not attach AdministratorAccess or grant new cloud access merely to run the demo. Service APIs differ in resource-level IAM support. The manifest limits what this program requests; IAM must enforce the actual security boundary.

## Collection limits

- One account and explicit region; maximum five functions, five log groups, five security groups, one Client VPN endpoint.
- Incident window at most one hour.
- At most 50 SDK operation attempts at the application layer; SDK retry configuration permits up to two HTTP attempts per operation.
- At most three log pages of up to 100 events each per group; pagination gaps are disclosed.
- VPN snapshots collect one page of up to 100 records and disclose continuation.
- API timeouts are bounded; there is not yet a global wall-clock cancellation mechanism.

## Data handling

Raw log messages are processed in memory and are not stored in generated bundles. Event IDs and network/resource identifiers can still be sensitive. Files are created with mode `0600` and refuse overwrite; parent-directory and backup security remain the operator's responsibility. Git ignores `evidence/`, `reports/`, local manifests, credential-like files, and environment files. File permissions do not substitute for access controls on a shared computer.

Never commit real telemetry or credentials. Use existing short-lived credential profiles when collecting. Secrets Manager, SSM decryption, arbitrary S3 reads, resource modification, arbitrary shell commands, and application request execution are not part of the collector.

No LLM is integrated yet. Before adding one, define allowed fields, redaction, retention, provider destination, and per-investigation transmission rules. A generated suggestion never grants authority for remediation.

## Reporting suspected issues

Keep this repository private during development. Report project security issues through a private channel to the owner; do not paste production telemetry into public issues.
