
from pathlib import Path
from datetime import datetime, timezone
import argparse

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "data" / "processed" / "port_call_exception_queue.csv"
REGISTRY = ROOT / "data" / "processed" / "exception_status_registry.csv"
MANAGED_OUTPUT = ROOT / "data" / "processed" / "port_call_exception_queue_managed.csv"
EVENT_LOG = ROOT / "data" / "processed" / "exception_status_history.csv"
REPORT = ROOT / "outputs" / "reports" / "exception_status_summary.txt"

VALID_STATUSES = ["Open", "In Progress", "Resolved", "Closed"]

REGISTRY_COLUMNS = [
    "exception_id",
    "queue_status",
    "created_at_utc",
    "updated_at_utc",
    "last_seen_at_utc",
    "present_in_source",
]

EVENT_COLUMNS = [
    "event_timestamp_utc",
    "exception_id",
    "event_type",
    "previous_status",
    "new_status",
    "details",
]


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def load_source_queue():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Exception queue not found: {INPUT}. "
            "Run src/port_call_exception_management.py first."
        )

    data = pd.read_csv(INPUT, dtype=str).fillna("")

    if "exception_id" not in data.columns:
        raise ValueError("The source queue needs an exception_id column.")

    if data["exception_id"].eq("").any():
        raise ValueError("Every exception must have an ID.")

    if data["exception_id"].duplicated().any():
        raise ValueError("The source queue contains duplicate exception IDs.")

    return data


def load_registry():
    if not REGISTRY.exists():
        return pd.DataFrame(columns=REGISTRY_COLUMNS)

    data = pd.read_csv(REGISTRY, dtype=str).fillna("")

    for column in REGISTRY_COLUMNS:
        if column not in data.columns:
            data[column] = ""

    if data["exception_id"].duplicated().any():
        raise ValueError("The status registry contains duplicate exception IDs.")

    invalid = ~data["queue_status"].isin(VALID_STATUSES)

    if invalid.any():
        raise ValueError("The status registry contains an invalid status.")

    return data[REGISTRY_COLUMNS].copy()


def append_events(events):
    if not events:
        return

    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(events, columns=EVENT_COLUMNS)

    frame.to_csv(
        EVENT_LOG,
        mode="a",
        header=not EVENT_LOG.exists(),
        index=False,
    )


