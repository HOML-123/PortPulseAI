
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

REGISTRY_FILE = ROOT / "data" / "processed" / "exception_status_registry.csv"
QUEUE_FILE = ROOT / "data" / "processed" / "port_call_exception_queue_managed.csv"
HISTORY_FILE = ROOT / "data" / "processed" / "exception_status_history.csv"
ISSUES_FILE = ROOT / "data" / "processed" / "exception_status_validation_issues.csv"
INTEGRATION_FILE = ROOT / "outputs" / "reports" / "exception_workflow_integration.txt"

REPORT_FILE = ROOT / "outputs" / "reports" / "exception_workflow_health_report.txt"
SNAPSHOT_FILE = ROOT / "data" / "processed" / "exception_workflow_health_snapshot.csv"

VALID_STATUSES = {"Open", "In Progress", "Resolved", "Closed"}


def read_required_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return pd.read_csv(path, dtype={"exception_id": "string"})


def clean_ids(series):
    return series.fillna("").astype(str).str.strip()


def main():
    registry = read_required_csv(REGISTRY_FILE)
    queue = read_required_csv(QUEUE_FILE)
    history = read_required_csv(HISTORY_FILE)
    issues = read_required_csv(ISSUES_FILE)

    if "exception_id" not in registry.columns:
        raise ValueError("The registry does not contain exception_id.")

    if "queue_status" not in registry.columns:
        raise ValueError("The registry does not contain queue_status.")

    if "exception_id" not in queue.columns:
        raise ValueError("The managed queue does not contain exception_id.")

    if "queue_status" not in queue.columns:
        raise ValueError("The managed queue does not contain queue_status.")

    if "exception_id" not in history.columns:
        raise ValueError("The status history does not contain exception_id.")

    registry_ids = clean_ids(registry["exception_id"])
    queue_ids = clean_ids(queue["exception_id"])

    valid_registry_ids = registry_ids[registry_ids.ne("")]
    valid_queue_ids = queue_ids[queue_ids.ne("")]

    registry_id_set = set(valid_registry_ids)
    queue_id_set = set(valid_queue_ids)

    duplicate_registry_ids = int(valid_registry_ids.duplicated().sum())
    duplicate_queue_ids = int(valid_queue_ids.duplicated().sum())

    registry_statuses = registry["queue_status"].fillna("").astype(str).str.strip()
    queue_statuses = queue["queue_status"].fillna("").astype(str).str.strip()

    invalid_registry_statuses = int(
        (~registry_statuses.isin(VALID_STATUSES)).sum()
    )
    invalid_queue_statuses = int(
        (~queue_statuses.isin(VALID_STATUSES)).sum()
    )

    registry_lookup = {}
    for exception_id, status in zip(registry_ids, registry_statuses):
        if exception_id and exception_id not in registry_lookup:
            registry_lookup[exception_id] = status

    queue_lookup = {}
    for exception_id, status in zip(queue_ids, queue_statuses):
        if exception_id and exception_id not in queue_lookup:
            queue_lookup[exception_id] = status

    missing_registry_ids = queue_id_set - registry_id_set

    mismatched_statuses = sum(
        1
        for exception_id in queue_id_set & registry_id_set
        if registry_lookup.get(exception_id) != queue_lookup.get(exception_id)
    )

    if "present_in_source" in registry.columns:
        source_presence = (
            registry["present_in_source"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )
        absent_from_source = int(
            source_presence.isin({"false", "0", "no"}).sum()
        )
    else:
        absent_from_source = -1

    status_counts = {
        status: int(registry_statuses.eq(status).sum())
        for status in sorted(VALID_STATUSES)
    }

    history_event_count = len(history)
    validation_issue_count = len(issues)

    integration_result = "UNKNOWN"

    if INTEGRATION_FILE.exists():
        integration_text = INTEGRATION_FILE.read_text(encoding="utf-8")
        for line in integration_text.splitlines():
            if line.startswith("OVERALL RESULT:"):
                integration_result = line.split(":", 1)[1].strip()
                break

    consistency_problem_count = (
        duplicate_registry_ids
        + duplicate_queue_ids
        + invalid_registry_statuses
        + invalid_queue_statuses
        + len(missing_registry_ids)
        + mismatched_statuses
    )

    if integration_result == "PASS" and validation_issue_count == 0:
        health_status = "HEALTHY"
    elif integration_result == "UNKNOWN":
        health_status = "REVIEW"
    else:
        health_status = "REVIEW"

    if consistency_problem_count > 0 or validation_issue_count > 0:
        health_status = "REVIEW"

    generated_at = datetime.now(timezone.utc).isoformat()

    metrics = [
        ("generated_at_utc", generated_at),
        ("health_status", health_status),
        ("integration_result", integration_result),
        ("registry_rows", len(registry)),
        ("managed_queue_rows", len(queue)),
        ("history_events", history_event_count),
        ("validation_issue_count", validation_issue_count),
        ("duplicate_registry_ids", duplicate_registry_ids),
        ("duplicate_queue_ids", duplicate_queue_ids),
        ("invalid_registry_statuses", invalid_registry_statuses),
        ("invalid_queue_statuses", invalid_queue_statuses),
        ("queue_ids_missing_from_registry", len(missing_registry_ids)),
        ("status_mismatches", mismatched_statuses),
        ("registry_exceptions_absent_from_source", absent_from_source),
    ]

    for status, count in status_counts.items():
        metrics.append((f"registry_status_{status.lower().replace(' ', '_')}", count))

    snapshot = pd.DataFrame(metrics, columns=["metric", "value"])

    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    snapshot.to_csv(SNAPSHOT_FILE, index=False)

    report_lines = [
        "PORTPULSEAI EXCEPTION WORKFLOW HEALTH REPORT",
        f"Generated UTC: {generated_at}",
        f"Overall health: {health_status}",
        f"Latest integration result: {integration_result}",
        "",
        "RECORD COUNTS",
        f"Registry rows: {len(registry)}",
        f"Managed queue rows: {len(queue)}",
        f"History events: {history_event_count}",
        f"Validation issues: {validation_issue_count}",
        "",
        "STATUS COUNTS IN REGISTRY",
    ]

    for status, count in status_counts.items():
        report_lines.append(f"{status}: {count}")

    report_lines.extend([
        "",
        "CONSISTENCY CHECKS",
        f"Duplicate registry IDs: {duplicate_registry_ids}",
        f"Duplicate managed queue IDs: {duplicate_queue_ids}",
        f"Invalid registry statuses: {invalid_registry_statuses}",
        f"Invalid managed queue statuses: {invalid_queue_statuses}",
        f"Queue IDs missing from registry: {len(missing_registry_ids)}",
        f"Status mismatches: {mismatched_statuses}",
        f"Registry exceptions absent from source: {absent_from_source}",
        "",
        "INTERPRETATION",
        "HEALTHY means the latest integration report passed and the saved validation issue file is empty.",
        "REVIEW means the workflow needs review or its latest integration result is unavailable.",
        "An exception absent from the source queue is not automatically considered resolved.",
        "This report summarizes saved files and does not verify real-world port operations.",
        "",
        f"Snapshot file: {SNAPSHOT_FILE}",
    ])

    REPORT_FILE.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("\n".join(report_lines))
    print(f"\nReport saved to: {REPORT_FILE}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as error:
        print(f"Health report could not be generated: {error}")
        raise SystemExit(1)
