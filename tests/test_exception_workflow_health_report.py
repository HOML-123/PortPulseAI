
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.exception_workflow_health_report as health_report


class TestExceptionWorkflowHealthReport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)

        self.registry_file = self.test_root / "registry.csv"
        self.queue_file = self.test_root / "queue.csv"
        self.history_file = self.test_root / "history.csv"
        self.issues_file = self.test_root / "issues.csv"
        self.integration_file = self.test_root / "integration.txt"
        self.report_file = self.test_root / "health_report.txt"
        self.snapshot_file = self.test_root / "health_snapshot.csv"

        self.registry = pd.DataFrame([
            {
                "exception_id": "EXC-001",
                "queue_status": "Open",
                "present_in_source": True,
            },
            {
                "exception_id": "EXC-002",
                "queue_status": "In Progress",
                "present_in_source": True,
            },
            {
                "exception_id": "EXC-003",
                "queue_status": "Resolved",
                "present_in_source": False,
            },
        ])

        self.queue = pd.DataFrame([
            {"exception_id": "EXC-001", "queue_status": "Open"},
            {"exception_id": "EXC-002", "queue_status": "In Progress"},
        ])

        self.history = pd.DataFrame([
            {"exception_id": "EXC-001"},
            {"exception_id": "EXC-002"},
        ])

        self.issues = pd.DataFrame(columns=["check", "details"])

        self.write_inputs()

        self.patches = [
            patch.object(health_report, "REGISTRY_FILE", self.registry_file),
            patch.object(health_report, "QUEUE_FILE", self.queue_file),
            patch.object(health_report, "HISTORY_FILE", self.history_file),
            patch.object(health_report, "ISSUES_FILE", self.issues_file),
            patch.object(health_report, "INTEGRATION_FILE", self.integration_file),
            patch.object(health_report, "REPORT_FILE", self.report_file),
            patch.object(health_report, "SNAPSHOT_FILE", self.snapshot_file),
        ]

        for active_patch in self.patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_inputs(self):
        self.registry.to_csv(self.registry_file, index=False)
        self.queue.to_csv(self.queue_file, index=False)
        self.history.to_csv(self.history_file, index=False)
        self.issues.to_csv(self.issues_file, index=False)
        self.integration_file.write_text(
            "OVERALL RESULT: PASS\n",
            encoding="utf-8",
        )

    def run_report(self):
        with contextlib.redirect_stdout(io.StringIO()):
            health_report.main()

        return self.report_file.read_text(encoding="utf-8")

    def test_consistent_data_produces_healthy_report(self):
        report = self.run_report()

        self.assertIn("Overall health: HEALTHY", report)
        self.assertIn("Duplicate registry IDs: 0", report)
        self.assertIn("Status mismatches: 0", report)
        self.assertTrue(self.snapshot_file.exists())

    def test_duplicate_registry_ids_require_review(self):
        self.registry.loc[1, "exception_id"] = "EXC-001"
        self.write_inputs()

        report = self.run_report()

        self.assertIn("Overall health: REVIEW", report)
        self.assertIn("Duplicate registry IDs: 1", report)

    def test_invalid_status_requires_review(self):
        self.registry.loc[0, "queue_status"] = "Waiting"
        self.write_inputs()

        report = self.run_report()

        self.assertIn("Overall health: REVIEW", report)
        self.assertIn("Invalid registry statuses: 1", report)

    def test_status_mismatch_requires_review(self):
        self.queue.loc[0, "queue_status"] = "Resolved"
        self.write_inputs()

        report = self.run_report()

        self.assertIn("Overall health: REVIEW", report)
        self.assertIn("Status mismatches: 1", report)

    def test_missing_integration_report_requires_review(self):
        self.integration_file.unlink()

        report = self.run_report()

        self.assertIn("Latest integration result: UNKNOWN", report)
        self.assertIn("Overall health: REVIEW", report)

    def test_validation_issues_require_review(self):
        self.issues = pd.DataFrame([
            {
                "check": "STATUS_MISMATCH",
                "details": "EXC-001 has inconsistent statuses",
            }
        ])
        self.write_inputs()

        report = self.run_report()

        self.assertIn("Validation issues: 1", report)
        self.assertIn("Overall health: REVIEW", report)

    def test_missing_source_exception_is_not_resolved_automatically(self):
        report = self.run_report()

        self.assertIn(
            "Registry exceptions absent from source: 1",
            report,
        )
        self.assertIn(
            "An exception absent from the source queue is not automatically considered resolved.",
            report,
        )


if __name__ == "__main__":
    unittest.main()
