"""Local contract exercise: real handler, stubbed dependency/AWS observations.

This is a smoke evaluation, not a live outage benchmark or accuracy estimate.
Ground truth stays in this harness; only the generated bundle reaches triage.
"""

import importlib.util
import io
import json
import logging
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aws_triage.collect import AWSCollector
from aws_triage.investigate import investigate
from aws_triage.model import Bundle

START, END = "2026-10-30T12:00:00Z", "2026-10-30T12:15:00Z"


def load_app():
    spec = importlib.util.spec_from_file_location("orders_sandbox_app", Path(__file__).parent / "orders" / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DependencyError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code, "Message": "sensitive SDK text must not be logged"}}


class LocalDynamo:
    def __init__(self, code=None):
        self.code, self.writes = code, []

    def put_item(self, **kwargs):
        if self.code:
            raise DependencyError(self.code)
        self.writes.append(kwargs)
        return {}


class LogFixtureCollector(AWSCollector):
    def __init__(self, messages):
        super().__init__(None, {"application": "synthetic-orders", "account_id": "111122223333", "region": "us-east-1"}, START, END)
        self.messages = messages

    def call(self, service, operation, **kwargs):
        if (service, operation) != ("logs", "filter_log_events"):
            raise AssertionError("Local evaluation must not contact AWS")
        return {"events": [{"eventId": str(i), "message": m, "timestamp": 1793361600000,
                            "logStreamName": "synthetic-stream"} for i, m in enumerate(self.messages)]}


def run_case(mode):
    app = load_app()
    app._client = LocalDynamo({"permission_denied": "AccessDeniedException",
                               "wrong_table": "ResourceNotFoundException"}.get(mode))
    stream = io.StringIO()
    capture = logging.StreamHandler(stream)
    # Match Lambda's normal text prefix to exercise structured log extraction.
    capture.setFormatter(logging.Formatter("[%(levelname)s]\t2026-10-30\trequest\t%(message)s"))
    app.LOG.addHandler(capture)
    app.LOG.propagate = False
    target = "orders-table-missing" if mode == "wrong_table" else "orders-table"
    try:
        with patch.dict(os.environ, {"ORDERS_TABLE": target,
                                     "FAULT_MODE": "code_exception" if mode == "code_exception" else "normal"}):
            response = None if mode == "throttle" else app.handler(
                {"body": json.dumps({"sku": "synthetic-test", "quantity": 1})},
                SimpleNamespace(aws_request_id="local-request-123"))
    finally:
        app.LOG.removeHandler(capture)
    collector = LogFixtureCollector(stream.getvalue().splitlines())
    collector.logs("/aws/lambda/synthetic-orders")
    collector.add("lambda_configuration", "synthetic-orders", "stubbed Lambda configuration",
                  {"orders_table": target, "expected_table": "orders-table"})
    collector.add("lambda_concurrency", "synthetic-orders", "stubbed Lambda concurrency",
                  {"reserved_concurrency": 0 if mode == "throttle" else None})
    if mode == "throttle":
        collector.add("lambda_metrics", "synthetic-orders", "stubbed CloudWatch metrics",
                      {"Errors": 0, "Invocations": 0, "Throttles": 1})
    bundle = Bundle("synthetic-orders", START, END,
                    [replace(e, source="local-only / " + e.source, source_url=None) for e in collector.evidence])
    return response, bundle, investigate(bundle)


def evaluate():
    cases = [
        ("normal", 201, []),
        ("permission_denied", 502, ["Authorization failure appears in application logs"]),
        ("code_exception", 500, ["Application exception appears in logs"]),
        ("wrong_table", 502, ["A dependency reports a missing resource", "Configured table differs from the application manifest"]),
        ("throttle", None, ["Lambda throttling observed", "Function reserved concurrency is currently zero"]),
    ]
    results = []
    for mode, status, expected in cases:
        response, bundle, report = run_case(mode)
        titles = [f.title for f in report.findings]
        actual_status = response["statusCode"] if response else None
        citations_valid = all(set(f.evidence_ids) <= {e.id for e in bundle.evidence} for f in report.findings)
        passed = actual_status == status and set(titles) == set(expected) and citations_valid
        results.append({"scenario": mode, "passed": passed, "handler_status": actual_status,
                        "finding_titles": titles, "evidence_references_valid": citations_valid,
                        "evidence_excludes_fault_selector": "FAULT_MODE" not in json.dumps(bundle.to_dict())})
    return {"evaluation_type": "local handler and mocked AWS observations; not live AWS validation",
            "passed": all(r["passed"] and r["evidence_excludes_fault_selector"] for r in results),
            "scenarios": results}


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
