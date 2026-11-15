# Security and access

The collector performs fixed read operations. It cannot modify the investigated infrastructure. Reads can expose sensitive data; use an application-specific role and review evidence before sharing. No production credentials or infrastructure access have been configured by this starter.

## Required operations for the implemented collector

| Operation | Purpose | Scope guidance |
| --- | --- | --- |
| `sts:GetCallerIdentity` | Fail closed on account mismatch | Existing authenticated identity |
| `cloudwatch:GetMetricStatistics` | Lambda and optional REST API incident/baseline metrics | Region/account role boundary; metric APIs may require `Resource: *` |
| `lambda:GetFunctionConfiguration` | Current role/code metadata and allowlisted table target | Explicit configured function ARNs; API response includes full environment in memory |
| `lambda:GetFunctionConcurrency` | Current reserved concurrency | Explicit configured function ARNs |
| `logs:FilterLogEvents` | Bounded application error samples | Explicit application log-group ARNs |
| `ec2:DescribeSecurityGroups` | Configured security groups only | Region/account boundary; API resource-level restrictions are limited |
| `ec2:DescribeClientVpnConnections` | Current session status snapshot | Optional; region/account boundary |
| `ec2:DescribeClientVpnRoutes` | VPN destination route snapshot | Optional; region/account boundary |
| `ec2:DescribeClientVpnAuthorizationRules` | VPN destination authorization snapshot | Optional; region/account boundary |

This table is an implementation inventory, not a deployable IAM policy. Do not attach AdministratorAccess or grant new cloud access merely to run the demo. Service APIs differ in resource-level IAM support. The manifest limits what this program requests; IAM must enforce the actual security boundary.

## Collection limits

- One account and explicit region; maximum five functions, five log groups, five security groups, one Client VPN endpoint, and two REST API stages.
- Incident window at most one hour.
- At most 75 SDK operation attempts at the application layer; SDK retry configuration permits up to two HTTP attempts per operation. Optional API collection adds a preceding equal-length baseline.
- At most three filtered log pages of up to 100 candidate events each per group; pagination gaps are disclosed and partial evidence is retained.
- VPN snapshots collect one page of up to 100 records and disclose continuation.
- Adaptive checks permit one extra attempt only for recognized transient read error codes, within existing step/time/75-operation budgets; SDK HTTP retry limits still apply. Access denials and scope/deadline failures are terminal.
- API timeouts are bounded; there is not yet a global wall-clock cancellation mechanism.

## Data handling

Raw log messages are processed in memory and are not stored in generated bundles. Request IDs, valid AWS root trace IDs, event IDs, and network/resource identifiers can still be sensitive. Files are created with mode `0600` and refuse overwrite; parent-directory and backup security remain the operator's responsibility. Git ignores `evidence/`, `reports/`, local manifests, credential-like files, and environment files. File permissions do not substitute for access controls on a shared computer.

Never commit real telemetry or credentials. Use existing short-lived credential profiles when collecting. Secrets Manager, SSM decryption, arbitrary S3 reads, resource modification, arbitrary shell commands, and application request execution are not part of the collector.

Lambda configuration retrieval includes all environment variables in SDK memory, even though only `ORDERS_TABLE` is retained in the bundle. Do not authorize collection where reading those variables is forbidden. Current configuration is not historical proof of incident-time state. The collector does not evaluate the execution role's effective permissions yet.

The optional sandbox operator helper is separate from collection. It reads the account identity and tagged CloudFormation stack, validates its outputs against the manifest, and sends at most one IAM-signed request to the stack's API. It may write one synthetic order. This requires existing stack-read and route-invoke permissions and never grants them, changes scenarios, or deploys resources. HTTP redirects are refused to protect signed headers. See [the sandbox guide](../sandbox/README.md).

A bounded Bedrock adapter is available with explicit model-data opt-in; live inference has not been exercised. The model receives curated evidence, not arbitrary raw log messages, full environments, or CloudTrail bodies. It proposes named checks; application code enforces scope, budgets, citations, and allowed next steps. Existing-profile `iam:SimulatePrincipalPolicy`, `cloudtrail:LookupEvents`, and `bedrock:InvokeModel` permissions may be needed for this opt-in workflow; the code grants none. See [the agent guide](AGENT.md) for transmitted fields, timeouts, and remaining evaluation. A generated suggestion never grants authority for remediation.

## Reporting suspected issues

Report suspected vulnerabilities privately to the repository owner before opening a public issue when disclosure could expose credentials, telemetry, or an exploitable weakness. Do not paste production telemetry, credentials, signed requests, or customer data into public issues. Public issues are appropriate for non-sensitive bugs and documentation problems.
