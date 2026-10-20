
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "data" / "processed" / "port_call_exception_queue.csv"
FILTERED_OUTPUT = ROOT / "data" / "processed" / "exception_queue_prioritised.csv"
HIGH_PRIORITY_OUTPUT = ROOT / "data" / "processed" / "high_priority_open_exceptions.csv"
REPORT = ROOT / "outputs" / "reports" / "exception_queue_prioritisation.txt"

PRIORITY_RANK = {
    "High": 1,
    "Medium": 2,
    "Low": 3,
}


def load_queue():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Exception queue not found: {INPUT}. "
            "Run src/port_call_exception_management.py first."
        )

    data = pd.read_csv(INPUT)

    required = {
        "exception_id",
        "port_call_id",
        "exception_type",
        "coordination_priority",
        "responsible_team",
        "queue_status",
    }

    missing = required.difference(data.columns)

    if missing:
        raise ValueError(
            "Required columns are missing: "
            + ", ".join(sorted(missing))
        )

    return data


def apply_filters(data, exception_type=None, team=None, status=None):
    filtered = data.copy()

    if exception_type:
        filtered = filtered[
            filtered["exception_type"].astype(str).str.casefold()
            == exception_type.casefold()
        ]

    if team:
        filtered = filtered[
            filtered["responsible_team"].astype(str).str.casefold()
            == team.casefold()
        ]

    if status:
        filtered = filtered[
            filtered["queue_status"].astype(str).str.casefold()
            == status.casefold()
        ]

    return filtered.copy()


def prioritise_queue(data):
    result = data.copy()

    result["_priority_rank"] = (
        result["coordination_priority"]
        .map(PRIORITY_RANK)
        .fillna(99)
    )

    sort_columns = ["_priority_rank"]

    if "port_call_id" in result.columns:
        sort_columns.append("port_call_id")

    if "exception_type" in result.columns:
        sort_columns.append("exception_type")

    result = result.sort_values(
        sort_columns,
        ascending=True,
        na_position="last",
    )

    return result.drop(columns="_priority_rank").reset_index(drop=True)


def create_report(data, prioritised, high_priority_open):
    total = len(data)
    open_count = int(
        data["queue_status"].astype(str).str.casefold().eq("open").sum()
    )
    high_count = int(
        data["coordination_priority"].astype(str).str.casefold().eq("high").sum()
    )

    lines = [
        "PORTPULSE AI - EXCEPTION QUEUE PRIORITISATION",
        "",
        "QUEUE OVERVIEW",
        f"Total exceptions: {total}",
        f"Open exceptions: {open_count}",
        f"High-priority exceptions: {high_count}",
        "",
        "PRIORITISED QUEUE",
        prioritised.head(20).to_string(index=False),
        "",
        "HIGH-PRIORITY OPEN EXCEPTIONS",
        f"Count: {len(high_priority_open)}",
        high_priority_open.to_string(index=False),
        "",
        "INTERPRETATION LIMITATION",
        (
            "Priority ordering uses the existing rule-based priority field. "
            "It does not establish real-time urgency, verified ownership, "
            "or actual operational impact. Confirm each exception against "
            "current port-call information."
        ),
    ]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    data = load_queue()

    prioritised = prioritise_queue(data)

    high_priority_open = apply_filters(
        prioritised,
        status="Open",
    )

    high_priority_open = high_priority_open[
        high_priority_open["coordination_priority"]
        .astype(str)
        .str.casefold()
        .eq("high")
    ].copy()

    FILTERED_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    prioritised.to_csv(FILTERED_OUTPUT, index=False)
    high_priority_open.to_csv(HIGH_PRIORITY_OUTPUT, index=False)

    create_report(data, prioritised, high_priority_open)

    print(f"Total exceptions: {len(data)}")
    print(f"Prioritised queue saved: {FILTERED_OUTPUT}")
    print(f"High-priority open exceptions: {len(high_priority_open)}")
    print(f"High-priority file saved: {HIGH_PRIORITY_OUTPUT}")
    print(f"Report saved: {REPORT}")


if __name__ == "__main__":
    main()
