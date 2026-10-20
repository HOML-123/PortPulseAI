
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.exception_workflow_integration as integration


class TestExceptionWorkflowIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)

        self.report_path = self.test_root / "reports" / "integration.txt"
        self.log_path = self.test_root / "reports" / "integration_log.txt"

        self.patches = [
            patch.object(integration, "REPORT_FILE", self.report_path),
            patch.object(integration, "LOG_FILE", self.log_path),
        ]

        for active_patch in self.patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_main(self, results):
        with patch.object(integration, "run_script", side_effect=results) as runner:
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = integration.main()

        return exit_code, runner

    def test_successful_workflow_returns_zero(self):
        results = [
            {
                "label": "Exception status synchronization",
                "return_code": 0,
                "output": "Synchronization completed.",
            },
            {
                "label": "Exception status validation",
                "return_code": 0,
                "output": "All validation checks passed.",
            },
        ]

        exit_code, runner = self.run_main(results)

        self.assertEqual(exit_code, 0)
        self.assertEqual(runner.call_count, 2)
        self.assertIn("OVERALL RESULT: PASS", self.report_path.read_text())
        self.assertTrue(self.log_path.exists())

    def test_sync_failure_skips_validation(self):
        results = [
            {
                "label": "Exception status synchronization",
                "return_code": 1,
                "output": "Synchronization failed.",
            }
        ]

        exit_code, runner = self.run_main(results)

        self.assertEqual(exit_code, 1)
        self.assertEqual(runner.call_count, 1)

        report = self.report_path.read_text()

        self.assertIn("Exception status validation: FAIL", report)
        self.assertIn("Skipped because synchronization failed.", report)
        self.assertIn("OVERALL RESULT: FAIL", report)

    def test_validation_failure_returns_one(self):
        results = [
            {
                "label": "Exception status synchronization",
                "return_code": 0,
                "output": "Synchronization completed.",
            },
            {
                "label": "Exception status validation",
                "return_code": 1,
                "output": "Validation issues detected.",
            },
        ]

        exit_code, runner = self.run_main(results)

        self.assertEqual(exit_code, 1)
        self.assertEqual(runner.call_count, 2)
        self.assertIn("OVERALL RESULT: FAIL", self.report_path.read_text())

    def test_report_and_log_include_script_output(self):
        results = [
            {
                "label": "Exception status synchronization",
                "return_code": 0,
                "output": "Sync test message.",
            },
            {
                "label": "Exception status validation",
                "return_code": 0,
                "output": "Validation test message.",
            },
        ]

        self.run_main(results)

        report = self.report_path.read_text()
        log = self.log_path.read_text()

        self.assertIn("Sync test message.", report)
        self.assertIn("Validation test message.", report)
        self.assertIn("Sync test message.", log)
        self.assertIn("Validation test message.", log)

    def test_sync_failure_is_recorded_in_log(self):
        results = [
            {
                "label": "Exception status synchronization",
                "return_code": 1,
                "output": "Test synchronization error.",
            }
        ]

        self.run_main(results)

        log = self.log_path.read_text()

        self.assertIn("Exit code: 1", log)
        self.assertIn("Test synchronization error.", log)


if __name__ == "__main__":
    unittest.main()
