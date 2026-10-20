
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from src import port_call_coordination as engine


class TestPortCallCoordination(unittest.TestCase):

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)

        self.folder = Path(self.temp_directory.name)
        self.input_file = self.folder / "port_calls.csv"
        self.results_file = self.folder / "results.csv"
        self.conflicts_file = self.folder / "conflicts.csv"
        self.report_file = self.folder / "summary.txt"

        now = pd.Timestamp.now().floor("min")

        records = [
            {
                "port_call_id": "PC-TEST-1",
                "vessel_name": "Test Vessel Alpha",
                "voyage_number": "TEST-01",
                "berth": "Berth 1",
                "estimated_arrival": now - pd.Timedelta(hours=23),
                "actual_arrival": now - pd.Timedelta(hours=20),
                "estimated_berthing": now - pd.Timedelta(hours=9),
                "actual_berthing": now - pd.Timedelta(hours=5),
                "estimated_departure": now + pd.Timedelta(hours=10),
                "actual_departure": now + pd.Timedelta(hours=10),
                "call_status": "Completed",
                "data_source": "TEST",
            },
            {
                "port_call_id": "PC-TEST-2",
                "vessel_name": "Test Vessel Beta",
                "voyage_number": "TEST-02",
                "berth": "Berth 1",
                "estimated_arrival": now - pd.Timedelta(hours=12),
                "actual_arrival": pd.NaT,
                "estimated_berthing": now - pd.Timedelta(hours=1),
                "actual_berthing": pd.NaT,
                "estimated_departure": now + pd.Timedelta(hours=8),
                "actual_departure": pd.NaT,
                "call_status": "Planned",
                "data_source": "TEST",
            },
            {
                "port_call_id": "PC-TEST-3",
                "vessel_name": "Test Vessel Gamma",
                "voyage_number": "TEST-03",
                "berth": "Berth 2",
                "estimated_arrival": now + pd.Timedelta(hours=24),
                "actual_arrival": pd.NaT,
                "estimated_berthing": now + pd.Timedelta(hours=30),
                "actual_berthing": pd.NaT,
                "estimated_departure": now + pd.Timedelta(hours=45),
                "actual_departure": pd.NaT,
                "call_status": "Planned",
                "data_source": "TEST",
            },
        ]

        pd.DataFrame(records).to_csv(self.input_file, index=False)

        self.patches = [
            patch.object(engine, "INPUT", self.input_file),
            patch.object(engine, "RESULTS", self.results_file),
            patch.object(engine, "CONFLICTS", self.conflicts_file),
            patch.object(engine, "REPORT", self.report_file),
        ]

        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

        engine.main()

        self.results = pd.read_csv(self.results_file)
        self.conflicts = pd.read_csv(self.conflicts_file)

    def test_delay_calculations(self):
        vessel = self.results[
            self.results["port_call_id"] == "PC-TEST-1"
        ].iloc[0]

        self.assertAlmostEqual(
            vessel["arrival_delay_hours"], 3.0, places=2
        )
        self.assertAlmostEqual(
            vessel["berthing_delay_hours"], 4.0, places=2
        )
        self.assertAlmostEqual(
            vessel["departure_delay_hours"], 0.0, places=2
        )

    def test_overdue_milestones_are_flagged(self):
        vessel = self.results[
            self.results["port_call_id"] == "PC-TEST-2"
        ].iloc[0]

        self.assertIn("Overdue Arrival", vessel["coordination_flags"])
        self.assertIn("Overdue Berthing", vessel["coordination_flags"])
        self.assertEqual(vessel["coordination_priority"], "High")

    def test_berth_overlap_is_detected(self):
        self.assertEqual(len(self.conflicts), 1)

        conflict = self.conflicts.iloc[0]

        self.assertEqual(conflict["berth"], "Berth 1")
        self.assertAlmostEqual(
            conflict["overlap_hours"], 9.0, places=2
        )

        alpha = self.results[
            self.results["port_call_id"] == "PC-TEST-1"
        ].iloc[0]

        beta = self.results[
            self.results["port_call_id"] == "PC-TEST-2"
        ].iloc[0]

        self.assertIn(
            "Berth Window Conflict", alpha["coordination_flags"]
        )
        self.assertIn(
            "Berth Window Conflict", beta["coordination_flags"]
        )

    def test_separate_berth_has_no_conflict(self):
        gamma = self.results[
            self.results["port_call_id"] == "PC-TEST-3"
        ].iloc[0]

        self.assertNotIn(
            "Berth Window Conflict", gamma["coordination_flags"]
        )
        self.assertEqual(gamma["coordination_priority"], "Low")

    def test_output_files_are_created(self):
        self.assertTrue(self.results_file.exists())
        self.assertTrue(self.conflicts_file.exists())
        self.assertTrue(self.report_file.exists())
        self.assertEqual(len(self.results), 3)


if __name__ == "__main__":
    unittest.main()
