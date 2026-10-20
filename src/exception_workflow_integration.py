
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

STATUS_SCRIPT = ROOT / "src" / "exception_status_management.py"
VALIDATION_SCRIPT = ROOT / "src" / "exception_status_validation.py"

REPORT_FILE = ROOT / "outputs" / "reports" / "exception_workflow_integration.txt"
LOG_FILE = ROOT / "outputs" / "reports" / "exception_workflow_integration_log.txt"


def run_script(script_path, label, arguments=None):
    if arguments is None:
        arguments = []

    if not script_path.exists():
        return {
            "label": label,
            "return_code": 1,
            "output": f"Script not found: {script_path}",
        }

    try:
        result = subprocess.run(
            [sys.executable, str(script_path), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

        output = "\n".join(
            part for part in [result.stdout.strip(), result.stderr.strip()] if part
        )

        return {
            "label": label,
            "return_code": result.returncode,
            "output": output or "No console output.",
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

    sync_result = run_script(
        STATUS_SCRIPT,
        "Exception status synchronization",
        ["sync"],
    )
    results.append(sync_result)

    if sync_result["return_code"] == 0:
        validation_result = run_script(
            VALIDATION_SCRIPT,
            "Exception status validation",
        )
        results.append(validation_result)
    else:
        results.append({
            "label": "Exception status validation",
            "return_code": 1,
            "output": "Skipped because synchronization failed.",
        })

    passed = all(result["return_code"] == 0 for result in results)
    finished_at = datetime.now(timezone.utc).isoformat()

    report_lines = [
        "PORTPULSEAI EXCEPTION WORKFLOW INTEGRATION REPORT",
        f"Started UTC: {started_at}",
        f"Finished UTC: {finished_at}",
        "",
    ]

    log_lines = []

    for result in results:
        status = "PASS" if result["return_code"] == 0 else "FAIL"

        report_lines.extend([
            f"{result['label']}: {status}",
            result["output"],
            "",
        ])

        log_lines.extend([
            f"=== {result['label']} ===",
            f"Exit code: {result['return_code']}",
            result["output"],
            "",
        ])

    report_lines.extend([
        f"OVERALL RESULT: {'PASS' if passed else 'FAIL'}",
        "",
        "A PASS means synchronization and validation both completed successfully.",
        "A FAIL requires review of the output above.",
        "An exception missing from the source queue is not automatically resolved.",
    ])

    LOG_FILE.write_text("\n".join(log_lines), encoding="utf-8")
    REPORT_FILE.write_text("\n".join(report_lines), encoding="utf-8")

    print("\n".join(report_lines))
    print(f"\nReport saved to: {REPORT_FILE}")
    print(f"Detailed log saved to: {LOG_FILE}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
