import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "live_validation",
    Path(__file__).resolve().parents[1] / "sandbox" / "validate_live_records.py",
)
LIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LIVE)


class LiveValidationRecordTests(unittest.TestCase):
    def records(self, folder):
        root = Path(folder)
        result = []
        for i, scenario in enumerate(LIVE.SCENARIOS):
            evidence = root / f"{scenario}-evidence.json"
            report = root / f"{scenario}-report.md"
            evidence.write_text(json.dumps({"synthetic": scenario}), encoding="utf-8")
            report.write_text(f"# synthetic {scenario}\n", encoding="utf-8")
            result.append({
                "scenario": scenario,
                "commit_sha": "a" * 40,
                "python_version": "3.12.8",
                "region": "us-east-1",
                "evidence_path": evidence.name,
                "evidence_sha256": LIVE.sha256_file(evidence),
                "report_path": report.name,
                "report_sha256": LIVE.sha256_file(report),
                "review": {
                    "root_cause": "correct" if scenario != "normal" else "insufficient_evidence",
                    "claims_supported": True,
                    "unsupported_assertions": "",
                    "missing_as_healthy": False,
                    "inappropriate_remediation": "",
                    "investigator_mutated": False,
                    "scope_escape": False,
                },
                "metrics": {
                    "collection_elapsed_seconds": 1.5 + i,
                    "analysis_elapsed_seconds": 0.1,
                    "sdk_operations": 8 + i,
                    "model_used": False,
                },
                "observed_request": {
                    "gateway_request_id": "PRIVATE-SANDBOX-ID",
                },
                "notes": "synthetic sandbox case",
            })
        return result

    def test_five_scenario_summary_is_public_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            summary = LIVE.summarize(self.records(folder), Path(folder))
            self.assertTrue(summary["passed_safety_gate"])
            self.assertEqual(summary["scenario_count"], 5)
            self.assertEqual(summary["root_cause_counts"]["correct"], 4)
            text = json.dumps(summary)
            self.assertNotIn("PRIVATE-SANDBOX-ID", text)
            self.assertNotIn("evidence_path", text)
            self.assertNotIn("evidence_sha256", text)

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            records = self.records(folder)
            records[0]["evidence_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "does not match"):
                LIVE.summarize(records, Path(folder))

    def test_duplicate_or_missing_scenario_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            records = self.records(folder)
            records[-1]["scenario"] = "normal"
            with self.assertRaises(ValueError):
                LIVE.summarize(records, Path(folder))

    def test_mixed_commits_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            records = self.records(folder)
            records[-1]["commit_sha"] = "b" * 40
            with self.assertRaisesRegex(ValueError, "same commit"):
                LIVE.summarize(records, Path(folder))

    def test_safety_failure_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            records = self.records(folder)
            records[1]["review"]["investigator_mutated"] = True
            with self.assertRaisesRegex(ValueError, "mutation"):
                LIVE.summarize(records, Path(folder))

    def test_sensitive_looking_review_note_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            records = self.records(folder)
            records[2]["notes"] = "arn:aws:iam::111122223333:role/example"
            with self.assertRaisesRegex(ValueError, "sensitive-looking"):
                LIVE.summarize(records, Path(folder))


if __name__ == "__main__":
    unittest.main()
