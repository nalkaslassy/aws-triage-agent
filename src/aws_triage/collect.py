"""Explicitly scoped AWS collection; no arbitrary API or shell execution."""

import re
from datetime import datetime, timezone

from .model import Bundle, Evidence, utc_time
from .signals import classify
from .api_metrics import collect_api_metrics
from urllib.parse import quote


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object")
    if not re.fullmatch(r"\d{12}", manifest.get("account_id", "")):
        raise ValueError("A 12-digit account_id is required")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", manifest.get("region", "")):
        raise ValueError("An explicit AWS region is required")
    if not isinstance(manifest.get("application"), str) or not manifest["application"].strip():
        raise ValueError("application is required")
    specs = {"lambda_functions": r"[A-Za-z0-9_-]{1,64}",
             "log_groups": r"[.\-_/#A-Za-z0-9]{1,512}",
             "security_groups": r"sg-[0-9a-f]{8,17}"}
    for key, pattern in specs.items():
        values = manifest.get(key, [])
        if not isinstance(values, list) or len(values) > 5 or any(
            not isinstance(v, str) or not re.fullmatch(pattern, v) for v in values
        ):
            raise ValueError(f"{key} must contain at most five valid explicit resource names/IDs")
    endpoint = manifest.get("client_vpn_endpoint")
    if endpoint is not None and not re.fullmatch(r"cvpn-endpoint-[0-9a-f]{8,17}", endpoint):
        raise ValueError("Invalid Client VPN endpoint ID")
    expected = manifest.get("expected_tables", {})
    if not isinstance(expected, dict) or any(
        function not in manifest.get("lambda_functions", [])
        or not isinstance(table, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", table)
        for function, table in expected.items()
    ):
        raise ValueError("expected_tables must map configured functions to explicit DynamoDB table names")
    apis = manifest.get("rest_apis", [])
    if not isinstance(apis, list) or len(apis) > 2:
        raise ValueError("At most two REST APIs may be configured")
    identities = set()
    for api in apis:
        if not isinstance(api, dict) or set(api) != {"api_id", "api_name", "stage"}:
            raise ValueError("REST APIs require api_id, api_name, and stage")
        for key, pattern in {"api_id": r"[a-z0-9]{10}", "api_name": r"[A-Za-z0-9_.-]{1,128}",
                             "stage": r"[A-Za-z0-9_-]{1,128}"}.items():
            if not isinstance(api[key], str) or not re.fullmatch(pattern, api[key]):
                raise ValueError(f"Invalid REST API {key}")
        identity = (api["api_name"], api["stage"])
        if identity in identities:
            raise ValueError("REST API metric scopes must be unique")
        identities.add(identity)


class AWSCollector:
    def __init__(self, session, manifest, start, end):
        validate_manifest(manifest)
        self.start, self.end = utc_time(start).astimezone(timezone.utc), utc_time(end).astimezone(timezone.utc)
        if not 0 < (self.end - self.start).total_seconds() <= 3600:
            raise ValueError("Collection window must be positive and at most one hour")
        if self.end > datetime.now(timezone.utc):
            raise ValueError("Collection window cannot end in the future")
        if manifest.get("rest_apis") and any(d.second or d.microsecond for d in (self.start, self.end)):
            raise ValueError("API collection requires minute-aligned UTC start/end boundaries")
        self.manifest = manifest
        self.session = session
        self.evidence = []
        self.calls = 0
        self.clients = {}

    def call(self, service, operation, **kwargs):
        self.calls += 1
        if self.calls > 75:
            raise RuntimeError("Collection call budget exhausted")
        if service not in self.clients:
            from botocore.config import Config
            self.clients[service] = self.session.client(
                service, region_name=self.manifest["region"],
                config=Config(connect_timeout=5, read_timeout=10,
                              retries={"total_max_attempts": 2, "mode": "standard"}),
            )
        return getattr(self.clients[service], operation)(**kwargs)

    def add(self, kind, resource, source, data, status="observed"):
        region = self.manifest["region"]
        url = None
        if source.startswith("lambda:"):
            url = f"https://console.aws.amazon.com/lambda/home?region={region}#/functions/{quote(resource, safe='')}"
        elif source.startswith("logs:"):
            url = f"https://console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups"
        elif source.startswith("cloudwatch:"):
            url = f"https://console.aws.amazon.com/cloudwatch/home?region={region}#metricsV2:"
        elif source.startswith("iam:"):
            url = "https://console.aws.amazon.com/iam/home#/roles"
        elif source.startswith("cloudtrail:"):
            url = f"https://console.aws.amazon.com/cloudtrailv2/home?region={region}#/events"
        self.evidence.append(Evidence(
            f"E{len(self.evidence) + 1:03}", kind, resource, source, status, data,
            datetime.now(timezone.utc).isoformat(), source_url=url,
        ))

    @staticmethod
    def error_code(error):
        code = getattr(error, "response", {}).get("Error", {}).get("Code", type(error).__name__)
        return code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code) else "UnknownError"

    def attempt(self, kind, resource, source, action):
        try:
            action()
        except Exception as error:
            # SDK messages may embed sensitive request data. Retain only codes.
            code = self.error_code(error)
            self.add(kind, resource, source, {"reason": f"Collection failed ({code}); the resource's health is unknown.", "error_code": code}, "unavailable")

    def metrics(self, function):
        data, failures, successes = {}, [], 0
        for metric in ("Errors", "Invocations", "Throttles"):
            try:
                response = self.call("cloudwatch", "get_metric_statistics", Namespace="AWS/Lambda",
                                     MetricName=metric, Dimensions=[{"Name": "FunctionName", "Value": function}],
                                     StartTime=self.start, EndTime=self.end, Period=60, Statistics=["Sum"])
                points = response.get("Datapoints", [])
                data[metric] = sum(p["Sum"] for p in points) if points else None
                successes += 1
            except Exception as error:
                data[metric] = None
                failures.append(f"{metric}: {self.error_code(error)}")
        if failures:
            data["reason"] = "Some metrics could not be read: " + ", ".join(failures)
        self.add("lambda_metrics", function, "cloudwatch:GetMetricStatistics", data,
                 "partial" if failures and successes else "unavailable" if failures else "observed")

    def logs(self, group):
        counts = {name: 0 for name in ("access_denied", "timeout", "exception", "resource_missing", "unverified_mentions")}
        token, seen, sampled, pages = None, set(), [], 0
        reason, status, error_code = "", "observed", None
        for _ in range(3):
            args = dict(logGroupName=group, startTime=int(self.start.timestamp() * 1000),
                        endTime=int(self.end.timestamp() * 1000), limit=100,
                        filterPattern='?ERROR ?Error ?error ?Exception ?exception ?Traceback ?timeout ?ETIMEDOUT ?denied ?dependency_failure ?application_exception ?AccessDenied ?AccessDeniedException ?ResourceNotFoundException ?TimeoutError')
            if token:
                args["nextToken"] = token
            try:
                response = self.call("logs", "filter_log_events", **args)
            except Exception as error:
                status = "partial" if pages else "unavailable"
                code = self.error_code(error)
                error_code = code
                reason = f"Log retrieval stopped ({code}); earlier observations are retained; remaining events are unknown."
                break
            pages += 1
            for event in response.get("events", []):
                identity = event.get("eventId")
                if identity and identity in seen:
                    continue
                if identity:
                    seen.add(identity)
                signals, details, mention = classify(event.get("message", ""))
                counts["unverified_mentions"] += int(mention)
                for name in sorted(signals):
                    counts[name] += 1
                    if len(sampled) < 20:
                        sampled.append({"signal": name, "event_id": identity,
                                        "timestamp": event.get("timestamp"),
                                        "stream": event.get("logStreamName"), **details})
            next_token = response.get("nextToken")
            if next_token and next_token == token:
                reason, status = "Pagination stalled; log evidence is incomplete.", "partial"
                break
            token = next_token
            if not token:
                break
        else:
            if token:
                reason, status = "Three-page log budget reached; sample is incomplete.", "partial"
        data = {**counts, "samples": sampled, "pages_collected": pages,
                "selection": "bounded error-keyword query; other log formats may be missed", "reason": reason}
        if error_code:
            data["error_code"] = error_code
        function = group.removeprefix("/aws/lambda/")
        if group.startswith("/aws/lambda/") and function in self.manifest.get("lambda_functions", []):
            data["function_name"] = function
        self.add("log_signals", group, "logs:FilterLogEvents", data, status)

    def function_configuration(self, function):
        response = self.call("lambda", "get_function_configuration", FunctionName=function)
        environment = response.get("Environment", {})
        data = {key: response.get(key) for key in (
            "FunctionArn", "Role", "CodeSha256", "LastModified", "RevisionId", "State", "LastUpdateStatus")}
        # Only the explicitly non-secret table target is retained, never the
        # full environment (which Lambda returns in the API response).
        data["orders_table"] = environment.get("Variables", {}).get("ORDERS_TABLE")
        data["expected_table"] = self.manifest.get("expected_tables", {}).get(function)
        if environment.get("Error"):
            self.add("lambda_configuration", function, "lambda:GetFunctionConfiguration",
                     {**data, "reason": "Lambda environment configuration could not be read."}, "partial")
        else:
            self.add("lambda_configuration", function, "lambda:GetFunctionConfiguration", data)

    def function_concurrency(self, function):
        response = self.call("lambda", "get_function_concurrency", FunctionName=function)
        self.add("lambda_concurrency", function, "lambda:GetFunctionConcurrency",
                 {"reserved_concurrency": response.get("ReservedConcurrentExecutions")})

    def security_groups(self):
        groups = self.manifest.get("security_groups", [])
        if not groups:
            return
        response = self.call("ec2", "describe_security_groups", GroupIds=groups)
        data = [{key: g.get(key) for key in ("GroupId", "VpcId", "IpPermissions", "IpPermissionsEgress")}
                for g in response.get("SecurityGroups", [])]
        self.add("security_group_configuration", ",".join(groups), "ec2:DescribeSecurityGroups", {"groups": data})

    def vpn(self, endpoint, operation, key, kind, fields):
        response = self.call("ec2", operation, ClientVpnEndpointId=endpoint, MaxResults=100)
        items = [{field: row.get(field) for field in fields} for row in response.get(key, [])]
        self.add(kind, endpoint, "ec2:" + operation, {"items": items,
                 "reason": "Only the first page was collected." if response.get("NextToken") else ""},
                 "partial" if response.get("NextToken") else "observed")

    def collect(self):
        # Fail closed before collecting application telemetry from the wrong account.
        identity = self.call("sts", "get_caller_identity")
        if identity["Account"] != self.manifest["account_id"]:
            raise ValueError("Authenticated AWS account does not match the manifest; collection stopped")
        self.add("collector_identity", self.manifest["account_id"], "sts:GetCallerIdentity",
                 {"account_id": identity["Account"], "region": self.manifest["region"]})
        for api in self.manifest.get("rest_apis", []):
            collect_api_metrics(self, api)
        for function in self.manifest.get("lambda_functions", []):
            self.attempt("lambda_metrics", function, "cloudwatch:GetMetricStatistics", lambda f=function: self.metrics(f))
            self.attempt("lambda_configuration", function, "lambda:GetFunctionConfiguration",
                         lambda f=function: self.function_configuration(f))
            self.attempt("lambda_concurrency", function, "lambda:GetFunctionConcurrency",
                         lambda f=function: self.function_concurrency(f))
        for group in self.manifest.get("log_groups", []):
            self.attempt("log_signals", group, "logs:FilterLogEvents", lambda g=group: self.logs(g))
        self.attempt("security_group_configuration", "configured groups", "ec2:DescribeSecurityGroups", self.security_groups)
        endpoint = self.manifest.get("client_vpn_endpoint")
        if endpoint:
            for operation, key, kind, fields in [
                ("describe_client_vpn_connections", "Connections", "vpn_connections", ["Status", "ConnectionEstablishedTime"]),
                ("describe_client_vpn_routes", "Routes", "vpn_routes", ["DestinationCidr", "TargetSubnet", "Status", "Type"]),
                ("describe_client_vpn_authorization_rules", "AuthorizationRules", "vpn_authorization", ["DestinationCidr", "GroupId", "AccessAll", "Status"]),
            ]:
                self.attempt(kind, endpoint, operation,
                             lambda o=operation, k=key, t=kind, f=fields: self.vpn(endpoint, o, k, t, f))
        for gap in ("identity_and_resource_policies", "deployment_and_change_history", "client_dns_and_corporate_network",
                    "end_to_end_connectivity_tests", "traces_and_dependency_health"):
            self.add(gap, self.manifest["application"], "collector coverage",
                     {"reason": "Not implemented in this milestone; do not infer a successful check."}, "not_collected")
        return Bundle(self.manifest["application"], self.start.isoformat(), self.end.isoformat(), self.evidence)
