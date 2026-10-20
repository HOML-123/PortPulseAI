
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

SCRIPTS = [
    (
        "Exception synchronization and validation",
        ROOT / "src" / "exception_workflow_integration.py",
    ),
    (
        "Exception history analytics",
        ROOT / "src" / "exception_workflow_history_analytics.py",
    ),
    (
        "Exception workflow health report",
        ROOT / "src" / "exception_workflow_health_report.py",
    ),
]

REPORT_FILE = ROOT / "outputs" / "reports" / "exception_workflow_full_run.txt"
LOG_FILE = ROOT / "outputs" / "reports" / "exception_workflow_full_run_log.txt"


def run_script(label, script_path):
    if not script_path.exists():
        return {
            "label": label,
            "return_code": 1,
            "output": f"Script not found: {script_path}",
        }

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
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
            "output": "The script exceeded the 300-second time limit.",
        }

    except OSError as error:
        return {
            "label": label,
            "return_code": 1,
            "output": f"Could not run script: {error}",
        }


def main():
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    results = []

    for label, script_path in SCRIPTS:
        result = run_script(label, script_path)
        results.append(result)

        if result["return_code"] != 0:
            break

    finished_at = datetime.now(timezone.utc).isoformat()
    passed = (
        len(results) == len(SCRIPTS)
        and all(result["return_code"] == 0 for result in results)
    )

    report_lines = [
        "PORTPULSEAI COMPLETE EXCEPTION WORKFLOW",
        f"Started UTC: {started_at}",
        f"Finished UTC: {finished_at}",
        "",
        "EXECUTION RESULTS",
    ]

    log_lines = [
        "PORTPULSEAI COMPLETE EXCEPTION WORKFLOW LOG",
        f"Started UTC: {started_at}",
        "",
    ]

    for result in results:
        status = "PASS" if result["return_code"] == 0 else "FAIL"

        report_lines.extend([
            f"{result['label']}: {status}",
            f"Exit code: {result['return_code']}",
            "",
        ])

        log_lines.extend([
            f"STEP: {result['label']}",
            f"Exit code: {result['return_code']}",
            result["output"],
            "",
        ])

    completed_count = len(results)

    if completed_count < len(SCRIPTS):
        next_label = SCRIPTS[completed_count][0]
        report_lines.extend([
            f"Remaining steps skipped after failure: {next_label}",
            "",
        ])

    report_lines.extend([
        f"STEPS COMPLETED: {completed_count} of {len(SCRIPTS)}",
        f"OVERALL RESULT: {'PASS' if passed else 'FAIL'}",
        "",
        "A PASS means every script completed with exit code zero.",
        "Review the detailed log if any step fails.",
        "A successful run does not prove that source data is complete or operationally accurate.",
    ])

    log_lines.extend([
        f"Finished UTC: {finished_at}",
        f"OVERALL RESULT: {'PASS' if passed else 'FAIL'}",
    ])

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

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
