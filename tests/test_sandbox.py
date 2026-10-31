import importlib.util
import io
import json
import logging
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aws_triage.collect import validate_manifest
from aws_triage.investigate import investigate
from aws_triage.sandbox import manifest_from_stack, NoRedirect

SPEC = importlib.util.spec_from_file_location("sandbox_evaluation", Path(__file__).resolve().parents[1] / "sandbox" / "local_evaluation.py")
LAB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAB)


def stack_description():
    return {"Stacks": [{"StackId": "arn:aws:cloudformation:us-east-1:111122223333:stack/triage-sandbox-test/1234-5678",
                        "StackStatus": "CREATE_COMPLETE",
                        "Tags": [{"Key": "Project", "Value": "aws-triage-agent"},
                                 {"Key": "Environment", "Value": "sandbox"}],
                        "Outputs": [{"OutputKey": key, "OutputValue": value} for key, value in {
                            "FunctionName": "triage-sandbox-test-orders", "LogGroup": "/aws/lambda/triage-sandbox-test-orders",
                            "ExpectedTable": "orders-table", "ApiId": "abc123def4", "ApiName": "triage-sandbox-test-api"}.items()]}]}


class SandboxTests(unittest.TestCase):
    def test_five_local_scenarios(self):
        result = LAB.evaluate()
        self.assertTrue(result["passed"], result)
        self.assertEqual(len(result["scenarios"]), 5)

    def test_no_ground_truth_in_investigator_input(self):
        for mode in ("permission_denied", "wrong_table", "code_exception", "throttle"):
            with self.subTest(mode=mode):
                _, bundle, _ = LAB.run_case(mode)
                value = json.dumps(bundle.to_dict())
                self.assertNotIn("FAULT_MODE", value)
                self.assertNotIn('"scenario"', value)
                self.assertNotIn('"ground_truth"', value)

    def test_no_secret_error_message_in_logs_or_bundle(self):
        _, bundle, _ = LAB.run_case("permission_denied")
        text = json.dumps(bundle.to_dict())
        self.assertNotIn("sensitive SDK text", text)
        sample = bundle.evidence[0].data["samples"][0]
        self.assertEqual(sample["request_id"], "local-request-123")
        self.assertEqual(sample["operation"], "PutItem")

    def test_handled_application_failure_works_without_lambda_error_metric(self):
        response, bundle, report = LAB.run_case("code_exception")
        self.assertEqual(response["statusCode"], 500)
        self.assertFalse(any(e.kind == "lambda_metrics" for e in bundle.evidence))
        self.assertEqual(report.findings[0].classification, "hypothesis")

    def test_input_cannot_choose_fault_mode(self):
        app = LAB.load_app()
        app._client = LAB.LocalDynamo()
        with patch.dict(os.environ, {"FAULT_MODE": "normal", "ORDERS_TABLE": "orders-table"}):
            result = app.handler({"body": json.dumps({"sku": "synthetic", "quantity": 1,
                                                       "FAULT_MODE": "code_exception"})},
                                 SimpleNamespace(aws_request_id="test-123"))
        self.assertEqual(result["statusCode"], 201)

    def test_malformed_requests_never_write(self):
        app = LAB.load_app()
        app._client = LAB.LocalDynamo()
        for value in ("{", "[]", '{"sku":"x","quantity":true}', '{"sku":"x","quantity":99}'):
            self.assertEqual(app.handler({"body": value}, SimpleNamespace(aws_request_id="test"))["statusCode"], 400)
        self.assertEqual(app._client.writes, [])

    def test_manifest_requires_sandbox_tags(self):
        description = stack_description()
        description["Stacks"][0]["Tags"] = []
        with self.assertRaises(ValueError):
            manifest_from_stack(description)

    def test_manifest_requires_completed_sandbox_stack(self):
        for key, value in [("StackStatus", "UPDATE_IN_PROGRESS"), ("StackId", "arn:aws:cloudformation:us-east-1:111122223333:stack/production/123")]:
            description = stack_description()
            description["Stacks"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                manifest_from_stack(description)

    def test_manifest_has_no_scenario_parameters(self):
        manifest = manifest_from_stack(stack_description())
        self.assertEqual(manifest["expected_tables"], {"triage-sandbox-test-orders": "orders-table"})
        self.assertNotIn("FaultMode", json.dumps(manifest))

    def test_manifest_rejects_unscoped_expected_function(self):
        manifest = manifest_from_stack(stack_description())
        manifest["expected_tables"] = {"other-function": "orders-table"}
        with self.assertRaises(ValueError):
            validate_manifest(manifest)

    def test_probe_does_not_follow_redirects(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://elsewhere.example"))
