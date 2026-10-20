
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

REGISTRY = ROOT / "data" / "processed" / "exception_status_registry.csv"
MANAGED_QUEUE = ROOT / "data" / "processed" / "port_call_exception_queue_managed.csv"
EVENT_LOG = ROOT / "data" / "processed" / "exception_status_history.csv"

ISSUES_FILE = ROOT / "data" / "processed" / "exception_status_validation_issues.csv"
REPORT_FILE = ROOT / "outputs" / "reports" / "exception_status_validation.txt"

VALID_STATUSES = {"Open", "In Progress", "Resolved", "Closed"}

REGISTRY_COLUMNS = {
    "exception_id",
    "queue_status",
    "created_at_utc",
    "updated_at_utc",
    "last_seen_at_utc",
    "present_in_source",
}

HISTORY_COLUMNS = {
    "event_timestamp_utc",
    "exception_id",
    "event_type",
    "previous_status",
    "new_status",
    "details",
}


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return pd.read_csv(path, dtype={"exception_id": "string"})


def add_issue(issues, check, details):
    issues.append({
        "check": check,
        "details": str(details),
    })


def validate_status_values(data, column, label, issues):
    if column not in data.columns:
        add_issue(issues, f"{label}_STATUS_COLUMN", f"Missing column: {column}")
        return

    statuses = data[column].fillna("").astype(str).str.strip()
    invalid = sorted(set(statuses) - VALID_STATUSES - {""})

    if invalid:
        add_issue(
            issues,
            f"{label}_INVALID_STATUSES",
            f"Invalid status values: {', '.join(invalid)}",
        )

    if statuses.eq("").any():
        add_issue(
            issues,
            f"{label}_EMPTY_STATUSES",
            f"{int(statuses.eq('').sum())} rows have an empty status.",
        )


def validate():
    issues = []
    results = []

    registry = read_csv(REGISTRY)
    queue = read_csv(MANAGED_QUEUE)
    history = read_csv(EVENT_LOG)

    missing_registry = REGISTRY_COLUMNS - set(registry.columns)
    missing_history = HISTORY_COLUMNS - set(history.columns)

    if missing_registry:
        raise ValueError(
            "Registry is missing required columns: "
            + ", ".join(sorted(missing_registry))
        )

    if missing_history:
        raise ValueError(
            "History file is missing required columns: "
            + ", ".join(sorted(missing_history))
        )

    if "exception_id" not in queue.columns:
        raise ValueError("Managed queue is missing the exception_id column.")

    registry_ids = registry["exception_id"].fillna("").astype(str).str.strip()
    queue_ids = queue["exception_id"].fillna("").astype(str).str.strip()

    if registry_ids.eq("").any():
        add_issue(
            issues,
            "REGISTRY_EMPTY_IDS",
            f"{int(registry_ids.eq('').sum())} registry rows have empty exception IDs.",
        )

    if queue_ids.eq("").any():
        add_issue(
            issues,
            "QUEUE_EMPTY_IDS",
            f"{int(queue_ids.eq('').sum())} managed queue rows have empty exception IDs.",
        )

    duplicate_registry = registry_ids[registry_ids.duplicated(keep=False)]
    if not duplicate_registry.empty:
        add_issue(
            issues,
            "DUPLICATE_REGISTRY_IDS",
            "Duplicate IDs: " + ", ".join(sorted(set(duplicate_registry))),
        )

    duplicate_queue = queue_ids[queue_ids.duplicated(keep=False)]
    if not duplicate_queue.empty:
        add_issue(
            issues,
            "DUPLICATE_QUEUE_IDS",
            "Duplicate IDs: " + ", ".join(sorted(set(duplicate_queue))),
        )

    validate_status_values(registry, "queue_status", "REGISTRY", issues)
    validate_status_values(queue, "queue_status", "QUEUE", issues)

    registry_lookup = registry.drop_duplicates(
        subset=["exception_id"], keep="last"
    ).set_index("exception_id")["queue_status"]

    queue_lookup = queue.drop_duplicates(
        subset=["exception_id"], keep="last"
    ).set_index("exception_id")["queue_status"]

    missing_registry_ids = sorted(
        set(queue_ids) - {value for value in registry_ids if value}
    )

    if missing_registry_ids:
        add_issue(
            issues,
            "QUEUE_IDS_NOT_IN_REGISTRY",
            "Queue IDs missing from registry: "
            + ", ".join(missing_registry_ids),
        )

    mismatches = []

    for exception_id in set(queue_ids) & set(registry_ids):
        if not exception_id:
            continue

        registry_status = registry_lookup.get(exception_id)
        queue_status = queue_lookup.get(exception_id)

        if pd.isna(registry_status) or pd.isna(queue_status):
            continue

        if str(registry_status).strip() != str(queue_status).strip():
            mismatches.append(
                f"{exception_id}: registry={registry_status}, queue={queue_status}"
            )

    if mismatches:
        add_issue(
            issues,
            "STATUS_MISMATCH",
            "; ".join(sorted(mismatches)),
        )

    history_ids = history["exception_id"].fillna("").astype(str).str.strip()

    if history_ids.eq("").any():
        add_issue(
            issues,
            "HISTORY_EMPTY_IDS",
            f"{int(history_ids.eq('').sum())} history rows have empty exception IDs.",
        )

    timestamps = pd.to_datetime(
        history["event_timestamp_utc"],
        errors="coerce",
        utc=True,
    )

    invalid_timestamps = int(timestamps.isna().sum())

    if invalid_timestamps:
        add_issue(
            issues,
            "HISTORY_INVALID_TIMESTAMPS",
            f"{invalid_timestamps} history rows have missing or invalid timestamps.",
        )

    for column in ["previous_status", "new_status"]:
        values = history[column].fillna("").astype(str).str.strip()
        invalid = sorted(set(values) - VALID_STATUSES - {""})

        if invalid:
            add_issue(
                issues,
                f"HISTORY_INVALID_{column.upper()}",
                f"Invalid values in {column}: {', '.join(invalid)}",
            )

    present_values = (
        registry["present_in_source"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    absent_count = int(present_values.isin({"false", "0", "no"}).sum())

    status_counts = (
        registry["queue_status"]
        .fillna("Missing")
        .astype(str)
        .value_counts()
        .to_dict()
    )

    results.append(f"Registry rows: {len(registry)}")
    results.append(f"Managed queue rows: {len(queue)}")
    results.append(f"History events: {len(history)}")
    results.append(f"Registry exceptions absent from latest source: {absent_count}")
    results.append("Registry status counts:")

    if status_counts:
        for status, count in sorted(status_counts.items()):
            results.append(f"  {status}: {count}")
    else:
        results.append("  No status records found.")

    results.append("")
    results.append(f"Validation issues: {len(issues)}")

    if issues:
        for issue in issues:
            results.append(f"  {issue['check']}: {issue['details']}")
    else:
        results.append("All validation checks passed.")

    ISSUES_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        issues,
        columns=["check", "details"],
    ).to_csv(ISSUES_FILE, index=False)

    REPORT_FILE.write_text("\n".join(results) + "\n", encoding="utf-8")

    print("\n".join(results))
    print(f"\nIssue file: {ISSUES_FILE}")
    print(f"Report file: {REPORT_FILE}")

    return len(issues)


if __name__ == "__main__":
    try:
        issue_count = validate()
        raise SystemExit(1 if issue_count else 0)
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as error:
        print(f"Validation could not complete: {error}")
        raise SystemExit(1)
