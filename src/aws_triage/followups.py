"""Read-only follow-ups chosen through named checks, never arbitrary SDK input."""

import re
import time
from datetime import timedelta

from .collect import AWSCollector

CHECKS = ("logs", "configuration", "permissions", "changes")


class DeadlineCollector(AWSCollector):
    def call(self, service, operation, **kwargs):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Investigation deadline reached")
        return super().call(service, operation, **kwargs)


class AWSFollowups:
    def __init__(self, session, manifest, bundle, function, seconds=60):
        if bundle.application != manifest.get("application") or function not in manifest.get("lambda_functions", []):
            raise ValueError("Function is outside the manifest")
        self.collector = DeadlineCollector(session, manifest, bundle.start, bundle.end)
        self.collector.deadline = time.monotonic() + seconds
        self.function = function
        identity = self.collector.call("sts", "get_caller_identity")
        if identity["Account"] != manifest["account_id"]:
            raise ValueError("Follow-up account mismatch")

    def run(self, check):
        if check not in CHECKS:
            raise ValueError("Unsupported check")
        c, function = self.collector, self.function
        before = len(c.evidence)
        try:
            if check == "logs":
                group = "/aws/lambda/" + function
                if group not in c.manifest.get("log_groups", []):
                    raise ValueError("Function log group is outside the manifest")
                c.logs(group)
            elif check == "configuration":
                c.function_configuration(function)
                c.function_concurrency(function)
            elif check == "permissions":
                self.permissions()
            else:
                self.changes()
        except Exception as error:
            c.add("followup_failure", function, check,
                  {"reason": f"Check could not be completed ({c.error_code(error)}); earlier evidence is retained."}, "unavailable")
        return list(c.evidence[before:])

    def permissions(self):
        c, function = self.collector, self.function
        c.function_configuration(function)
        config = c.evidence[-1]
        table = c.manifest.get("expected_tables", {}).get(function)
        role = config.data.get("Role")
        account, region = c.manifest["account_id"], c.manifest["region"]
        if (config.status != "observed" or not table or config.data.get("orders_table") != table
                or not isinstance(role, str)
                or not re.fullmatch(r"arn:aws:iam::" + account + r":role/[A-Za-z0-9+=,.@_/-]{1,640}", role)):
            c.add("permission_simulation", function, "iam:SimulatePrincipalPolicy",
                  {"reason": "Cannot bind the current execution role and configured target to the manifest. No simulation was run."}, "unavailable")
            return
        target = f"arn:aws:dynamodb:{region}:{account}:table/{table}"
        result = c.call("iam", "simulate_principal_policy", PolicySourceArn=role,
                        ActionNames=["dynamodb:PutItem"], ResourceArns=[target], MaxItems=10)
        rows = result.get("EvaluationResults", [])
        matching = [row for row in rows if row.get("EvalActionName") == "dynamodb:PutItem"
                    and row.get("EvalResourceName") == target]
        if len(matching) != 1:
            c.add("permission_simulation", function, "iam:SimulatePrincipalPolicy",
                  {"reason": "Simulation returned no unique matching evaluation."}, "unavailable")
            return
        row = matching[0]
        c.add("permission_simulation", function, "iam:SimulatePrincipalPolicy", {
            "role": role, "action": "dynamodb:PutItem", "target": target,
            "decision": row["EvalDecision"], "missing_context": row.get("MissingContextValues", [])[:20],
            "reason": "Current policy simulation only. Resource/endpoint policies, session context, and historical state may differ; the application's actual request principal is not established by its current execution role."
        }, "partial" if result.get("IsTruncated") else "observed")

    def changes(self):
        c = self.collector
        result = c.call("cloudtrail", "lookup_events", LookupAttributes=[{
            "AttributeKey": "ResourceName", "AttributeValue": self.function}],
            StartTime=c.start - timedelta(minutes=30), EndTime=c.end, MaxResults=10)
        # Never retain CloudTrailEvent, usernames, access keys, or request bodies.
        rows = []
        for event in result.get("Events", []):
            if event.get("ReadOnly") != "false":
                continue
            stamp = event.get("EventTime")
            if stamp is None or stamp.utcoffset() is None or not c.start - timedelta(minutes=30) <= stamp <= c.end:
                continue
            row = {key: event.get(key) for key in ("EventId", "EventName", "EventSource")}
            if any(not isinstance(value, str) or len(value) > 256 for value in row.values()):
                continue
            rows.append({**row, "EventTime": stamp.isoformat()})
        c.add("change_history", self.function, "cloudtrail:LookupEvents", {
            "events": rows, "reason": "One ResourceName-filtered page in the manifest region; not complete deployment or IAM history. Recent changes are correlation, not cause."
        }, "partial" if result.get("NextToken") else "observed")


class ReplayFollowups:
    """Synthetic/recorded evidence returned by named checks. No network access."""

    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.calls = []

    def run(self, check):
        from .model import Evidence
        self.calls.append(check)
        return [Evidence(**item) for item in self.fixtures.get(check, [])]
