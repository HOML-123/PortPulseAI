
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "data" / "processed" / "port_call_exception_queue.csv"
TYPE_OUTPUT = ROOT / "data" / "processed" / "exception_type_summary.csv"
TEAM_OUTPUT = ROOT / "data" / "processed" / "exception_team_summary.csv"
PRIORITY_OUTPUT = ROOT / "data" / "processed" / "exception_priority_summary.csv"
REPORT = ROOT / "outputs" / "reports" / "exception_queue_analytics.txt"

PRIORITY_ORDER = ["High", "Medium", "Low"]


def load_queue():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Exception queue not found: {INPUT}. "
            "Run src/port_call_exception_management.py first."
        )

    data = pd.read_csv(INPUT)

    required = {
        "exception_id",
        "exception_type",
        "coordination_priority",
        "responsible_team",
        "queue_status",
    }

    missing = required.difference(data.columns)

    if missing:
        raise ValueError(
            "Exception queue is missing required columns: "
            + ", ".join(sorted(missing))
        )

    return data


def summarize_by_type(data):
    result = (
        data.groupby("exception_type", dropna=False)
        .agg(
            total_exceptions=("exception_id", "count"),
            high_priority=(
                "coordination_priority",
                lambda values: values.eq("High").sum(),
            ),
            open_exceptions=(
                "queue_status",
                lambda values: values.eq("Open").sum(),
            ),
        )
        .reset_index()
    )

    return result.sort_values(
        ["total_exceptions", "exception_type"],
        ascending=[False, True],
    ).reset_index(drop=True)


def summarize_by_team(data):
    result = (
        data.groupby("responsible_team", dropna=False)
        .agg(
            total_exceptions=("exception_id", "count"),
            high_priority=(
                "coordination_priority",
                lambda values: values.eq("High").sum(),
            ),
            open_exceptions=(
                "queue_status",
                lambda values: values.eq("Open").sum(),
            ),
        )
        .reset_index()
    )

    return result.sort_values(
        ["total_exceptions", "responsible_team"],
        ascending=[False, True],
    ).reset_index(drop=True)


def summarize_by_priority(data):
    result = (
        data.groupby("coordination_priority", dropna=False)
        .agg(
            total_exceptions=("exception_id", "count"),
            open_exceptions=(
                "queue_status",
                lambda values: values.eq("Open").sum(),
            ),
        )
        .reset_index()
    )

    result["_order"] = result["coordination_priority"].map(
        {priority: index for index, priority in enumerate(PRIORITY_ORDER)}
    ).fillna(len(PRIORITY_ORDER))

    result = result.sort_values(
        ["_order", "coordination_priority"]
    ).drop(columns="_order")

    return result.reset_index(drop=True)


def create_report(data, by_type, by_team, by_priority):
    total = len(data)
    open_count = int(data["queue_status"].eq("Open").sum())
    high_count = int(
        data["coordination_priority"].eq("High").sum()
    )

    if total:
        top_type = str(by_type.iloc[0]["exception_type"])
        top_type_count = int(by_type.iloc[0]["total_exceptions"])

        top_team = str(by_team.iloc[0]["responsible_team"])
        top_team_count = int(by_team.iloc[0]["total_exceptions"])
    else:
        top_type = "None"
        top_type_count = 0
        top_team = "None"
        top_team_count = 0

    lines = [
        "PORTPULSE AI - EXCEPTION QUEUE ANALYTICS",
        "",
        "OVERALL SUMMARY",
        f"Total exceptions: {total}",
        f"Open exceptions: {open_count}",
        f"High-priority exceptions: {high_count}",
        "",
        "MOST FREQUENT EXCEPTION TYPE",
        f"Type: {top_type}",
        f"Count: {top_type_count}",
        "",
        "TEAM WITH MOST ASSIGNED EXCEPTIONS",
        f"Suggested team: {top_team}",
        f"Count: {top_team_count}",
        "",
        "EXCEPTIONS BY TYPE",
        by_type.to_string(index=False),
        "",
        "EXCEPTIONS BY SUGGESTED TEAM",
        by_team.to_string(index=False),
        "",
        "EXCEPTIONS BY PRIORITY",
        by_priority.to_string(index=False),
        "",
        "INTERPRETATION LIMITATION",
        (
            "Counts describe the generated exception queue, not verified "
            "real-world incident rates or actual team capacity. Team "
            "assignments are rule-based suggestions. The same port call "
            "may contribute multiple exceptions."
        ),
    ]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    data = load_queue()

    by_type = summarize_by_type(data)
    by_team = summarize_by_team(data)
    by_priority = summarize_by_priority(data)

    TYPE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    by_type.to_csv(TYPE_OUTPUT, index=False)
    by_team.to_csv(TEAM_OUTPUT, index=False)
    by_priority.to_csv(PRIORITY_OUTPUT, index=False)

    create_report(data, by_type, by_team, by_priority)

    print(f"Exceptions analysed: {len(data)}")
    print(f"Exception type summary: {TYPE_OUTPUT}")
    print(f"Team workload summary: {TEAM_OUTPUT}")
    print(f"Priority summary: {PRIORITY_OUTPUT}")
    print(f"Analytics report: {REPORT}")


if __name__ == "__main__":
    main()
