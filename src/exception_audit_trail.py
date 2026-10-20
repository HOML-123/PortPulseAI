
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "data" / "processed" / "port_call_exception_queue.csv"
STATE_FILE = ROOT / "data" / "processed" / "exception_audit_state.csv"
EVENT_LOG = ROOT / "data" / "processed" / "exception_audit_log.csv"
REPORT = ROOT / "outputs" / "reports" / "exception_audit_summary.txt"

TRACKED_FIELDS = [
    "port_call_id",
    "vessel_name",
    "voyage_number",
    "berth",
    "exception_type",
    "exception_description",
    "coordination_priority",
    "last_known_milestone",
    "responsible_team",
    "recommended_action",
    "queue_status",
    "data_source",
]

STATE_COLUMNS = ["exception_id"] + TRACKED_FIELDS

EVENT_COLUMNS = [
    "event_timestamp_utc",
    "exception_id",
    "event_type",
    "changed_fields",
    "previous_values",
    "current_values",
]


def timestamp_now():
    return datetime.now(timezone.utc).isoformat()


def normalise_value(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def load_current_queue():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Exception queue not found: {INPUT}. "
            "Run src/port_call_exception_management.py first."
        )

    data = pd.read_csv(INPUT, dtype=str).fillna("")

    if "exception_id" not in data.columns:
        raise ValueError("The exception queue needs an exception_id column.")

    if data["exception_id"].eq("").any():
        raise ValueError("Every exception must have a non-empty exception_id.")

    if data["exception_id"].duplicated().any():
        raise ValueError(
            "Duplicate exception_id values were found. "
            "The audit trail requires unique exception identifiers."
        )

    for column in TRACKED_FIELDS:
        if column not in data.columns:
            data[column] = ""

    return data[STATE_COLUMNS].copy()


def load_previous_state():
    if not STATE_FILE.exists():
        return pd.DataFrame(columns=STATE_COLUMNS)

    previous = pd.read_csv(STATE_FILE, dtype=str).fillna("")

    for column in STATE_COLUMNS:
        if column not in previous.columns:
            previous[column] = ""

    if previous["exception_id"].duplicated().any():
        raise ValueError(
            "The saved audit state contains duplicate exception IDs."
        )

    return previous[STATE_COLUMNS].copy()


def compare_snapshots(previous, current):
    previous_map = {
        row["exception_id"]: row
        for _, row in previous.iterrows()
    }

    current_map = {
        row["exception_id"]: row
        for _, row in current.iterrows()
    }

    timestamp = timestamp_now()
    events = []

    for exception_id, current_row in current_map.items():
        if exception_id not in previous_map:
            events.append({
                "event_timestamp_utc": timestamp,
                "exception_id": exception_id,
                "event_type": "NEW_EXCEPTION",
                "changed_fields": "",
                "previous_values": "",
                "current_values": "",
            })
            continue

        previous_row = previous_map[exception_id]
        changed_fields = []
        previous_values = []
        current_values = []

        for field in TRACKED_FIELDS:
            old_value = normalise_value(previous_row[field])
            new_value = normalise_value(current_row[field])

            if old_value != new_value:
                changed_fields.append(field)
                previous_values.append(f"{field}={old_value}")
                current_values.append(f"{field}={new_value}")

        if changed_fields:
            events.append({
                "event_timestamp_utc": timestamp,
                "exception_id": exception_id,
                "event_type": "EXCEPTION_UPDATED",
                "changed_fields": " | ".join(changed_fields),
                "previous_values": " | ".join(previous_values),
                "current_values": " | ".join(current_values),
            })

    for exception_id in previous_map:
        if exception_id not in current_map:
            events.append({
                "event_timestamp_utc": timestamp,
                "exception_id": exception_id,
                "event_type": "MISSING_FROM_CURRENT_SNAPSHOT",
                "changed_fields": "",
                "previous_values": "",
                "current_values": "",
            })

    return pd.DataFrame(events, columns=EVENT_COLUMNS)


def append_event_log(events):
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)

    if events.empty:
        if not EVENT_LOG.exists():
            events.to_csv(EVENT_LOG, index=False)
        return

    write_header = not EVENT_LOG.exists()

    events.to_csv(
        EVENT_LOG,
        mode="a",
        header=write_header,
        index=False,
    )


def create_report(previous, current, events):
    if events.empty:
        event_counts = "No changes detected between snapshots."
    else:
        event_counts = events["event_type"].value_counts().to_string()

    lines = [
        "PORTPULSE AI - EXCEPTION AUDIT TRAIL",
        f"Snapshot timestamp UTC: {timestamp_now()}",
        "",
        "SNAPSHOT SUMMARY",
        f"Previous exception count: {len(previous)}",
        f"Current exception count: {len(current)}",
        f"Events recorded this run: {len(events)}",
        "",
        "EVENT TYPES",
        event_counts,
        "",
        "INTERPRETATION",
        (
            "MISSING_FROM_CURRENT_SNAPSHOT means an exception ID was present "
            "in the previous saved queue but is absent from the current queue. "
            "It does not prove that the exception was resolved. "
            "The comparison records observed snapshot differences only."
        ),
        "",
        f"Saved state: {STATE_FILE}",
        f"Append-only event log: {EVENT_LOG}",
    ]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    current = load_current_queue()
    previous = load_previous_state()

    events = compare_snapshots(previous, current)

    append_event_log(events)

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    current.to_csv(STATE_FILE, index=False)

    create_report(previous, current, events)

    print(f"Previous exceptions: {len(previous)}")
    print(f"Current exceptions: {len(current)}")
    print(f"Audit events this run: {len(events)}")
    print(f"Saved state: {STATE_FILE}")
    print(f"Audit log: {EVENT_LOG}")
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
