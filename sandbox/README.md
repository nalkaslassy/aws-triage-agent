# Disposable Orders API sandbox

This lab is prepared for live testing, but has not been deployed or validated in an AWS account. The investigator is still deterministic; no LLM or Datadog connection is configured.

## What it deploys

An IAM-authenticated regional API Gateway REST API, one Python Lambda function, a DynamoDB on-demand table, a three-day CloudWatch log group, and a narrowly scoped Lambda execution role. Lambda/API tracing is enabled, but trace retrieval is not implemented. There is no VPC, NAT gateway, VPN, or database instance. This lab tests application failures; it does not validate network or VPN diagnosis.

The API is internet-addressable and requires IAM-signed requests. It is not a private network endpoint. The API has a low request throttle; this reduces accidental traffic but is not a spending cap. Usage of API Gateway, Lambda, DynamoDB, CloudWatch, X-Ray, and SAM artifact storage can incur charges. This milestone does not estimate a dollar cost or configure a budget.

Use a separate sandbox account and synthetic data. The operator deploys/changes scenarios; the investigator only reads evidence. Do not run fault injection against an existing production application.

## Local checks (no AWS credentials or calls)

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python sandbox/local_evaluation.py
```

The local evaluation invokes the real handler with stubbed DynamoDB responses, then feeds emitted logs and mocked configuration into the investigator. The throttling case models platform metrics/configuration and does not invoke the handler. Ground truth is held by the harness, separate from investigator input. Passing these cases establishes local contract behavior, not root-cause accuracy in real incidents. See [the checked-in local result](local-evaluation.json).

For SDK contracts and infrastructure validation:

```bash
python -m pip install -e '.[aws]' 'cfn-lint>=1,<2'
python -m unittest discover -s tests -v
cfn-lint sandbox/template.yaml
```

## Prepare the live lab

Install the AWS CLI and AWS SAM CLI using AWS's official instructions. Configure an existing sandbox profile; credentials do not belong in the repository. The deployment identity needs the necessary CloudFormation/SAM artifact, API Gateway, Lambda, DynamoDB, log group, and IAM deployment permissions. The template creates only the application's execution role, not an investigator or operator role.

From the repository root:

```bash
export AWS_PROFILE=your-sandbox-profile
export AWS_DEFAULT_REGION=us-east-1
umask 077
mkdir -p evidence reports
aws sts get-caller-identity
sam validate --lint --template-file sandbox/template.yaml
sam build --template-file sandbox/template.yaml
sam deploy --stack-name triage-sandbox-orders --region us-east-1 \
  --capabilities CAPABILITY_IAM --resolve-s3 --confirm-changeset \
  --parameter-overrides FaultMode=normal BuildRevision=first-sandbox \
  --tags Project=aws-triage-agent Environment=sandbox
```

Review the account identity and change set before executing. The helper requires a stack name beginning `triage-sandbox-` and a suffix no longer than 25 characters. Both tags shown above are required. This milestone supports the standard `aws` partition; other AWS partitions are rejected by the probe helper.

`sam build` prepares local artifacts. `sam deploy` creates or updates real AWS resources. The project does not invoke either deployment command automatically.

## Create the collection manifest

After CloudFormation reports `CREATE_COMPLETE` or `UPDATE_COMPLETE`:

```bash
aws cloudformation describe-stacks --stack-name triage-sandbox-orders \
  --region us-east-1 > evidence/stack-normal.json
aws-triage sandbox manifest --outputs evidence/stack-normal.json \
  --out application.local.json
```

The generated manifest identifies the account, region, function, log group, intended table, stack ARN, and API ID. It excludes CloudFormation's fault-selection parameter. The investigator does not read stack parameters or the function's `FAULT_MODE` environment setting.

The collector now needs `lambda:GetFunctionConfiguration` and `lambda:GetFunctionConcurrency` for the explicitly configured function, in addition to its existing metric/log permissions. Configuration retrieval includes the environment in SDK memory; only the `ORDERS_TABLE` value is retained. Do not collect a production function if merely reading its environment is outside your authorization.

## Send one synthetic request

The operator identity must already have `cloudformation:DescribeStacks` for this stack and `execute-api:Invoke` for the API's `sandbox/POST/orders` route. The helper does not grant those permissions. Prefer a separate read-only profile for investigation.

```bash
aws-triage sandbox probe --manifest application.local.json \
  --out evidence/probe-normal.json
