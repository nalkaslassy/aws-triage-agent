import copy
import importlib.util
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aws_triage.agent import run_agent, agent_markdown
from aws_triage.evaluation import load_suite, evaluate_suite
from aws_triage.followups import ReplayFollowups
from aws_triage.model import Bundle, Evidence
from aws_triage.planner import ReplayPlanner
from aws_triage.signals import classify
from test_agent import case, run, ROOT


def transient_item(code="ThrottlingException"):
    return Evidence("Transient", "followup_failure", "orders", "permissions", "unavailable",
                    {"reason": "Collection failed", "error_code": code}, "2026-10-30T12:15:00Z")


class IncidentBindingTests(unittest.TestCase):
    def test_simulation_only_cannot_explain_an_incident(self):
        value = case()
        value["bundle"]["evidence"] = []
        value["decisions"][-1]["candidates"][0]["supporting"] = ["F002"]
        result, _ = run(value)
        self.assertEqual(result["stop_reason"], "invalid_decision")
        self.assertEqual(result["assessment"]["candidates"], [])
        self.assertTrue(any(f["title"] == "Current IAM simulation result observed" for f in result["report"]["findings"]))

    def test_candidate_requires_request_id_action_and_target(self):
        for field in ("request_id", "operation", "target"):
            value = case()
            del value["bundle"]["evidence"][0]["data"]["samples"][0][field]
            with self.subTest(field=field):
                self.assertEqual(run(value)[0]["stop_reason"], "invalid_decision")

    def test_mismatched_simulation_cannot_be_used_as_support_or_counterevidence(self):
        for name in ("permission_denied", "contradictory_simulation"):
            value = case(name)
            simulation = next(e for e in value["followups"]["permissions"] if e["kind"] == "permission_simulation")
            simulation["data"]["target"] = "arn:aws:dynamodb:us-east-1:111122223333:table/unrelated-table"
            with self.subTest(name=name):
                self.assertEqual(run(value)[0]["stop_reason"], "invalid_decision")

    def test_matching_failure_has_specific_handoff(self):
        result, _ = run(case())
        summary = result["summary"]
        for text in ("local-request-1", "PutItem", "orders-table"):
            self.assertIn(text, summary["leading_candidate"]["explanation"])
            self.assertIn(text, summary["next_verification"])
        self.assertIn("actual principal", summary["next_verification"])

    def test_summary_escapes_untrusted_symptom(self):
        value = case()
        value["symptom"] = '[unsafe](https://untrusted.example) <script>alert(1)</script>'
        result, _ = run(value)
        rendered = agent_markdown(result)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('[unsafe](https://untrusted.example)', rendered)

    def test_request_trace_identifier_retained_and_grouped(self):
        value = case()
        trace = "1-690344c0-111111111111111111111111"
        value["bundle"]["evidence"][0]["data"]["samples"][0]["trace_id"] = trace
        result, _ = run(value)
        self.assertEqual(result["summary"]["request_correlations"][0]["trace_ids"], [trace])
        self.assertIn("not a complete distributed trace", result["summary"]["limits"])
        signals, details, _ = classify(json.dumps({"event": "dependency_failure", "error_code": "AccessDeniedException", "trace_id": trace}))
        self.assertEqual(details["trace_id"], trace)
        self.assertEqual(signals, {"access_denied"})

    def test_sandbox_logs_only_valid_root_trace_id(self):
        from test_sandbox import LAB
        app = LAB.load_app()
        trace = "1-690344c0-111111111111111111111111"
        with patch.dict("os.environ", {"_X_AMZN_TRACE_ID": f"Root={trace};Parent=PRIVATE_PARENT;Sampled=1"}), patch.object(app.LOG, "log") as log:
            app.emit(logging.ERROR, {"event": "application_exception", "request_id": "request-1"})
            text = log.call_args.args[1]
            self.assertEqual(json.loads(text)["trace_id"], trace)
            self.assertNotIn("PRIVATE_PARENT", text)
        with patch.dict("os.environ", {"_X_AMZN_TRACE_ID": "Root=invalid;Parent=PRIVATE_PARENT"}), patch.object(app.LOG, "log") as log:
            app.emit(logging.ERROR, {"event": "application_exception"})
            self.assertNotIn("trace_id", json.loads(log.call_args.args[1]))


