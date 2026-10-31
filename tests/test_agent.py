import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aws_triage.agent import run_agent, validate_decision, agent_markdown
from aws_triage.cli import main
from aws_triage.followups import ReplayFollowups
from aws_triage.model import Bundle, Evidence
from aws_triage.planner import BedrockPlanner, ReplayPlanner

ROOT = Path(__file__).resolve().parents[1]


def case(name="permission_denied"):
    return json.loads((ROOT / "examples" / "agent" / (name + ".json")).read_text())


def run(value, decisions=None, **budgets):
    backend = ReplayFollowups(value["followups"])
    result = run_agent(Bundle.from_dict(value["bundle"]), value["manifest"], value["function"], value["symptom"],
                       ReplayPlanner(decisions or value["decisions"]), backend, **budgets)
    return result, backend


class AgentTests(unittest.TestCase):
    def test_seven_contract_cases(self):
        paths = list((ROOT / "examples" / "agent").glob("*.json"))
        self.assertEqual(len(paths), 7)
        for path in paths:
            value = json.loads(path.read_text())
            with self.subTest(case=path.stem):
                result, _ = run(value)
                self.assertEqual(result["stop_reason"], value["expected"]["stop_reason"])
                self.assertEqual([c["cause"] for c in result["assessment"]["candidates"]], value["expected"]["causes"])

    def test_repeated_checks_are_cached(self):
        result, backend = run(case(), [{"action": "check", "check": "permissions"}] * 4, max_steps=4)
        self.assertEqual(backend.calls, ["permissions"])
        self.assertEqual(result["stop_reason"], "step_budget")
        self.assertEqual(result["journal"][1]["status"], "cached")
        self.assertEqual(len(result["evidence_bundle"]["evidence"]), 3)

    def test_no_cloud_calls_for_unsupported_tool_or_arbitrary_arguments(self):
        for decision in ({"action": "check", "check": "delete_stack"},
                         {"action": "check", "check": "permissions", "role": "other-account-role"}):
            with self.subTest(decision=decision):
                result, backend = run(case(), [decision])
                self.assertEqual(result["stop_reason"], "invalid_decision")
                self.assertEqual(backend.calls, [])

    def test_unknown_evidence_ids_and_unavailable_evidence_are_rejected(self):
        value = case()
        finish = copy.deepcopy(value["decisions"][-1])
        finish["candidates"][0]["supporting"] = ["invented"]
        result, _ = run(value, [finish])
        self.assertEqual(result["stop_reason"], "invalid_decision")
        value = case("missing_policy_access")
        value["decisions"][-1] = {"action": "finish", "candidates": [{"cause": "authorization", "supporting": ["F001"], "contradicting": []}], "next_steps": ["review_iam"]}
        self.assertEqual(run(value)[0]["stop_reason"], "invalid_decision")

    def test_model_cannot_emit_arbitrary_remediation_text(self):
        value = case()
        value["decisions"][-1]["next_steps"] = ["Attach AdministratorAccess immediately"]
        result, _ = run(value)
        self.assertEqual(result["stop_reason"], "invalid_decision")
        self.assertNotIn("Attach AdministratorAccess", json.dumps(result))

    def test_out_of_scope_evidence_is_not_shown_to_planner(self):
        value = case()
        foreign = copy.deepcopy(value["bundle"]["evidence"][0])
        foreign.update(id="OTHER", resource="/aws/lambda/another-application")
        value["bundle"]["evidence"].append(foreign)
        class Planner:
            def next(self, state):
                self.ids = [e["id"] for e in state["evidence"]]
                return {"action": "finish", "candidates": [], "next_steps": ["collect_missing"]}
        planner = Planner()
        result = run_agent(Bundle.from_dict(value["bundle"]), value["manifest"], value["function"], value["symptom"], planner, ReplayFollowups({}))
        self.assertEqual(planner.ids, ["E001"])
        self.assertNotIn("OTHER", json.dumps(result))

    def test_raw_log_messages_and_unknown_fields_excluded_from_model_context(self):
        value = case()
        value["bundle"]["evidence"][0]["data"]["message"] = "PRIVATE_RAW_LOG"
        value["bundle"]["evidence"][0]["data"]["secret"] = "PRIVATE_UNKNOWN_FIELD"
        class Planner:
            def next(self, state):
                self.payload = json.dumps(state)
                return {"action": "finish", "candidates": [], "next_steps": ["collect_missing"]}
        planner = Planner()
        run_agent(Bundle.from_dict(value["bundle"]), value["manifest"], value["function"], value["symptom"], planner, ReplayFollowups({}))
        self.assertNotIn("PRIVATE_RAW_LOG", planner.payload)
        self.assertNotIn("PRIVATE_UNKNOWN_FIELD", planner.payload)

    def test_simulation_allow_is_retained_as_counterevidence(self):
        result, _ = run(case("contradictory_simulation"))
        self.assertEqual(result["assessment"]["candidates"][0]["contradicting"], ["F001"])
        self.assertTrue(all(f["classification"] != "confirmed_root_cause" for f in result["report"]["findings"]))

    def test_deadline_stops_before_backend_action(self):
        with patch("aws_triage.agent.time.monotonic", side_effect=[0, 0, 61, 61]):
            result, backend = run(case())
        self.assertEqual(result["stop_reason"], "deadline")
        self.assertEqual(backend.calls, [])

    def test_runtime_reports_execution_metrics(self):
        result, _ = run(case())
        self.assertEqual(result["metrics"]["planner_turns"], 2)
        self.assertEqual(result["metrics"]["executed_checks"], 1)
        self.assertGreaterEqual(result["metrics"]["elapsed_seconds"], 0)
        self.assertIsNone(result["metrics"]["sdk_operations"])

    def test_planner_failure_keeps_deterministic_report(self):
        class Planner:
            def next(self, state):
                raise RuntimeError("PRIVATE_PROVIDER_ERROR")
        value = case()
        result = run_agent(Bundle.from_dict(value["bundle"]), value["manifest"], value["function"], value["symptom"], Planner(), ReplayFollowups({}))
        self.assertEqual(result["stop_reason"], "planner_unavailable")
        self.assertTrue(result["report"]["findings"])
        self.assertNotIn("PRIVATE_PROVIDER_ERROR", json.dumps(result))

    def test_cli_replay_and_markdown_require_no_sdk(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.md"
            self.assertEqual(main(["agent", "replay", str(ROOT / "examples/agent/permission_denied.json"), "--format", "markdown", "--out", str(path)]), 0)
            self.assertIn("Synthetic/scripted replay", path.read_text())
            self.assertIn("Candidate 1", path.read_text())

    def test_bedrock_requires_opt_in_and_unknown_output_is_rejected(self):
        client = Mock()
        with self.assertRaises(ValueError):
            BedrockPlanner(client, "operator-selected-model")
        client.converse.assert_not_called()
        client.converse.return_value = {"stopReason": "end_turn", "output": {"message": {"content": [{"text": "do something"}]}}}
        with self.assertRaises(ValueError):
            BedrockPlanner(client, "operator-selected-model", True).next({})

    def test_context_budget_prevents_model_call(self):
        client = Mock()
        with self.assertRaises(ValueError):
            BedrockPlanner(client, "operator-selected-model", True).next({"too_large": "x" * 25000})
        client.converse.assert_not_called()
