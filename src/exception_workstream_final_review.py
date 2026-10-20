
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

REPORT_FILE = ROOT / "outputs" / "reports" / "exception_workstream_final_review.txt"
LOG_FILE = ROOT / "outputs" / "reports" / "exception_workstream_final_review_log.txt"

EXPECTED_OUTPUTS = [
    ROOT / "data" / "processed" / "port_call_coordination_results.csv",
    ROOT / "data" / "processed" / "berth_conflict_pairs.csv",
    ROOT / "data" / "processed" / "port_call_exception_queue.csv",
    ROOT / "data" / "processed" / "exception_type_summary.csv",
    ROOT / "data" / "processed" / "exception_team_summary.csv",
    ROOT / "data" / "processed" / "exception_priority_summary.csv",
    ROOT / "data" / "processed" / "exception_queue_prioritised.csv",
    ROOT / "data" / "processed" / "high_priority_open_exceptions.csv",
    ROOT / "data" / "processed" / "exception_audit_state.csv",
    ROOT / "data" / "processed" / "exception_audit_log.csv",
    ROOT / "data" / "processed" / "exception_status_registry.csv",
    ROOT / "data" / "processed" / "port_call_exception_queue_managed.csv",
    ROOT / "data" / "processed" / "exception_status_history.csv",
    ROOT / "data" / "processed" / "exception_status_validation_issues.csv",
    ROOT / "data" / "processed" / "exception_history_daily_summary.csv",
    ROOT / "data" / "processed" / "exception_history_event_summary.csv",
    ROOT / "data" / "processed" / "exception_history_transition_summary.csv",
    ROOT / "data" / "processed" / "exception_workflow_health_snapshot.csv",
    ROOT / "outputs" / "reports" / "port_call_coordination_summary.txt",
    ROOT / "outputs" / "reports" / "port_call_exception_summary.txt",
    ROOT / "outputs" / "reports" / "exception_queue_analytics.txt",
    ROOT / "outputs" / "reports" / "exception_queue_prioritisation.txt",
    ROOT / "outputs" / "reports" / "exception_audit_summary.txt",
    ROOT / "outputs" / "reports" / "exception_status_validation.txt",
    ROOT / "outputs" / "reports" / "exception_workflow_integration.txt",
    ROOT / "outputs" / "reports" / "exception_workflow_integration_log.txt",
    ROOT / "outputs" / "reports" / "exception_workflow_health_report.txt",
    ROOT / "outputs" / "reports" / "exception_workflow_history_analytics.txt",
    ROOT / "outputs" / "reports" / "exception_workflow_full_run.txt",
    ROOT / "outputs" / "reports" / "exception_workflow_full_run_log.txt",
]


def run_command(label, command, timeout_seconds=600):
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

        output_parts = [
            part for part in [
                result.stdout.strip(),
                result.stderr.strip(),
            ] if part
        ]

        return {
            "label": label,
            "return_code": result.returncode,
            "output": "\n".join(output_parts) or "No console output.",
        }

    except subprocess.TimeoutExpired:
        return {
            "label": label,
            "return_code": 1,
            "output": f"Command exceeded {timeout_seconds} seconds.",
        }

    except OSError as error:
        return {
            "label": label,
            "return_code": 1,
            "output": f"Could not run command: {error}",
        }


def main():
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()

    test_result = run_command(
        "Full unit test suite",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    )

    workflow_result = run_command(
        "Day 49 integrated exception workflow",
        [sys.executable, str(ROOT / "src" / "exception_workflow_full_run.py")],
    )

    missing_outputs = [
        str(path.relative_to(ROOT))
        for path in EXPECTED_OUTPUTS
        if not path.is_file()
    ]

    finished_at = datetime.now(timezone.utc).isoformat()

    tests_passed = test_result["return_code"] == 0
    workflow_passed = workflow_result["return_code"] == 0
    outputs_passed = len(missing_outputs) == 0

    overall_passed = tests_passed and workflow_passed and outputs_passed

    report_lines = [
        "PORTPULSEAI EXCEPTION WORKSTREAM FINAL REVIEW",
        f"Started UTC: {started_at}",
        f"Finished UTC: {finished_at}",
        "",
        f"FULL UNIT TEST SUITE: {'PASS' if tests_passed else 'FAIL'}",
        f"Test command exit code: {test_result['return_code']}",
        "",
        f"INTEGRATED WORKFLOW: {'PASS' if workflow_passed else 'FAIL'}",
        f"Workflow command exit code: {workflow_result['return_code']}",
        "",
        f"EXPECTED OUTPUT FILES: {'PASS' if outputs_passed else 'FAIL'}",
        f"Expected files checked: {len(EXPECTED_OUTPUTS)}",
        f"Missing files: {len(missing_outputs)}",
    ]

    if missing_outputs:
        report_lines.append("")
        report_lines.append("MISSING OUTPUT FILES")
        report_lines.extend(missing_outputs)

    report_lines.extend([
        "",
        f"OVERALL RESULT: {'PASS' if overall_passed else 'REVIEW REQUIRED'}",
        "",
        "Interpretation:",
        "- PASS means the discovered tests passed, the integrated workflow returned exit code zero, and expected output files exist.",
        "- REVIEW REQUIRED means at least one check failed.",
        "- File existence does not prove that data is accurate or operationally complete.",
        "- Synthetic demonstration data must not be presented as live port data.",
    ])

    log_lines = [
        "PORTPULSEAI EXCEPTION WORKSTREAM FINAL REVIEW LOG",
        f"Started UTC: {started_at}",
        "",
        "FULL UNIT TEST SUITE",
        f"Exit code: {test_result['return_code']}",
        test_result["output"],
        "",
        "DAY 49 INTEGRATED WORKFLOW",
        f"Exit code: {workflow_result['return_code']}",
        workflow_result["output"],
        "",
        "MISSING EXPECTED OUTPUT FILES",
        *(missing_outputs or ["None"]),
        "",
        f"OVERALL RESULT: {'PASS' if overall_passed else 'REVIEW REQUIRED'}",
        f"Finished UTC: {finished_at}",
    ]

    REPORT_FILE.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    print("\n".join(report_lines))
    print(f"\nReport saved to: {REPORT_FILE}")
    print(f"Detailed log saved to: {LOG_FILE}")

    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