class OutcomeAndRetryTests(unittest.TestCase):
    def execute(self, responses, code="ThrottlingException", times=3):
        value = case()
        class Backend:
            def __init__(self):
                self.calls = 0
            def run(self, check):
                self.calls += 1
                return responses[min(self.calls - 1, len(responses) - 1)]
        backend = Backend()
        decisions = [{"action": "check", "check": "permissions"}] * times + [{"action": "finish", "candidates": [], "next_steps": ["collect_missing"]}]
        result = run_agent(Bundle.from_dict(value["bundle"]), value["manifest"], "orders", value["symptom"], ReplayPlanner(decisions), backend)
        return result, backend

    def test_unavailable_check_is_not_successful(self):
        result, _ = run(case("missing_policy_access"))
        self.assertEqual(result["journal"][0]["status"], "unavailable")
        self.assertEqual(result["summary"]["incomplete_checks"][0]["check"], "permissions")

    def test_mixed_results_are_partial(self):
        observed = Evidence(**case()["followups"]["permissions"][0])
        result, _ = self.execute([[observed, transient_item("AccessDeniedException")]], times=1)
        self.assertEqual(result["journal"][0]["status"], "partial")
        self.assertFalse(result["journal"][0]["retryable"])

    def test_transient_failure_can_retry_once_and_preserves_prior_evidence(self):
        observed = Evidence(**case()["followups"]["permissions"][1])
        result, backend = self.execute([[transient_item()], [observed]])
        self.assertEqual(backend.calls, 2)
        self.assertEqual([j["status"] for j in result["journal"]], ["unavailable", "successful", "cached"])
        self.assertEqual(result["journal"][-1]["cached_outcome"], "successful")
        self.assertEqual(result["metrics"]["retry_attempts"], 1)
        self.assertEqual(len(result["evidence_bundle"]["evidence"]), 3)
        self.assertEqual(result["summary"]["incomplete_checks"], [])

    def test_continuous_transient_failures_still_stop_at_two_attempts(self):
        result, backend = self.execute([[transient_item()]])
        self.assertEqual(backend.calls, 2)
        self.assertEqual(result["journal"][-1]["status"], "cached")
        self.assertFalse(result["journal"][1]["retryable"])

    def test_access_denial_deadline_and_unknown_failure_never_retry(self):
        for code in ("AccessDeniedException", "TimeoutError", "ValueError"):
            with self.subTest(code=code):
                result, backend = self.execute([[transient_item(code)]])
                self.assertEqual(backend.calls, 1)
                self.assertEqual(result["metrics"]["retry_attempts"], 0)


class EvaluationBoundaryTests(unittest.TestCase):
    def test_preflight_loads_five_separate_input_packets(self):
        packets, rubric = load_suite(ROOT / "evaluation")
        self.assertEqual(len(packets), 5)
        self.assertEqual(set(rubric), {identity for identity, _, _ in packets})
        for _, packet, digest in packets:
            self.assertNotIn("decisions", packet)
            self.assertNotIn("expected", packet)
            self.assertEqual(len(digest), 64)

    def test_planner_receives_no_case_id_rubric_or_scripted_answers(self):
        payloads = []
        class Planner:
            def next(self, state):
                payloads.append(json.dumps(state))
                return {"action": "finish", "candidates": [], "next_steps": ["collect_missing"]}
        result = evaluate_suite(ROOT / "evaluation", Planner, limit=5)
        self.assertEqual(result["total_runs"], 5)
        for payload in payloads:
            for forbidden in ('"allowed_causes"', '"required_checks"', '"require_counterevidence"', '"case01"', '"decisions"'):
                self.assertNotIn(forbidden, payload)
        self.assertLess(result["rubric_passes"], result["total_runs"])
        self.assertTrue(result["human_causal_review_required"])

    def test_preflight_does_not_require_or_call_bedrock(self):
        spec = importlib.util.spec_from_file_location("evaluate_model", ROOT / "sandbox/evaluate_model.py")
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preflight.json"
            self.assertEqual(script.main(["--out", str(path)]), 0)
            self.assertEqual(json.loads(path.read_text())["model_calls"], 0)

    def test_live_evaluation_requires_explicit_opt_in(self):
        spec = importlib.util.spec_from_file_location("evaluate_model_optin", ROOT / "sandbox/evaluate_model.py")
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            script.main(["--out", str(Path(folder) / "out.json"), "--run-bedrock", "--model-id", "operator-selected-model"])
