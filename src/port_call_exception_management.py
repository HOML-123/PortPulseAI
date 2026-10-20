
from pathlib import Path
from datetime import datetime, timezone
import hashlib

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "data" / "processed" / "port_call_coordination_results.csv"
OUTPUT = ROOT / "data" / "processed" / "port_call_exception_queue.csv"
SUMMARY = ROOT / "outputs" / "reports" / "port_call_exception_summary.txt"

MILESTONES = [
    ("Arrival", "actual_arrival"),
    ("Berthing", "actual_berthing"),
    ("Departure", "actual_departure"),
]

QUEUE_COLUMNS = [
    "exception_id",
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


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_flags(value):
    text = clean_text(value)

    if not text:
        return []

    for separator in ["|", ";", ","]:
        text = text.replace(separator, "|")

    flags = []
    seen = set()

    for part in text.split("|"):
        flag = part.strip()
        key = flag.casefold()

        if flag and key not in seen:
            flags.append(flag)
            seen.add(key)

    return flags


def create_exception_id(port_call_id, flag):
    stable_key = (
        clean_text(port_call_id).casefold()
        + "|"
        + clean_text(flag).casefold()
    )

    digest = hashlib.sha256(
        stable_key.encode("utf-8")
    ).hexdigest()[:16].upper()

    return f"EXC-{digest}"


def get_last_known_milestone(row):
    recorded = []

    for name, actual_column in MILESTONES:
        if actual_column not in row.index:
            continue

        timestamp = pd.to_datetime(
            row[actual_column],
            errors="coerce",
            utc=True,
        )

        if pd.notna(timestamp):
            recorded.append((timestamp, name))

    if not recorded:
        return "No actual milestone recorded"

    timestamp, milestone = max(
        recorded,
        key=lambda item: item[0],
    )

    return f"{milestone} recorded at {timestamp.isoformat()}"


def classify_exception(flag):
    text = flag.casefold()

    if "berth window conflict" in text:
        return {
            "exception_type": "Berth Conflict",
            "responsible_team": "Berth Planning",
            "recommended_action": (
                "Verify berth allocation, vessel time windows, "
                "and the latest confirmed schedule."
            ),
        }

    if "overdue arrival" in text or "arrival delay" in text:
        return {
            "exception_type": "Arrival Exception",
            "responsible_team": "Vessel Operations",
            "recommended_action": (
                "Verify the latest vessel arrival status and "
                "confirm the revised estimated arrival time."
            ),
        }

    if "overdue berthing" in text or "berthing delay" in text:
        return {
            "exception_type": "Berthing Exception",
            "responsible_team": "Vessel Operations",
            "recommended_action": (
                "Confirm the vessel's berthing status and check "
                "the latest berth allocation with the planning team."
            ),
        }

    if "overdue departure" in text or "departure delay" in text:
        return {
            "exception_type": "Departure Exception",
            "responsible_team": "Vessel Operations",
            "recommended_action": (
                "Verify departure readiness and obtain a confirmed "
                "departure time from the relevant operations team."
            ),
        }

    return {
        "exception_type": "Schedule Exception",
        "responsible_team": "Port Coordination",
        "recommended_action": (
            "Verify the exception against the latest confirmed "
            "port-call schedule and assign an accountable team."
        ),
    }


def build_exception_queue(data):
    exceptions = []

    for _, row in data.iterrows():
        port_call_id = clean_text(row.get("port_call_id", ""))

        if not port_call_id:
            raise ValueError(
                "Every port call must have a non-empty port_call_id."
            )

        flags = parse_flags(row.get("coordination_flags", ""))

        for flag in flags:
            details = classify_exception(flag)

            exceptions.append({
                "exception_id": create_exception_id(
                    port_call_id,
                    flag,
                ),
                "port_call_id": port_call_id,
                "vessel_name": clean_text(
                    row.get("vessel_name", "")
                ),
                "voyage_number": clean_text(
                    row.get("voyage_number", "")
                ),
                "berth": clean_text(row.get("berth", "")),
                "exception_type": details["exception_type"],
                "exception_description": flag,
                "coordination_priority": clean_text(
                    row.get("coordination_priority", "Medium")
                ),
                "last_known_milestone": get_last_known_milestone(row),
                "responsible_team": details["responsible_team"],
                "recommended_action": details["recommended_action"],
                "queue_status": "Open",
                "data_source": clean_text(
                    row.get("data_source", "SOURCE_NOT_SPECIFIED")
                ),
            })

    queue = pd.DataFrame(exceptions, columns=QUEUE_COLUMNS)

    if queue["exception_id"].duplicated().any():
        raise ValueError(
            "Duplicate exception IDs were generated. "
            "Check for repeated port-call records and flags."
        )

    if not queue.empty:
        priority_order = {
            "High": 0,
            "Medium": 1,
            "Low": 2,
        }

        queue["_priority_order"] = (
            queue["coordination_priority"]
            .map(priority_order)
            .fillna(3)
        )

        queue = queue.sort_values(
            [
                "_priority_order",
                "port_call_id",
                "exception_type",
                "exception_id",
            ]
        ).drop(columns="_priority_order")

        queue = queue.reset_index(drop=True)

    return queue


def create_summary(queue):
    total = len(queue)

    if queue.empty:
        high = 0
        medium = 0
        low = 0
        open_count = 0
        type_summary = "No exceptions were identified."
        team_summary = "No team assignments were generated."
    else:
        high = int(
            queue["coordination_priority"].eq("High").sum()
        )
        medium = int(
            queue["coordination_priority"].eq("Medium").sum()
        )
        low = int(
            queue["coordination_priority"].eq("Low").sum()
        )
        open_count = int(queue["queue_status"].eq("Open").sum())

        type_summary = queue[
            "exception_type"
        ].value_counts().to_string()

        team_summary = queue[
            "responsible_team"
        ].value_counts().to_string()

    lines = [
        "PORTPULSE AI - PORT CALL EXCEPTION MANAGEMENT",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "QUEUE SUMMARY",
        f"Total exceptions: {total}",
        f"Open exceptions: {open_count}",
        f"High priority: {high}",
        f"Medium priority: {medium}",
        f"Low priority: {low}",
        "",
        "EXCEPTIONS BY TYPE",
        type_summary,
        "",
        "SUGGESTED TEAM ASSIGNMENTS",
        team_summary,
        "",
        "IDENTIFIER POLICY",
        (
            "Exception IDs are generated deterministically from the "
            "port-call ID and exception description. Repeated runs "
            "produce the same ID when those values remain unchanged."
        ),
        "",
        "DATA LIMITATION",
        (
            "Team assignments are rule-based suggestions. The queue "
            "does not independently verify live operational status."
        ),
        "",
        f"Output file: {OUTPUT}",
    ]

    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")


def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Coordination results were not found: {INPUT}. "
            "Run src/port_call_coordination.py first."
        )

    data = pd.read_csv(INPUT)

    required = {
        "port_call_id",
        "coordination_flags",
        "coordination_priority",
    }

    missing = required.difference(data.columns)

    if missing:
        raise ValueError(
            "Coordination results are missing required columns: "
            + ", ".join(sorted(missing))
        )

    queue = build_exception_queue(data)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(OUTPUT, index=False)

    create_summary(queue)

    print(f"Port calls analysed: {len(data)}")
    print(f"Exceptions created: {len(queue)}")
    print(f"Unique exception IDs: {queue['exception_id'].nunique()}")
    print(f"Exception queue saved: {OUTPUT}")
    print(f"Summary saved: {SUMMARY}")


if __name__ == "__main__":
    main()
