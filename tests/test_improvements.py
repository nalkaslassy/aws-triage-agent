import copy
import json
import unittest
from datetime import datetime, timezone

from aws_triage.api_metrics import collect_api_metrics
from aws_triage.collect import AWSCollector, validate_manifest
from aws_triage.investigate import investigate, markdown
from aws_triage.model import Bundle, Evidence
from aws_triage.signals import classify
from test_triage import FakeCollector, MANIFEST, START, END, evidence


def api_item(identity="E001", window="incident", **data):
    values = {"window": window, "start": START if window == "incident" else "2026-10-30T11:45:00Z",
              "end": END if window == "incident" else START, "requests": 100,
              "server_errors": 10, "client_errors": 0, "latency_ms": 200,
              "integration_latency_ms": 150, **data}
    return Evidence(identity, "api_metrics", "orders-api/sandbox (abc123def4)", "test metrics", "observed", values, END)


class ValidationTests(unittest.TestCase):
    def test_boolean_concurrency_rejected(self):
        with self.assertRaises(ValueError):
            evidence("lambda_concurrency", {"reserved_concurrency": False})

    def test_invalid_numeric_fields_rejected(self):
        for value in (True, "4", -1, float("nan"), float("inf"), 10 ** 1000):
            with self.subTest(type=type(value).__name__), self.assertRaises(ValueError):
                evidence("lambda_metrics", {"Errors": value})

    def test_fractional_log_counts_rejected(self):
        with self.assertRaises(ValueError):
            evidence("log_signals", {"access_denied": 1.5})

    def test_null_log_count_does_not_create_a_failure(self):
        result = investigate(Bundle("orders", START, END, [evidence("log_signals", {"access_denied": None})]))
        self.assertEqual(result.findings, [])

    def test_invalid_data_shape_rejected(self):
        with self.assertRaises(ValueError):
            evidence("lambda_metrics", [])

    def test_boolean_schema_version_rejected(self):
        with self.assertRaises(ValueError):
            Bundle("orders", START, END, [], schema_version=True)

    def test_untrusted_source_link_rejected(self):
        for url in ("javascript:alert(1)", "https://attacker.example", "https://console.aws.amazon.com.attacker.example",
                    "https://user:secret@console.aws.amazon.com", "https://console.aws.amazon.com/\nnew"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                Evidence("E001", "unknown", "orders", "test", "observed", {}, END, source_url=url)

    def test_rest_api_manifest_validates_scope(self):
        api = {"api_id": "abc123def4", "api_name": "orders-api", "stage": "sandbox"}
        for values in ([{**api, "api_name": "*"}], [api] * 3, [api, api], [{**api, "stage": "*"}]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_manifest({**MANIFEST, "rest_apis": values})

    def test_api_collection_requires_minute_boundaries(self):
        manifest = {**MANIFEST, "rest_apis": [{"api_id": "abc123def4", "api_name": "orders-api", "stage": "sandbox"}]}
        with self.assertRaises(ValueError):
            AWSCollector(None, manifest, "2026-10-30T12:00:01Z", END)


class LogReliabilityTests(unittest.TestCase):
    def test_later_log_failure_preserves_earlier_evidence(self):
        collector = FakeCollector([{"events": [{"eventId": "1", "message": "ERROR AccessDeniedException"}], "nextToken": "page2"},
                                   RuntimeError("do-not-store-secret")])
        collector.logs("/aws/lambda/orders")
        item = collector.evidence[0]
        self.assertEqual(item.status, "partial")
        self.assertEqual(item.data["access_denied"], 1)
        self.assertNotIn("do-not-store-secret", json.dumps(item.data))
        self.assertEqual(len(investigate(Bundle("orders", START, END, [item])).findings), 1)

    def test_first_page_failure_is_unavailable(self):
        collector = FakeCollector([RuntimeError("failure")])
        collector.logs("/aws/lambda/orders")
        self.assertEqual(collector.evidence[0].status, "unavailable")

    def test_information_and_bare_mentions_are_not_failures(self):
        for message in ("INFO example: AccessDeniedException", "AccessDeniedException documentation", "WARNING retry example TimeoutError",
                        json.dumps({"level": "INFO", "message": "AccessDeniedException"})):
            with self.subTest(message=message):
                signals, _, mention = classify(message)
                self.assertEqual(signals, set())
                self.assertTrue(mention)

    def test_structured_failure_does_not_need_keyword_matching(self):
        signals, details, mention = classify(json.dumps({"event": "dependency_failure", "error_code": "AccessDeniedException",
                                                        "request_id": "request-123", "target": "orders-table", "operation": "PutItem"}))
        self.assertEqual(signals, {"access_denied"})
        self.assertEqual(details["target"], "orders-table")
        self.assertFalse(mention)

    def test_structured_and_regex_signal_not_counted_twice(self):
        message = '[ERROR] ' + json.dumps({"event": "application_exception", "message": "Unhandled exception"})
        collector = FakeCollector([{"events": [{"eventId": "1", "message": message}]}])
        collector.logs("/aws/lambda/orders")
        self.assertEqual(collector.evidence[0].data["exception"], 1)

    def test_malformed_structured_error_does_not_drop_other_evidence(self):
        collector = FakeCollector([{"events": [
            {"eventId": "1", "message": "ERROR AccessDeniedException"},
            {"eventId": "2", "message": json.dumps({"event": "dependency_failure", "error_code": ["bad-shape"]})}]}])
        collector.logs("/aws/lambda/orders")
        self.assertEqual(collector.evidence[0].data["access_denied"], 1)
        self.assertEqual(collector.evidence[0].status, "observed")

    def test_error_query_is_bounded_and_filtered(self):
        collector = FakeCollector([{"events": []}])
        collector.logs("/aws/lambda/orders")
        args = collector.operations[0][2]
        self.assertIn("AccessDeniedException", args["filterPattern"])
        self.assertEqual(args["limit"], 100)

    def test_empty_page_with_token_does_not_end_search(self):
        collector = FakeCollector([{"events": [], "nextToken": "more"},
                                   {"events": [{"eventId": "1", "message": "ERROR TimeoutError"}]}])
        collector.logs("/aws/lambda/orders")
        self.assertEqual(collector.evidence[0].data["timeout"], 1)
        self.assertEqual(collector.evidence[0].status, "observed")

    def test_partial_lambda_metrics_preserve_successes(self):
        collector = FakeCollector([{"Datapoints": [{"Sum": 5}]}, RuntimeError("private error"), {"Datapoints": [{"Sum": 2}]}])
        collector.metrics("orders")
        item = collector.evidence[0]
        self.assertEqual(item.status, "partial")
        self.assertEqual(item.data["Errors"], 5)
        self.assertEqual(item.data["Throttles"], 2)
        self.assertIsNone(item.data["Invocations"])


class APIMetricTests(unittest.TestCase):
    def test_api_statistics_baseline_and_weighted_latency(self):
        one_window = [{"Datapoints": [{"SampleCount": 100}]}, {"Datapoints": [{"Sum": 10}]},
                      {"Datapoints": [{"Sum": 0}]},
                      {"Datapoints": [{"Sum": 100, "SampleCount": 1}, {"Sum": 9000, "SampleCount": 99}]},
                      {"Datapoints": [{"Sum": 8000, "SampleCount": 100}]}]
        collector = FakeCollector(one_window * 2)
        collect_api_metrics(collector, {"api_id": "abc123def4", "api_name": "orders-api", "stage": "sandbox"})
        self.assertEqual(collector.evidence[0].data["requests"], 100)
        self.assertEqual(collector.evidence[0].data["latency_ms"], 91)
        self.assertEqual(collector.operations[0][2]["Statistics"], ["SampleCount"])
        self.assertEqual(collector.operations[5][2]["EndTime"], collector.start)
        self.assertEqual(collector.evidence[1].data["window"], "baseline")

    def test_api_partial_failure_retains_counts(self):
        collector = FakeCollector([{"Datapoints": [{"SampleCount": 100}]}, {"Datapoints": [{"Sum": 10}]},
                                   RuntimeError("private details"), {"Datapoints": []}, {"Datapoints": []}] * 2)
        collect_api_metrics(collector, {"api_id": "abc123def4", "api_name": "orders-api", "stage": "sandbox"})
        self.assertEqual(collector.evidence[0].status, "partial")
        self.assertEqual(collector.evidence[0].data["server_errors"], 10)
        self.assertNotIn("private details", json.dumps(collector.evidence[0].data))

    def test_api_failure_visible_when_lambda_errors_are_zero(self):
        item = api_item()
        result = investigate(Bundle("orders", START, END, [item, evidence("lambda_metrics", {"Errors": 0, "Invocations": 100, "Throttles": 0}, identity="E002")]))
        self.assertEqual(result.findings[0].title, "API server-side errors observed")
        self.assertIn("10.00%", result.findings[0].explanation)

    def test_error_rate_baseline_comparison_cites_both_sources(self):
        result = investigate(Bundle("orders", START, END, [api_item(), api_item("E002", "baseline", server_errors=1)]))
        self.assertEqual(result.findings[0].evidence_ids, ["E001", "E002"])
        self.assertIn("+9.00 percentage points", result.findings[0].explanation)

    def test_missing_zero_inconsistent_or_partial_counts_do_not_create_rate(self):
        for data in ({"requests": 0}, {"requests": None}, {"server_errors": 200}, {"server_errors": None}):
            with self.subTest(data=data):
                result = investigate(Bundle("orders", START, END, [api_item(**data)]))
                self.assertTrue(any("could not be calculated" in gap for gap in result.gaps))
        item = api_item()
        partial = Evidence(item.id, item.kind, item.resource, item.source, "partial", item.data, END)
        result = investigate(Bundle("orders", START, END, [partial]))
        self.assertNotIn("Observed 5xx rate", result.findings[0].explanation)

    def test_wrong_window_baseline_is_not_compared(self):
        result = investigate(Bundle("orders", START, END, [api_item(), api_item("E002", "baseline", end="2026-10-30T11:59:00Z")]))
        self.assertEqual(result.findings[0].evidence_ids, ["E001"])

    def test_latency_increase_requires_volume_and_cites_baseline(self):
        result = investigate(Bundle("orders", START, END, [api_item(server_errors=0, latency_ms=300),
                                                                           api_item("E002", "baseline", server_errors=0, latency_ms=100)]))
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0].classification, "hypothesis")
        self.assertIn("not a statistical anomaly test", result.findings[0].explanation)
        low = investigate(Bundle("orders", START, END, [api_item(requests=1, server_errors=0, latency_ms=300),
                                                                        api_item("E002", "baseline", server_errors=0, latency_ms=100)]))
        self.assertEqual(low.findings, [])


