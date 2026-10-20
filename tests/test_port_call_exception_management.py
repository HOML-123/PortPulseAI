
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from src import port_call_exception_management as engine


class TestPortCallExceptionManagement(unittest.TestCase):

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)

        self.folder = Path(self.temp_directory.name)
        self.input_file = self.folder / "coordination.csv"
        self.output_file = self.folder / "exceptions.csv"
        self.summary_file = self.folder / "summary.txt"

        now = pd.Timestamp.now().floor("min")

        records = [
            {
                "port_call_id": "PC-TEST-1",
                "vessel_name": "Test Vessel Alpha",
                "voyage_number": "TEST-01",
                "berth": "Berth 1",
                "actual_arrival": now - pd.Timedelta(hours=2),
                "actual_berthing": pd.NaT,
                "actual_departure": pd.NaT,
                "coordination_flags": (
                    "Overdue Arrival | Berth Window Conflict"
                ),
                "coordination_priority": "High",
                "data_source": "TEST",
            },
            {
                "port_call_id": "PC-TEST-2",
                "vessel_name": "Test Vessel Beta",
                "voyage_number": "TEST-02",
                "berth": "Berth 2",
                "actual_arrival": pd.NaT,
                "actual_berthing": pd.NaT,
                "actual_departure": pd.NaT,
                "coordination_flags": "",
                "coordination_priority": "Low",
                "data_source": "TEST",
            },
            {
                "port_call_id": "PC-TEST-3",
                "vessel_name": "Test Vessel Gamma",
                "voyage_number": "TEST-03",
                "berth": "Berth 3",
                "actual_arrival": pd.NaT,
                "actual_berthing": pd.NaT,
                "actual_departure": pd.NaT,
                "coordination_flags": "Overdue Departure",
                "coordination_priority": "Medium",
                "data_source": "TEST",
            },
        ]

        pd.DataFrame(records).to_csv(self.input_file, index=False)

        patches = [
            patch.object(engine, "INPUT", self.input_file),
            patch.object(engine, "OUTPUT", self.output_file),
            patch.object(engine, "SUMMARY", self.summary_file),
        ]

        for item in patches:
            item.start()
            self.addCleanup(item.stop)

        engine.main()

        self.queue = pd.read_csv(self.output_file)

    def test_expected_exception_count(self):
        self.assertEqual(len(self.queue), 3)

    def test_arrival_exception_assignment(self):
        exception = self.queue[
            self.queue["exception_description"] == "Overdue Arrival"
        ].iloc[0]

        self.assertEqual(
            exception["exception_type"], "Arrival Exception"
        )
        self.assertEqual(
            exception["responsible_team"], "Vessel Operations"
        )
        self.assertEqual(exception["queue_status"], "Open")

    def test_berth_conflict_assignment(self):
        exception = self.queue[
            self.queue["exception_description"]
            == "Berth Window Conflict"
        ].iloc[0]

        self.assertEqual(
            exception["exception_type"], "Berth Conflict"
        )
        self.assertEqual(
            exception["responsible_team"], "Berth Planning"
        )

    def test_departure_exception_assignment(self):
        exception = self.queue[
            self.queue["exception_description"]
            == "Overdue Departure"
        ].iloc[0]

        self.assertEqual(
            exception["exception_type"], "Departure Exception"
        )
        self.assertEqual(
            exception["responsible_team"], "Vessel Operations"
        )

    def test_last_known_milestone(self):
        exception = self.queue[
            self.queue["exception_description"] == "Overdue Arrival"
        ].iloc[0]

        self.assertIn(
            "Arrival recorded at",
            exception["last_known_milestone"],
        )

    def test_priorities_are_sorted(self):
        priorities = self.queue[
            "coordination_priority"
        ].tolist()

        self.assertEqual(
            priorities,
            ["High", "High", "Medium"],
        )

    def test_empty_queue(self):
        empty_data = pd.DataFrame(
            columns=[
                "port_call_id",
                "coordination_flags",
                "coordination_priority",
            ]
        )

        queue = engine.build_exception_queue(empty_data)

        self.assertTrue(queue.empty)
        self.assertIn("exception_id", queue.columns)

    def test_output_files_are_created(self):
        self.assertTrue(self.output_file.exists())
        self.assertTrue(self.summary_file.exists())

        summary = self.summary_file.read_text(encoding="utf-8")

        self.assertIn("Total exceptions: 3", summary)
        self.assertIn("High priority: 2", summary)
        self.assertIn("Medium priority: 1", summary)


if __name__ == "__main__":
    unittest.main()
