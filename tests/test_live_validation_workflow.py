import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "sandbox") not in sys.path:
    sys.path.insert(0, str(ROOT / "sandbox"))
SPEC = importlib.util.spec_from_file_location(
    "live_validation_workflow",
    ROOT / "sandbox" / "live_validation_workflow.py",
)
WORK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORK)


class LiveValidationWorkflowTests(unittest.TestCase):
    def make_artifacts(self, folder, records):
        root = Path(folder)
        for record in records:
            (root / record["evidence_path"]).write_text(
                json.dumps({"synthetic": record["scenario"]}), encoding="utf-8"
            )
            (root / record["report_path"]).write_text(
                f"# synthetic {record['scenario']}\n", encoding="utf-8"
            )

    def review_records(self, records):
        for record in records:
            record["review"]["root_cause"] = (
                "insufficient_evidence" if record["scenario"] == "normal" else "correct"
            )
            record["review"]["claims_supported"] = True
        return records

    def test_init_creates_exactly_five_stubs_without_ground_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.json"
            records = WORK.init_records(path, "a" * 40, "3.12.8", "us-east-1")
            self.assertEqual([r["scenario"] for r in records], list(WORK.SCENARIOS))
            text = path.read_text()
            self.assertNotIn("expected_http", text)
            self.assertNotIn("fault_mode", text)
            self.assertNotIn("account_id", text)

    def test_init_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.json"
            path.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                WORK.init_records(path, "a" * 40, "3.12.8", "us-east-1")

    def test_hash_populates_local_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.json"
            records = WORK.init_records(path, "a" * 40, "3.12.8", "us-east-1")
            self.make_artifacts(folder, records)
            updated = WORK.populate_hashes(path)
            self.assertTrue(all(len(r["evidence_sha256"]) == 64 for r in updated))
            self.assertTrue(all(len(r["report_sha256"]) == 64 for r in updated))

    def test_hash_rejects_absolute_artifact_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.json"
            records = WORK.init_records(path, "a" * 40, "3.12.8", "us-east-1")
            records[0]["evidence_path"] = str((Path(folder) / "absolute.json").resolve())
            path.write_text(json.dumps(records), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "relative"):
                WORK.populate_hashes(path)

    def test_finalize_produces_sanitized_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records_path = root / "records.json"
            output = root / "public-summary.json"
            records = WORK.init_records(records_path, "a" * 40, "3.12.8", "us-east-1")
            self.make_artifacts(folder, records)
            WORK.populate_hashes(records_path)
            records = WORK.load_records(records_path)
            self.review_records(records)
            records[0]["notes"] = "synthetic local validation"
            records_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
            result = WORK.finalize(records_path, output)
            self.assertTrue(result["passed_safety_gate"])
            text = output.read_text()
            self.assertNotIn("evidence_path", text)
            self.assertNotIn("report_path", text)
            self.assertNotIn("notes", text)

    def test_finalize_refuses_incomplete_human_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records_path = root / "records.json"
            output = root / "public-summary.json"
            records = WORK.init_records(records_path, "a" * 40, "3.12.8", "us-east-1")
            self.make_artifacts(folder, records)
            WORK.populate_hashes(records_path)
            with self.assertRaises(ValueError):
                WORK.finalize(records_path, output)


if __name__ == "__main__":
    unittest.main()