class ReportTests(unittest.TestCase):
    def test_report_contains_resource_source_time_and_safe_console_link(self):
        item = Evidence("E001", "lambda_concurrency", "orders-function", "lambda:GetFunctionConcurrency", "observed",
                        {"reserved_concurrency": 0}, END, "https://console.aws.amazon.com/lambda/home?region=us-east-1#/functions/orders-function")
        value = markdown(investigate(Bundle("orders", START, END, [item])))
        for text in ("orders-function", "lambda:GetFunctionConcurrency", "Evidence index", END, "[Open AWS console]"):
            self.assertIn(text, value)

    def test_untrusted_markdown_and_arbitrary_log_fields_not_rendered(self):
        item = Evidence("E001", "log_signals", "orders [click](https://attacker.example)", "source", "observed",
                        {"access_denied": 1, "message": "DO_NOT_ECHO_RAW_MESSAGE"}, END)
        result = investigate(Bundle("orders", START, END, [item]))
        self.assertNotIn("DO_NOT_ECHO_RAW_MESSAGE", markdown(result))
        self.assertNotIn("DO_NOT_ECHO_RAW_MESSAGE", json.dumps(result.to_dict()))
        self.assertNotIn("[click](https://attacker.example)", markdown(result))

    def test_log_reference_includes_request_and_event_details(self):
        item = evidence("log_signals", {"access_denied": 1, "samples": [{"signal": "access_denied", "request_id": "request-123",
                         "event_id": "event-456", "stream": "stream-789", "timestamp": 1793361600000}]})
        value = markdown(investigate(Bundle("orders", START, END, [item])))
        for text in ("request-123", "event-456", "stream-789", "2026-10-30T12:00:00+00:00"):
            self.assertIn(text, value)

    def test_matching_target_correlation_requires_function_and_time(self):
        config = evidence("lambda_configuration", {"orders_table": "missing-table", "expected_table": "orders-table"})
        sample = {"signal": "resource_missing", "target": "missing-table", "operation": "PutItem",
                  "request_id": "request-123", "timestamp": 1793361600000}
        log = evidence("log_signals", {"function_name": config.resource, "resource_missing": 1, "samples": [sample]}, identity="E002")
        result = investigate(Bundle("orders", START, END, [config, log]))
        joined = [f for f in result.findings if f.title.startswith("Table mismatch may")]
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0].evidence_ids, ["E001", "E002"])
        wrong = evidence("log_signals", {"function_name": "unrelated", "resource_missing": 1, "samples": [sample]}, identity="E002")
        self.assertFalse(any(f.title.startswith("Table mismatch may") for f in investigate(Bundle("orders", START, END, [config, wrong])).findings))
        old = evidence("log_signals", {"function_name": config.resource, "resource_missing": 1,
                                      "samples": [{**sample, "timestamp": 1}]}, identity="E002")
        self.assertFalse(any(f.title.startswith("Table mismatch may") for f in investigate(Bundle("orders", START, END, [config, old])).findings))
