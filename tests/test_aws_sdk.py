"""Validate adapter requests against real botocore models without AWS access."""

import importlib.util
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from aws_triage.collect import AWSCollector
from aws_triage.sandbox import manifest_from_stack, probe
from aws_triage.api_metrics import collect_api_metrics, SPECS

HAS_SDK = importlib.util.find_spec("boto3") is not None


@unittest.skipUnless(HAS_SDK, "Install the optional aws extra for botocore contract checks")
class SDKContractTests(unittest.TestCase):
    def setUp(self):
        import boto3
        self.session = boto3.Session(aws_access_key_id="synthetic-key", aws_secret_access_key="synthetic-secret", region_name="us-east-1")
        self.collector = AWSCollector(self.session, {"application": "orders", "account_id": "111122223333", "region": "us-east-1",
                                                    "lambda_functions": ["orders"], "expected_tables": {"orders": "orders-table"}},
                                      "2026-10-30T12:00:00Z", "2026-10-30T12:15:00Z")

    def test_lambda_configuration_excludes_secret_environment(self):
        from botocore.stub import Stubber
        client = self.session.client("lambda")
        self.collector.clients["lambda"] = client
        with Stubber(client) as stub:
            stub.add_response("get_function_configuration", {"FunctionName": "orders", "Environment": {"Variables": {
                "ORDERS_TABLE": "orders-table", "API_SECRET": "never-store-this", "FAULT_MODE": "code_exception"}}}, {"FunctionName": "orders"})
            self.collector.function_configuration("orders")
        data = self.collector.evidence[0].data
        self.assertEqual(data["orders_table"], "orders-table")
        self.assertNotIn("never-store-this", str(data))
        self.assertNotIn("code_exception", str(data))

    def test_lambda_environment_error_marks_partial(self):
        from botocore.stub import Stubber
        client = self.session.client("lambda")
        self.collector.clients["lambda"] = client
        with Stubber(client) as stub:
            stub.add_response("get_function_configuration", {"Environment": {"Error": {"ErrorCode": "AccessDeniedException"}}}, {"FunctionName": "orders"})
            self.collector.function_configuration("orders")
        self.assertEqual(self.collector.evidence[0].status, "partial")

    def test_zero_concurrency_request_shape(self):
        from botocore.stub import Stubber
        client = self.session.client("lambda")
        self.collector.clients["lambda"] = client
        with Stubber(client) as stub:
            stub.add_response("get_function_concurrency", {"ReservedConcurrentExecutions": 0}, {"FunctionName": "orders"})
            self.collector.function_concurrency("orders")
        self.assertEqual(self.collector.evidence[0].data["reserved_concurrency"], 0)

    def test_api_metric_requests_against_sdk_schema(self):
        from botocore.stub import Stubber
        client = self.session.client("cloudwatch")
        self.collector.clients["cloudwatch"] = client
        api = {"api_id": "abc123def4", "api_name": "orders-api", "stage": "sandbox"}
        duration = self.collector.end - self.collector.start
        with Stubber(client) as stub:
            for start, end in ((self.collector.start, self.collector.end), (self.collector.start - duration, self.collector.start)):
                for name, metric, stats in SPECS:
                    point = {"Timestamp": start, **{stat: 100.0 for stat in stats}}
                    stub.add_response("get_metric_statistics", {"Datapoints": [point]}, {
                        "Namespace": "AWS/ApiGateway", "MetricName": metric,
                        "Dimensions": [{"Name": "ApiName", "Value": "orders-api"}, {"Name": "Stage", "Value": "sandbox"}],
                        "StartTime": start, "EndTime": end, "Period": 60, "Statistics": stats})
            collect_api_metrics(self.collector, api)
            stub.assert_no_pending_responses()
        self.assertEqual(self.collector.evidence[0].data["requests"], 100)
        self.assertEqual(self.collector.evidence[1].data["window"], "baseline")

    def test_client_vpn_request_shapes(self):
        from botocore.stub import Stubber
        client = self.session.client("ec2")
        self.collector.clients["ec2"] = client
        for operation, key in [("describe_client_vpn_connections", "Connections"),
                               ("describe_client_vpn_routes", "Routes"),
                               ("describe_client_vpn_authorization_rules", "AuthorizationRules")]:
            with self.subTest(operation=operation), Stubber(client) as stub:
                stub.add_response(operation, {key: []}, {"ClientVpnEndpointId": "cvpn-endpoint-12345678", "MaxResults": 100})
                self.collector.vpn("cvpn-endpoint-12345678", operation, key, key, [])

    def test_probe_account_mismatch_sends_no_request(self):
        # Import the synthetic stack fixture; it contains no live account data.
        from test_sandbox import stack_description
        manifest = manifest_from_stack(stack_description())
        session = Mock()
        session.client.return_value.get_caller_identity.return_value = {"Account": "999999999999"}
        send = Mock()
        with self.assertRaises(ValueError):
            probe(session, manifest, send)
        send.assert_not_called()

    def test_probe_rejects_changed_stack_before_signing(self):
        from test_sandbox import stack_description
        manifest = manifest_from_stack(stack_description())
        description = stack_description()
        description["Stacks"][0]["Tags"] = []
        session = Mock()
        session.client.return_value.get_caller_identity.return_value = {"Account": "111122223333"}
        session.client.return_value.describe_stacks.return_value = description
        send = Mock()
        with self.assertRaises(ValueError):
            probe(session, manifest, send)
        send.assert_not_called()

    def test_probe_signs_only_verified_target_and_one_synthetic_order(self):
        from botocore.credentials import Credentials
        from test_sandbox import stack_description
        manifest = manifest_from_stack(stack_description())
        session = Mock()
        session.client.return_value.get_caller_identity.return_value = {"Account": "111122223333"}
        session.client.return_value.describe_stacks.return_value = stack_description()
        session.get_credentials.return_value = Credentials("synthetic-key", "synthetic-secret")
        response = Mock()
        response.status, response.headers = 201, {"x-amzn-RequestId": "request-123"}
        send = Mock()
        send.return_value.__enter__ = Mock(return_value=response)
        send.return_value.__exit__ = Mock(return_value=False)
        result = probe(session, manifest, send)
        self.assertEqual(result["http_status"], 201)
        self.assertEqual(send.call_count, 1)
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://abc123def4.execute-api.us-east-1.amazonaws.com/sandbox/orders")
        self.assertEqual(request.method, "POST")
        self.assertNotIn("synthetic-secret", str(result))
