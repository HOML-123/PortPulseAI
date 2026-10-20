
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.exception_status_validation as validation


class TestExceptionStatusValidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.registry_path = self.root / "exception_status_registry.csv"
        self.queue_path = self.root / "port_call_exception_queue_managed.csv"
        self.history_path = self.root / "exception_status_history.csv"
        self.issues_path = self.root / "exception_status_validation_issues.csv"
        self.report_path = self.root / "exception_status_validation.txt"

        self.registry = pd.DataFrame([
            {
                "exception_id": "EXC-001",
                "queue_status": "Open",
                "created_at_utc": "2026-10-19T10:00:00Z",
                "updated_at_utc": "2026-10-19T10:00:00Z",
                "last_seen_at_utc": "2026-10-19T10:00:00Z",
                "present_in_source": True,
            },
            {
                "exception_id": "EXC-002",
                "queue_status": "In Progress",
                "created_at_utc": "2026-10-19T10:00:00Z",
                "updated_at_utc": "2026-10-19T10:00:00Z",
                "last_seen_at_utc": "2026-10-19T10:00:00Z",
                "present_in_source": True,
            },
        ])

        self.queue = pd.DataFrame([
            {"exception_id": "EXC-001", "queue_status": "Open"},
            {"exception_id": "EXC-002", "queue_status": "In Progress"},
        ])

        self.history = pd.DataFrame([
            {
                "event_timestamp_utc": "2026-10-19T10:00:00Z",
                "exception_id": "EXC-001",
                "event_type": "EXCEPTION_REGISTERED",
                "previous_status": "",
                "new_status": "Open",
                "details": "Test event",
            }
        ])

        self.write_inputs()

        self.patches = [
            patch.object(validation, "REGISTRY", self.registry_path),
            patch.object(validation, "MANAGED_QUEUE", self.queue_path),
            patch.object(validation, "EVENT_LOG", self.history_path),
            patch.object(validation, "ISSUES_FILE", self.issues_path),
            patch.object(validation, "REPORT_FILE", self.report_path),
        ]

        for active_patch in self.patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_inputs(self):
        self.registry.to_csv(self.registry_path, index=False)
        self.queue.to_csv(self.queue_path, index=False)
        self.history.to_csv(self.history_path, index=False)

    def run_validation(self):
        return validation.validate()

    def read_issues(self):
        return pd.read_csv(self.issues_path)

    def test_valid_files_pass_validation(self):
        issue_count = self.run_validation()

        self.assertEqual(issue_count, 0)
        self.assertTrue(self.report_path.exists())
        self.assertTrue(self.issues_path.exists())

    def test_invalid_registry_status_is_detected(self):
        self.registry.loc[0, "queue_status"] = "Waiting"
        self.write_inputs()

        self.run_validation()
        issues = self.read_issues()

        self.assertIn("REGISTRY_INVALID_STATUSES", issues["check"].tolist())

    def test_duplicate_registry_ids_are_detected(self):
        self.registry.loc[1, "exception_id"] = "EXC-001"
        self.write_inputs()

        self.run_validation()
        issues = self.read_issues()

        self.assertIn("DUPLICATE_REGISTRY_IDS", issues["check"].tolist())

    def test_duplicate_queue_ids_are_detected(self):
        self.queue.loc[1, "exception_id"] = "EXC-001"
        self.write_inputs()

        self.run_validation()
        issues = self.read_issues()

        self.assertIn("DUPLICATE_QUEUE_IDS", issues["check"].tolist())

    def test_status_mismatch_is_detected(self):
        self.queue.loc[0, "queue_status"] = "Resolved"
        self.write_inputs()

        self.run_validation()
        issues = self.read_issues()

        self.assertIn("STATUS_MISMATCH", issues["check"].tolist())

    def test_queue_id_missing_from_registry_is_detected(self):
        self.queue.loc[0, "exception_id"] = "EXC-999"
        self.write_inputs()

        self.run_validation()
        issues = self.read_issues()

        self.assertIn("QUEUE_IDS_NOT_IN_REGISTRY", issues["check"].tolist())

    def test_invalid_history_timestamp_is_detected(self):
        self.history.loc[0, "event_timestamp_utc"] = "not-a-date"
        self.write_inputs()

        self.run_validation()
        issues = self.read_issues()

        self.assertIn("HISTORY_INVALID_TIMESTAMPS", issues["check"].tolist())

    def test_empty_queue_exception_id_is_detected(self):
        self.queue.loc[0, "exception_id"] = ""
        self.write_inputs()

        self.run_validation()
        issues = self.read_issues()

        self.assertIn("QUEUE_EMPTY_IDS", issues["check"].tolist())


if __name__ == "__main__":
    unittest.main()
