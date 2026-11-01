"""Exercise real boto3 request/response models with Stubber; no live AWS."""

import importlib.util
import json
import unittest
from datetime import timedelta
from unittest.mock import Mock

from aws_triage.followups import AWSFollowups
from aws_triage.model import Bundle, utc_time
from aws_triage.planner import BedrockPlanner, DECISION_SCHEMA

HAS_SDK = importlib.util.find_spec("boto3") is not None
START, END = "2026-10-30T12:00:00Z", "2026-10-30T12:15:00Z"
ROLE = "arn:aws:iam::111122223333:role/orders-role"
TARGET = "arn:aws:dynamodb:us-east-1:111122223333:table/orders-table"


@unittest.skipUnless(HAS_SDK, "Install aws extra for SDK checks")
class FollowupSDKTests(unittest.TestCase):
    def setUp(self):
        import boto3
        from botocore.stub import Stubber
        session = boto3.Session(aws_access_key_id="synthetic-key", aws_secret_access_key="synthetic-secret", region_name="us-east-1")
        self.clients = {s: session.client(s) for s in ("sts", "lambda", "iam", "cloudtrail")}
        self.stubs = {s: Stubber(c) for s, c in self.clients.items()}
        for stub in self.stubs.values():
            stub.activate()
            self.addCleanup(stub.deactivate)
        self.session = Mock()
        self.session.client.side_effect = lambda service, **kwargs: self.clients[service]
        self.manifest = {"application": "orders", "account_id": "111122223333", "region": "us-east-1",
                         "lambda_functions": ["orders"], "log_groups": ["/aws/lambda/orders"],
                         "expected_tables": {"orders": "orders-table"}}
        self.bundle = Bundle("orders", START, END, [])

    def identity(self, account="111122223333"):
        self.stubs["sts"].add_response("get_caller_identity", {"Account": account,
            "UserId": "ABCDEFGHIJKLMNOPQRSTU", "Arn": f"arn:aws:iam::{account}:user/synthetic"}, {})

    def configuration(self, role=ROLE, target="orders-table"):
        self.stubs["lambda"].add_response("get_function_configuration", {
            "Role": role, "Environment": {"Variables": {"ORDERS_TABLE": target, "SECRET": "DO_NOT_RETAIN"}}}, {"FunctionName": "orders"})

    def test_policy_simulation_is_bound_to_current_role_and_manifest_target(self):
        self.identity()
        self.configuration()
        self.stubs["iam"].add_response("simulate_principal_policy", {"EvaluationResults": [{
            "EvalActionName": "dynamodb:PutItem", "EvalResourceName": TARGET, "EvalDecision": "implicitDeny", "MissingContextValues": []}]},
            {"PolicySourceArn": ROLE, "ActionNames": ["dynamodb:PutItem"], "ResourceArns": [TARGET], "MaxItems": 10})
        backend = AWSFollowups(self.session, self.manifest, self.bundle, "orders")
        evidence = backend.run("permissions")
        self.assertEqual(evidence[-1].data["decision"], "implicitDeny")
        self.assertEqual(evidence[-1].data["target"], TARGET)
        self.assertNotIn("DO_NOT_RETAIN", str(evidence))
        self.stubs["iam"].assert_no_pending_responses()

    def test_no_simulation_for_out_of_scope_role_or_wrong_table(self):
        for role, target in (("arn:aws:iam::999999999999:role/foreign", "orders-table"), (ROLE, "unexpected-table")):
            with self.subTest(role=role, target=target):
                self.identity()
                self.configuration(role, target)
                backend = AWSFollowups(self.session, self.manifest, self.bundle, "orders")
                result = backend.run("permissions")
                self.assertEqual(result[-1].status, "unavailable")
        self.assertNotIn("iam", [call.args[0] for call in self.session.client.call_args_list])

    def test_account_mismatch_prevents_further_reads(self):
        self.identity("999999999999")
        with self.assertRaises(ValueError):
            AWSFollowups(self.session, self.manifest, self.bundle, "orders")
        self.assertEqual([c.args[0] for c in self.session.client.call_args_list], ["sts"])

    def test_later_configuration_error_preserves_first_read(self):
        self.identity()
        self.configuration()
        self.stubs["lambda"].add_client_error("get_function_concurrency", service_error_code="AccessDeniedException",
                                               service_message="PRIVATE_ERROR", expected_params={"FunctionName": "orders"})
        backend = AWSFollowups(self.session, self.manifest, self.bundle, "orders")
        evidence = backend.run("configuration")
        self.assertEqual([e.kind for e in evidence], ["lambda_configuration", "followup_failure"])
        self.assertEqual(evidence[0].status, "observed")
        self.assertEqual(evidence[1].status, "unavailable")
        self.assertNotIn("PRIVATE_ERROR", str(evidence))

    def test_transient_sdk_code_is_preserved_for_retry_classification(self):
        from aws_triage.check_outcomes import check_outcome, retryable
        self.identity()
        self.configuration()
        self.stubs["lambda"].add_client_error("get_function_concurrency", service_error_code="ThrottlingException",
                                               service_message="PRIVATE_ERROR", expected_params={"FunctionName": "orders"})
        backend = AWSFollowups(self.session, self.manifest, self.bundle, "orders")
        evidence = backend.run("configuration")
        self.assertEqual(check_outcome(evidence), "partial")
        self.assertTrue(retryable(evidence))
        self.assertEqual(evidence[-1].data["error_code"], "ThrottlingException")
        self.assertNotIn("PRIVATE_ERROR", str(evidence))

    def test_change_lookup_discards_sensitive_event_body_and_read_events(self):
        self.identity()
        self.stubs["cloudtrail"].add_response("lookup_events", {"Events": [
            {"EventId": "write-123", "EventName": "UpdateFunctionCode", "EventSource": "lambda.amazonaws.com",
             "EventTime": utc_time(START), "ReadOnly": "false", "Username": "PRIVATE_USER",
             "CloudTrailEvent": json.dumps({"requestParameters": {"secret": "PRIVATE_CONTENT"}})},
            {"EventId": "read-456", "EventName": "GetFunction", "EventSource": "lambda.amazonaws.com",
             "EventTime": utc_time(START), "ReadOnly": "true"}], "NextToken": "more"},
            {"LookupAttributes": [{"AttributeKey": "ResourceName", "AttributeValue": "orders"}],
             "StartTime": utc_time(START) - timedelta(minutes=30), "EndTime": utc_time(END), "MaxResults": 10})
        backend = AWSFollowups(self.session, self.manifest, self.bundle, "orders")
        evidence = backend.run("changes")[-1]
        self.assertEqual(evidence.status, "partial")
        self.assertEqual(len(evidence.data["events"]), 1)
        self.assertNotIn("PRIVATE_", json.dumps(evidence.data))

    def test_converse_tool_contract_and_usage(self):
        from botocore.stub import Stubber, ANY
        import boto3
        client = boto3.client("bedrock-runtime", region_name="us-east-1", aws_access_key_id="synthetic-key", aws_secret_access_key="synthetic-secret")
        with Stubber(client) as stub:
            decision = {"action": "check", "check": "permissions"}
            stub.add_response("converse", {"output": {"message": {"role": "assistant", "content": [
                {"toolUse": {"toolUseId": "tooluse_0123456789012345678901", "name": "investigation_step", "input": decision}}]}},
                "stopReason": "tool_use", "usage": {"inputTokens": 100, "outputTokens": 20, "totalTokens": 120}, "metrics": {"latencyMs": 1}},
                {"modelId": "operator-selected-model", "system": ANY, "messages": ANY, "inferenceConfig": {"maxTokens": 1024},
                 "toolConfig": {"tools": [{"toolSpec": {"name": "investigation_step", "description": "Propose the next check or a bounded final assessment.",
                    "inputSchema": {"json": DECISION_SCHEMA}}}], "toolChoice": {"tool": {"name": "investigation_step"}}}})
            planner = BedrockPlanner(client, "operator-selected-model", True)
            self.assertEqual(planner.next({"application": "orders"}), decision)
            self.assertEqual(planner.usage, {"input_tokens": 100, "output_tokens": 20})
