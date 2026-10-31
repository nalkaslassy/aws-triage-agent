"""Sandbox-only onboarding and a bounded, IAM-signed synthetic order request.

This module is an operator tool, separate from the read-only investigator.
It never deploys infrastructure or changes the injected fault mode.
"""

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .collect import validate_manifest


def manifest_from_stack(description):
    stacks = description.get("Stacks", [])
    if len(stacks) != 1:
        raise ValueError("Expected exactly one CloudFormation stack")
    stack = stacks[0]
    tags = {t["Key"]: t["Value"] for t in stack.get("Tags", [])}
    if tags.get("Project") != "aws-triage-agent" or tags.get("Environment") != "sandbox":
        raise ValueError("Stack must have the project's sandbox tags")
    if stack.get("StackStatus") not in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
        raise ValueError("Stack must have a completed deployment")
    match = re.fullmatch(r"arn:aws:cloudformation:([a-z0-9-]+):(\d{12}):stack/(triage-sandbox-[A-Za-z0-9-]{1,25})/[A-Za-z0-9-]+",
                         stack.get("StackId", ""))
    if not match:
        raise ValueError("Use a standard AWS partition stack named triage-sandbox-<suffix> (suffix at most 25 characters)")
    region, account, name = match.groups()
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
    function = outputs["FunctionName"]
    if function != name + "-orders" or not re.fullmatch(r"[a-z0-9]{10}", outputs["ApiId"]):
        raise ValueError("Stack outputs do not match the sandbox layout")
    if outputs["LogGroup"] != "/aws/lambda/" + function:
        raise ValueError("Unexpected log group")
    manifest = {"application": function, "account_id": account, "region": region,
                "lambda_functions": [function], "log_groups": [outputs["LogGroup"]],
                "security_groups": [], "expected_tables": {function: outputs["ExpectedTable"]},
                "sandbox": {"stack_id": stack["StackId"], "api_id": outputs["ApiId"]}}
    validate_manifest(manifest)
    return manifest


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def probe(session, manifest, send=None):
    """Send one POST that may create one disposable synthetic order.

    Refuse non-sandbox targets. Verify account, live stack tags, and outputs
    before signing. Never log credentials, signed headers, or response bodies.
    """
    validate_manifest(manifest)
    sandbox = manifest.get("sandbox", {})
    stack_id = sandbox.get("stack_id", "")
    # Validate account/region before creating any CloudFormation client or making
    # calls with the supplied stack ARN.
    prefix = f"arn:aws:cloudformation:{manifest['region']}:{manifest['account_id']}:stack/triage-sandbox-"
    if not isinstance(stack_id, str) or not stack_id.startswith(prefix):
        raise ValueError("A sandbox stack in the manifest account and region is required")
    from botocore.config import Config
    config = Config(connect_timeout=5, read_timeout=10, retries={"total_max_attempts": 1})
    region = manifest["region"]
    identity = session.client("sts", region_name=region, config=config).get_caller_identity()
    if identity["Account"] != manifest["account_id"]:
        raise ValueError("Probe account mismatch")
    description = session.client("cloudformation", region_name=region, config=config).describe_stacks(StackName=stack_id)
    live = manifest_from_stack(description)
    if live != manifest:
        raise ValueError("Manifest differs from the live sandbox outputs; regenerate it")
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    credentials = session.get_credentials()
    if credentials is None:
        raise ValueError("No signing credentials available")
    url = f"https://{sandbox['api_id']}.execute-api.{region}.amazonaws.com/sandbox/orders"
    body = json.dumps({"sku": "synthetic-triage-probe", "quantity": 1}).encode()
    aws_request = AWSRequest(method="POST", url=url, data=body, headers={"Content-Type": "application/json"})
    SigV4Auth(credentials.get_frozen_credentials(), "execute-api", region).add_auth(aws_request)
    request = urllib.request.Request(url, data=body, headers=dict(aws_request.headers), method="POST")
    sender = send or urllib.request.build_opener(NoRedirect()).open
    start = datetime.now(timezone.utc).isoformat()
    result = {"application": manifest["application"], "start": start,
              "request_count": 1, "kind": "synthetic_order_probe", "writes_synthetic_data": True}
    try:
        with sender(request, timeout=10) as response:
            result["http_status"] = response.status
            result["gateway_request_id"] = response.headers.get("x-amzn-RequestId")
    except urllib.error.HTTPError as error:
        result["http_status"] = error.code
        result["gateway_request_id"] = error.headers.get("x-amzn-RequestId") if error.headers else None
        error.close()
    except (urllib.error.URLError, TimeoutError, OSError):
        result["http_status"] = None
        result["visibility_gap"] = "Transport failed from the operator's location; DNS/TCP/TLS cause is unresolved."
    result["end"] = datetime.now(timezone.utc).isoformat()
    return result
