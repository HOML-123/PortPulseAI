
import unittest

import pandas as pd

from src.port_call_exception_management import (
    build_exception_queue,
    create_exception_id,
)


class TestExceptionIdStability(unittest.TestCase):

    def setUp(self):
        self.data = pd.DataFrame([
            {
                "port_call_id": "PC-100",
                "vessel_name": "Vessel Alpha",
                "voyage_number": "VOY-100",
                "berth": "Berth 1",
                "actual_arrival": "2026-10-19 08:00:00",
                "actual_berthing": "",
                "actual_departure": "",
                "coordination_flags": (
                    "Overdue Arrival | Berth Window Conflict"
                ),
                "coordination_priority": "High",
                "data_source": "TEST",
            },
            {
                "port_call_id": "PC-200",
                "vessel_name": "Vessel Beta",
                "voyage_number": "VOY-200",
                "berth": "Berth 2",
                "actual_arrival": "",
                "actual_berthing": "",
                "actual_departure": "",
                "coordination_flags": "Overdue Departure",
                "coordination_priority": "Medium",
                "data_source": "TEST",
            },
        ])

    def test_same_issue_gets_same_id(self):
        first = create_exception_id("PC-100", "Overdue Arrival")
        second = create_exception_id("PC-100", "Overdue Arrival")

        self.assertEqual(first, second)

    def test_id_is_independent_of_letter_case(self):
        first = create_exception_id("PC-100", "Overdue Arrival")
        second = create_exception_id("pc-100", "overdue arrival")

        self.assertEqual(first, second)

    def test_different_exceptions_get_different_ids(self):
        first = create_exception_id("PC-100", "Overdue Arrival")
        second = create_exception_id("PC-100", "Berth Window Conflict")

        self.assertNotEqual(first, second)

    def test_queue_ids_survive_row_reordering(self):
        first_queue = build_exception_queue(self.data)
        reordered_data = self.data.iloc[::-1].reset_index(drop=True)
        second_queue = build_exception_queue(reordered_data)

        first_ids = set(first_queue["exception_id"])
        second_ids = set(second_queue["exception_id"])

        self.assertEqual(first_ids, second_ids)

    def test_repeated_flags_do_not_create_duplicate_entries(self):
        data = pd.DataFrame([{
            "port_call_id": "PC-300",
            "coordination_flags": (
                "Overdue Arrival | overdue arrival | Overdue Arrival"
            ),
            "coordination_priority": "High",
        }])

        queue = build_exception_queue(data)

        self.assertEqual(len(queue), 1)
        self.assertEqual(queue["exception_id"].nunique(), 1)


if __name__ == "__main__":
    unittest.main()
