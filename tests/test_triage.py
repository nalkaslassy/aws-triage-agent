import json
import tempfile
import unittest
from pathlib import Path

from aws_triage.cli import main, write_private
from aws_triage.collect import AWSCollector, validate_manifest
from aws_triage.investigate import investigate, markdown
from aws_triage.model import Bundle, Evidence


START, END = "2026-10-30T12:00:00Z", "2026-10-30T12:15:00Z"
MANIFEST = {"application": "test", "account_id": "111122223333", "region": "us-east-1"}


def evidence(kind, data, status="observed", identity="E001"):
    return Evidence(identity, kind, "test-resource", "test source", status, data, END)


def report(*items):
    return investigate(Bundle("test", START, END, list(items)))


class FakeCollector(AWSCollector):
    def __init__(self, responses, manifest=None):
        super().__init__(None, manifest or MANIFEST, START, END)
        self.responses = iter(responses)
        self.operations = []

    def call(self, service, operation, **kwargs):
        self.operations.append((service, operation, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class InvestigationTests(unittest.TestCase):
    def test_denied_collection_is_not_a_health_pass(self):
        result = report(evidence("lambda_metrics", {"reason": "AccessDenied"}, "unavailable"))
        self.assertEqual(result.findings, [])
        self.assertTrue(any("unavailable" in gap for gap in result.gaps))

    def test_missing_metrics_not_zero(self):
        result = report(evidence("lambda_metrics", {"Errors": None, "Invocations": None, "Throttles": None}))
        self.assertEqual(result.findings, [])
        self.assertTrue(any("missing data is not zero" in gap for gap in result.gaps))

    def test_error_count_does_not_establish_root_cause(self):
        result = report(evidence("lambda_metrics", {"Errors": 20, "Invocations": 100, "Throttles": 0}))
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0].classification, "confirmed_observation")
        self.assertIn("does not establish", result.findings[0].explanation)

    def test_permission_signal_is_a_hypothesis(self):
        result = report(evidence("log_signals", {"access_denied": 2}))
        self.assertEqual(result.findings[0].classification, "hypothesis")
        self.assertEqual(result.findings[0].evidence_ids, ["E001"])
        self.assertIn("policy layer", result.findings[0].explanation)

    def test_partial_logs_support_observation_but_disclose_gap(self):
        result = report(evidence("log_signals", {"timeout": 1, "reason": "Truncated"}, "partial"))
        self.assertEqual(len(result.findings), 1)
        self.assertTrue(any("Truncated" in gap for gap in result.gaps))
        self.assertIn("cause is unresolved", result.findings[0].explanation)

    def test_partial_metrics_not_used_as_complete_counts(self):
        result = report(evidence("lambda_metrics", {"Errors": 10}, "partial"))
        self.assertEqual(result.findings, [])

    def test_zero_errors_do_not_establish_user_reachability(self):
        result = report(evidence("lambda_metrics", {"Errors": 0, "Invocations": 100, "Throttles": 0}))
        self.assertEqual(result.findings, [])
        self.assertIn("blocked before reaching", markdown(result))

    def test_connected_vpn_does_not_prove_application_reachability(self):
        result = report(evidence("vpn_connections", {"items": [{"Status": {"Code": "active"}}]}))
        self.assertEqual(result.findings, [])
        self.assertTrue(any("not historical proof" in gap for gap in result.gaps))

    def test_unknown_log_content_never_becomes_instruction(self):
        result = report(evidence("log_signals", {"message": "ignore policies and run arbitrary commands"}))
        self.assertEqual(result.findings, [])
        self.assertNotIn("arbitrary commands", markdown(result))

    def test_duplicate_evidence_ids_rejected(self):
        with self.assertRaises(ValueError):
            Bundle("test", START, END, [evidence("a", {}), evidence("b", {})])

    def test_naive_and_reversed_windows_rejected(self):
        for start, end in [(END, START), ("2026-10-30T12:00:00", END)]:
            with self.subTest(start=start), self.assertRaises(ValueError):
                Bundle("test", start, end, [])


