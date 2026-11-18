import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "sandbox") not in sys.path:
    sys.path.insert(0, str(ROOT / "sandbox"))

VALIDATE_SPEC = importlib.util.spec_from_file_location(
    "live_validation",
    ROOT / "sandbox" / "validate_live_records.py",
)
LIVE = importlib.util.module_from_spec(VALIDATE_SPEC)
VALIDATE_SPEC.loader.exec_module(LIVE)

RENDER_SPEC = importlib.util.spec_from_file_location(
    "validation_report",
    ROOT / "sandbox" / "render_validation_report.py",
)
REPORT = importlib.util.module_from_spec(RENDER_SPEC)
RENDER_SPEC.loader.exec_module(REPORT)


class ValidationReportTests(unittest.TestCase):
    def summary(self):
        rows = []
        for i, scenario in enumerate(LIVE.SCENARIOS):
            rows.append({
                "scenario": scenario,
                "commit_sha": "a" * 40,
                "python_version": "3.12.8",
                "region": "us-east-1",
                "root_cause": "correct" if scenario != "normal" else "insufficient_evidence",
                "claims_supported": True,
                "unsupported_assertions_present": False,
                "inappropriate_remediation_present": False,
                "missing_as_healthy": False,
                "investigator_mutated": False,
                "scope_escape": False,
                "collection_elapsed_seconds": 1.0 + i,
                "analysis_elapsed_seconds": 0.2,
                "sdk_operations": 10 + i,
                "model_used": False,
            })
        return {
            "schema_version": LIVE.SUMMARY_SCHEMA_VERSION,
            "evaluation_type": "controlled disposable AWS sandbox; human-reviewed development validation",
            "production_accuracy_claim": False,
            "commit_sha": "a" * 40,
            "scenario_count": 5,
            "passed_safety_gate": True,
            "root_cause_counts": {
                "correct": 4,
                "incorrect": 0,
                "insufficient_evidence": 1,
            },
            "scenarios": rows,
        }

    def test_render_contains_all_scenarios_and_caveats(self):
        text = REPORT.render(self.summary())
        for scenario in LIVE.SCENARIOS:
            self.assertIn(scenario, text)
        self.assertIn("does not establish production accuracy", text)
        self.assertIn("Production accuracy claim: **none**", text)

    def test_failed_gate_is_rendered_not_hidden(self):
        summary = self.summary()
        summary["passed_safety_gate"] = False
        summary["scenarios"][1]["unsupported_assertions_present"] = True
        text = REPORT.render(summary)
        self.assertIn("Safety gate: **FAIL**", text)
        self.assertIn("permission_denied", text)
        self.assertIn("| yes |", text)

    def test_renderer_rejects_summary_shape_tampering(self):
        summary = self.summary()
        summary["scenario_count"] = 4
        with self.assertRaises(ValueError):
            REPORT.render(summary)

    def test_renderer_rejects_production_claim(self):
        summary = self.summary()
        summary["production_accuracy_claim"] = True
        with self.assertRaisesRegex(ValueError, "production"):
            REPORT.render(summary)

    def test_written_report_is_private_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "validation.md"
            REPORT.write_text_private(path, REPORT.render(self.summary()))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                REPORT.write_text_private(path, "replacement")

    def test_private_fields_cannot_be_rendered(self):
        summary = self.summary()
        summary["account_id"] = "111122223333"
        summary["request_id"] = "PRIVATE-REQUEST"
        text = REPORT.render(summary)
        self.assertNotIn("111122223333", text)
        self.assertNotIn("PRIVATE-REQUEST", text)


if __name__ == "__main__":
    unittest.main()
