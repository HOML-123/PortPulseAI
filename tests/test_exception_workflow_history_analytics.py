
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

import src.exception_workflow_history_analytics as analytics


class TestExceptionWorkflowHistoryAnalytics(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)

        self.history_file = self.test_root / "history.csv"
        self.daily_file = self.test_root / "daily.csv"
        self.event_file = self.test_root / "events.csv"
        self.transition_file = self.test_root / "transitions.csv"
        self.report_file = self.test_root / "report.txt"

        self.history = pd.DataFrame([
            {
                "event_timestamp_utc": "2026-10-18T09:00:00Z",
                "exception_id": "EXC-001",
                "event_type": "EXCEPTION_REGISTERED",
                "previous_status": "",
                "new_status": "Open",
                "details": "Registered",
            },
            {
                "event_timestamp_utc": "2026-10-18T10:00:00Z",
                "exception_id": "EXC-001",
                "event_type": "STATUS_CHANGED",
                "previous_status": "Open",
                "new_status": "In Progress",
                "details": "Status updated",
            },
            {
                "event_timestamp_utc": "2026-10-19T11:00:00Z",
                "exception_id": "EXC-002",
                "event_type": "EXCEPTION_REGISTERED",
                "previous_status": "",
                "new_status": "Open",
                "details": "Registered",
            },
        ])

        self.write_history()

        self.patches = [
            patch.object(analytics, "HISTORY_FILE", self.history_file),
            patch.object(analytics, "DAILY_OUTPUT", self.daily_file),
            patch.object(analytics, "EVENT_OUTPUT", self.event_file),
            patch.object(analytics, "TRANSITION_OUTPUT", self.transition_file),
            patch.object(analytics, "REPORT_FILE", self.report_file),
        ]

        for active_patch in self.patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_history(self):
        self.history.to_csv(self.history_file, index=False)

    def test_daily_summary_counts_events_by_date(self):
        history = analytics.read_history()
        daily = analytics.build_daily_summary(history)

        self.assertEqual(len(daily), 2)

        first_day = daily[daily["event_date_utc"] == "2026-10-18"].iloc[0]

        self.assertEqual(int(first_day["total_events"]), 2)
        self.assertEqual(int(first_day["unique_exceptions"]), 1)
        self.assertEqual(int(first_day["status_changes"]), 1)
        self.assertEqual(int(first_day["registrations"]), 1)

    def test_event_summary_counts_event_types(self):
        history = analytics.read_history()
        summary = analytics.build_event_summary(history)

        counts = dict(zip(summary["event_type"], summary["event_count"]))

        self.assertEqual(int(counts["EXCEPTION_REGISTERED"]), 2)
        self.assertEqual(int(counts["STATUS_CHANGED"]), 1)

    def test_transition_summary_counts_status_changes(self):
        history = analytics.read_history()
        summary = analytics.build_transition_summary(history)

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.iloc[0]["previous_status"], "Open")
        self.assertEqual(summary.iloc[0]["new_status"], "In Progress")
        self.assertEqual(int(summary.iloc[0]["transition_count"]), 1)

    def test_invalid_timestamp_is_reported(self):
        self.history.loc[0, "event_timestamp_utc"] = "not-a-date"
        self.write_history()

        with contextlib.redirect_stdout(io.StringIO()):
            analytics.main()

        report = self.report_file.read_text(encoding="utf-8")

        self.assertIn("Events with invalid timestamps: 1", report)

    def test_main_creates_all_output_files(self):
        with contextlib.redirect_stdout(io.StringIO()):
            analytics.main()

        self.assertTrue(self.daily_file.exists())
        self.assertTrue(self.event_file.exists())
        self.assertTrue(self.transition_file.exists())
        self.assertTrue(self.report_file.exists())

    def test_empty_history_produces_empty_summaries(self):
        empty_history = pd.DataFrame(columns=[
            "event_timestamp_utc",
            "exception_id",
            "event_type",
            "previous_status",
            "new_status",
            "details",
        ])

        daily = analytics.build_daily_summary(empty_history)
        events = analytics.build_event_summary(empty_history)
        transitions = analytics.build_transition_summary(empty_history)

        self.assertTrue(daily.empty)
        self.assertTrue(events.empty)
        self.assertTrue(transitions.empty)

    def test_missing_required_column_is_rejected(self):
        self.history.drop(columns=["event_type"]).to_csv(
            self.history_file,
            index=False,
        )

        with self.assertRaises(ValueError):
            analytics.read_history()


if __name__ == "__main__":
    unittest.main()