def sync_queue():
    source = load_source_queue()
    registry = load_registry()

    registry_map = {
        row["exception_id"]: row.to_dict()
        for _, row in registry.iterrows()
    }

    timestamp = now_utc()
    events = []

    for _, source_row in source.iterrows():
        exception_id = source_row["exception_id"]

        if exception_id not in registry_map:
            record = {
                "exception_id": exception_id,
                "queue_status": "Open",
                "created_at_utc": timestamp,
                "updated_at_utc": timestamp,
                "last_seen_at_utc": timestamp,
                "present_in_source": "True",
            }

            registry_map[exception_id] = record

            events.append({
                "event_timestamp_utc": timestamp,
                "exception_id": exception_id,
                "event_type": "EXCEPTION_REGISTERED",
                "previous_status": "",
                "new_status": "Open",
                "details": "New exception registered in status tracking.",
            })

        else:
            record = registry_map[exception_id]

            if record["present_in_source"] != "True":
                events.append({
                    "event_timestamp_utc": timestamp,
                    "exception_id": exception_id,
                    "event_type": "EXCEPTION_RETURNED",
                    "previous_status": record["queue_status"],
                    "new_status": record["queue_status"],
                    "details": (
                        "Exception ID reappeared in the source queue. "
                        "Its saved workflow status was preserved."
                    ),
                })

            record["last_seen_at_utc"] = timestamp
            record["present_in_source"] = "True"

    current_ids = set(source["exception_id"])

    for exception_id, record in registry_map.items():
        if exception_id not in current_ids and record["present_in_source"] == "True":
            record["present_in_source"] = "False"

            events.append({
                "event_timestamp_utc": timestamp,
                "exception_id": exception_id,
                "event_type": "EXCEPTION_MISSING_FROM_SOURCE",
                "previous_status": record["queue_status"],
                "new_status": record["queue_status"],
                "details": (
                    "Exception is absent from the current source snapshot. "
                    "It has not been automatically resolved or closed."
                ),
            })

    updated_registry = pd.DataFrame(
        list(registry_map.values()),
        columns=REGISTRY_COLUMNS,
    )

    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    updated_registry.to_csv(REGISTRY, index=False)

    append_events(events)

    status_map = dict(
        zip(
            updated_registry["exception_id"],
            updated_registry["queue_status"],
        )
    )

    managed = source.copy()
    managed["queue_status"] = managed["exception_id"].map(status_map)

    managed.to_csv(MANAGED_OUTPUT, index=False)

    counts = managed["queue_status"].value_counts().to_dict()

    lines = [
        "PORTPULSE AI - EXCEPTION STATUS SUMMARY",
        f"Generated at UTC: {timestamp}",
        "",
        f"Current source exceptions: {len(source)}",
        f"Tracked exception IDs: {len(updated_registry)}",
        f"Events generated during this sync: {len(events)}",
        "",
        "CURRENT QUEUE STATUS COUNTS",
    ]

    for status in VALID_STATUSES:
        lines.append(f"{status}: {counts.get(status, 0)}")

    lines.extend([
        "",
        "IMPORTANT",
        (
            "An exception missing from the current source queue is not "
            "automatically resolved. Workflow status is preserved in the "
            "registry until a user changes it."
        ),
        "",
        f"Registry: {REGISTRY}",
        f"Managed queue: {MANAGED_OUTPUT}",
        f"Event history: {EVENT_LOG}",
    ])

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Source exceptions: {len(source)}")
    print(f"Tracked exception IDs: {len(updated_registry)}")
    print(f"Events generated: {len(events)}")
    print(f"Managed queue saved: {MANAGED_OUTPUT}")
    print(f"Status registry saved: {REGISTRY}")
    print(f"History saved: {EVENT_LOG}")
    print(f"Report saved: {REPORT}")


def update_status(exception_id, new_status):
    if new_status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status: {new_status}. "
            f"Choose from: {', '.join(VALID_STATUSES)}"
        )

    sync_queue()

    registry = load_registry()
    matches = registry["exception_id"] == exception_id

    if not matches.any():
        raise ValueError(
            f"Exception ID not found in the tracked registry: {exception_id}"
        )

    index = registry.index[matches][0]
    old_status = registry.at[index, "queue_status"]

    if old_status == new_status:
        print(f"Status is already {new_status}. No change made.")
        return

    timestamp = now_utc()

    registry.at[index, "queue_status"] = new_status
    registry.at[index, "updated_at_utc"] = timestamp

    registry.to_csv(REGISTRY, index=False)

    append_events([{
        "event_timestamp_utc": timestamp,
        "exception_id": exception_id,
        "event_type": "STATUS_CHANGED",
        "previous_status": old_status,
        "new_status": new_status,
        "details": "Workflow status changed by an explicit user command.",
    }])

    source = load_source_queue()
    status_map = dict(
        zip(registry["exception_id"], registry["queue_status"])
    )

    managed = source.copy()
    managed["queue_status"] = managed["exception_id"].map(status_map)
    managed.to_csv(MANAGED_OUTPUT, index=False)

    print(f"Exception ID: {exception_id}")
    print(f"Previous status: {old_status}")
    print(f"New status: {new_status}")
    print(f"Managed queue updated: {MANAGED_OUTPUT}")


def main():
    parser = argparse.ArgumentParser(
        description="Synchronise and manage PortPulse AI exception statuses."
    )

    parser.add_argument(
        "action",
        nargs="?",
        choices=["sync", "update"],
        default="sync",
    )
    parser.add_argument("exception_id", nargs="?")
    parser.add_argument("status", nargs="?")

    args = parser.parse_args()

    if args.action == "sync":
        sync_queue()
        return

    if not args.exception_id or not args.status:
        parser.error(
            "For update, provide an exception ID and a status."
        )

    update_status(args.exception_id, args.status)


if __name__ == "__main__":
    main()