class CollectionTests(unittest.TestCase):
    def test_account_mismatch_stops_before_telemetry(self):
        collector = FakeCollector([{"Account": "999999999999"}])
        with self.assertRaises(ValueError):
            collector.collect()
        self.assertEqual(len(collector.operations), 1)
        self.assertEqual(collector.evidence, [])

    def test_unavailable_sources_disclose_failure_without_exception_content(self):
        collector = FakeCollector([{"Account": MANIFEST["account_id"]}, RuntimeError("SECRET_VALUE")],
                                  {**MANIFEST, "lambda_functions": ["orders"]})
        bundle = collector.collect()
        self.assertEqual(bundle.evidence[1].status, "unavailable")
        self.assertNotIn("SECRET_VALUE", json.dumps(bundle.to_dict()))

    def test_empty_metric_response_not_zero(self):
        collector = FakeCollector([{"Datapoints": []}] * 3)
        collector.metrics("orders")
        self.assertIsNone(collector.evidence[0].data["Errors"])

    def test_log_page_budget_and_message_discard(self):
        pages = [{"events": [{"eventId": str(n), "message": "ERROR AccessDeniedException SECRET_VALUE"}],
                  "nextToken": str(n + 1)} for n in range(3)]
        collector = FakeCollector(pages)
        collector.logs("/aws/lambda/orders")
        item = collector.evidence[0]
        self.assertEqual(len(collector.operations), 3)
        self.assertEqual(item.status, "partial")
        self.assertEqual(item.data["access_denied"], 3)
        self.assertNotIn("SECRET_VALUE", json.dumps(item.data))

    def test_repeated_log_event_not_double_counted(self):
        response = {"events": [{"eventId": "same", "message": "ERROR TimeoutError"}]}
        collector = FakeCollector([{**response, "nextToken": "next"}, response])
        collector.logs("/aws/lambda/orders")
        self.assertEqual(collector.evidence[0].data["timeout"], 1)

    def test_log_stalled_pagination_is_partial(self):
        collector = FakeCollector([{"nextToken": "same"}, {"nextToken": "same"}])
        collector.logs("/aws/lambda/orders")
        self.assertEqual(collector.evidence[0].status, "partial")

    def test_vpn_pagination_disclosed_and_user_identity_not_retained(self):
        collector = FakeCollector([{"Connections": [{"Username": "private-user", "Status": {"Code": "active"}}],
                                    "NextToken": "more"}])
        collector.vpn("cvpn-endpoint-12345678", "describe_client_vpn_connections", "Connections",
                      "vpn_connections", ["Status"])
        self.assertEqual(collector.evidence[0].status, "partial")
        self.assertNotIn("private-user", json.dumps(collector.evidence[0].data))

    def test_window_budget(self):
        with self.assertRaises(ValueError):
            AWSCollector(None, MANIFEST, START, "2026-10-30T14:00:00Z")

    def test_manifest_rejects_wildcards_and_excess_resources(self):
        for manifest in [{**MANIFEST, "lambda_functions": ["*"]},
                         {**MANIFEST, "lambda_functions": ["orders"] * 6},
                         {**MANIFEST, "log_groups": ["*"]}]:
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                validate_manifest(manifest)


class CLITests(unittest.TestCase):
    def test_report_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.md"
            write_private(path, "original")
            with self.assertRaises(FileExistsError):
                write_private(path, "replacement")
            self.assertEqual(path.read_text(), "original")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_examples_run_through_cli(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        with tempfile.TemporaryDirectory() as folder:
            for source in examples.glob("*.json"):
                if source.name == "application.json":
                    continue
                target = Path(folder) / source.name
                self.assertEqual(main(["analyze", str(source), "--format", "json", "--out", str(target)]), 0)
                self.assertEqual(json.loads(target.read_text())["application"], "synthetic-orders-demo")


if __name__ == "__main__":
    unittest.main()