```

This makes one signed POST and may create one synthetic DynamoDB item. It checks the live account, stack tags, completed stack status, and outputs before sending. It never follows HTTP redirects and never logs credentials, signed headers, or response bodies. The result retains HTTP status and the API Gateway request ID. An expected normal response is HTTP 201; 401/403 may indicate probe identity/API authorization rather than an injected application failure. A timeout remains a transport observation, not proof of a specific network block.

Items have a one-hour TTL value, but DynamoDB deletion is asynchronous and may occur substantially later. Stack cleanup is the reliable way to remove the lab table.

## Collect and investigate

Allow time for CloudWatch metrics/logs to arrive. Use a UTC window spanning the request and at most one hour; choose a complete minute boundary before and after the request because CloudWatch aggregates metrics by period. Do not mix multiple scenarios into the same window.

```bash
aws-triage collect --manifest application.local.json \
  --start 2026-10-31T19:00:00Z --end 2026-10-31T19:10:00Z \
  --out evidence/normal.json
aws-triage analyze evidence/normal.json --out reports/normal.md
```

Replace those example times with the actual probe window. Zero Lambda `Errors` is not proof of a healthy API: this application returns handled HTTP 500/502 responses and logs the underlying failure. Metrics may initially have no datapoints. The investigator must use the logs and disclose missing visibility.

Current configuration is collected at investigation time, not reconstructed at incident onset. Collect before restoring the scenario, and preserve separate snapshots if comparing before/after behavior. A table mismatch is relative to the manifest, whose intended value should also be checked with the application owner.

## Fault scenarios and recovery

Update the same sandbox stack with exactly one `FaultMode` using the same `sam deploy` command above and the same tags. Change `FaultMode=normal` to one value below, and review the update change set. Wait for `UPDATE_COMPLETE` before probing. Return to `normal` between cases and verify a successful request. Keep the ground-truth record of selected mode separate from the evidence supplied to the investigator.

| Mode | Actual injected behavior | Expected evidence / limitations |
| --- | --- | --- |
| `normal` | Writes an order | HTTP 201; no supported failure established in available evidence |
| `permission_denied` | Removes the function's `PutItem` allow policy | Dependency `AccessDeniedException`; logs identify request, operation, and target. The current investigator does not evaluate effective IAM policy layers. |
| `code_exception` | Raises a controlled application exception | Handled HTTP 500 and structured exception log; no assumption that Lambda `Errors` rises |
| `wrong_table` | Changes table configuration to an uncreated lab target, with scoped permission to that target | `ResourceNotFoundException` plus configured/intended table mismatch |
| `throttle` | Sets function reserved concurrency to zero | Current concurrency zero, invocation throttles, and no application log for the rejected invocation. API error details can vary. |

Recovery is always an operator action: redeploy `FaultMode=normal`, wait for completion, regenerate the manifest if outputs changed, and send another synthetic request using a new output filename. No AI or investigator performs remediation. Keep prior reports and use unique output filenames because the CLI refuses overwrite.

## Cleanup

When finished, run `sam delete --stack-name triage-sandbox-orders --region us-east-1` and review its prompts. The lab table and log group have no retain policy and are deleted with the stack. Confirm deletion and inspect SAM's managed deployment artifact bucket for remaining artifacts; removing the stack does not establish that all account-level SAM artifact storage has disappeared. Do not delete a shared artifact bucket without checking its other uses.

## What remains before claiming milestone 0.2 complete

Deploy and exercise the real AWS cases, verify logged request IDs and HTTP outcomes, gather incident windows, record delayed/partial telemetry, and compare findings against ground truth. Scoped IAM policy inspection, deployment history correlation, trace retrieval, and live performance measurements are still pending.

References: [SAM build](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-build.html), [SAM validation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference-sam-validate.html), [API authentication](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-api-apiauth.html), [Lambda reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html).
