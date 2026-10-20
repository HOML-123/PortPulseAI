
from pathlib import Path
from itertools import combinations
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "data" / "demo" / "port_call_milestones_demo.csv"
RESULTS = ROOT / "data" / "processed" / "port_call_coordination_results.csv"
CONFLICTS = ROOT / "data" / "processed" / "berth_conflict_pairs.csv"
REPORT = ROOT / "outputs" / "reports" / "port_call_coordination_summary.txt"

TIMESTAMP_COLUMNS = [
    "estimated_arrival",
    "actual_arrival",
    "estimated_berthing",
    "actual_berthing",
    "estimated_departure",
    "actual_departure",
]

DELAY_THRESHOLD_HOURS = 2


def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT}\n"
            "Run: python src\\create_port_call_demo_data.py"
        )

    df = pd.read_csv(INPUT)

    required_columns = [
        "port_call_id",
        "vessel_name",
        "berth",
        "call_status",
        *TIMESTAMP_COLUMNS,
    ]

    missing_columns = [
        column for column in required_columns if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Required columns are missing: {missing_columns}"
        )

    for column in TIMESTAMP_COLUMNS:
        df[column] = pd.to_datetime(df[column], errors="coerce")

    now = pd.Timestamp.now()
    df["coordination_flags"] = ""
    df["recommended_action"] = ""
    df["arrival_delay_hours"] = (
        df["actual_arrival"] - df["estimated_arrival"]
    ).dt.total_seconds() / 3600
    df["berthing_delay_hours"] = (
        df["actual_berthing"] - df["estimated_berthing"]
    ).dt.total_seconds() / 3600
    df["departure_delay_hours"] = (
        df["actual_departure"] - df["estimated_departure"]
    ).dt.total_seconds() / 3600

    flags_by_call = {
        call_id: [] for call_id in df["port_call_id"].astype(str)
    }
    actions_by_call = {
        call_id: [] for call_id in df["port_call_id"].astype(str)
    }

    def add_flag(call_id, flag, action):
        flags_by_call[call_id].append(flag)
        actions_by_call[call_id].append(action)

    for _, row in df.iterrows():
        call_id = str(row["port_call_id"])

        delay_fields = [
            ("arrival_delay_hours", "Arrival Delay"),
            ("berthing_delay_hours", "Berthing Delay"),
            ("departure_delay_hours", "Departure Delay"),
        ]

        for delay_column, flag in delay_fields:
            delay = row[delay_column]
            if pd.notna(delay) and delay > DELAY_THRESHOLD_HOURS:
                add_flag(
                    call_id,
                    flag,
                    f"Review {flag.lower()} of {delay:.1f} hours",
                )

        overdue_milestones = [
            ("estimated_arrival", "actual_arrival", "Arrival"),
            ("estimated_berthing", "actual_berthing", "Berthing"),
            ("estimated_departure", "actual_departure", "Departure"),
        ]

        for estimate_column, actual_column, milestone in overdue_milestones:
            estimated_time = row[estimate_column]
            actual_time = row[actual_column]

            if (
                pd.isna(actual_time)
                and pd.notna(estimated_time)
                and estimated_time < now
            ):
                add_flag(
                    call_id,
                    f"Overdue {milestone}",
                    f"Verify missing actual {milestone.lower()} milestone",
                )

    conflict_rows = []
    windows = []

    for _, row in df.iterrows():
        start = (
            row["actual_berthing"]
            if pd.notna(row["actual_berthing"])
            else row["estimated_berthing"]
        )
        end = (
            row["actual_departure"]
            if pd.notna(row["actual_departure"])
            else row["estimated_departure"]
        )

        if pd.notna(start) and pd.notna(end) and end > start:
                        windows.append({
                "port_call_id": str(row["port_call_id"]),
                "vessel_name": row["vessel_name"],
                "berth": row["berth"],
                "window_start": start,
                "window_end": end,
                "window_basis": (
                    "Actual times"
                    if pd.notna(row["actual_berthing"])
                    and pd.notna(row["actual_departure"])
                    else "Estimated or mixed times"
                ),
            })

    for first, second in combinations(windows, 2):
        if (
            pd.notna(first["berth"])
            and first["berth"] == second["berth"]
            and first["window_start"] < second["window_end"]
            and second["window_start"] < first["window_end"]
        ):
            overlap_start = max(
                first["window_start"], second["window_start"]
            )
            overlap_end = min(
                first["window_end"], second["window_end"]
            )
            overlap_hours = (
                overlap_end - overlap_start
            ).total_seconds() / 3600

            conflict_rows.append({
                "port_call_id_1": first["port_call_id"],
                "vessel_1": first["vessel_name"],
                "port_call_id_2": second["port_call_id"],
                "vessel_2": second["vessel_name"],
                "berth": first["berth"],
                "overlap_start": overlap_start,
                "overlap_end": overlap_end,
                "overlap_hours": round(overlap_hours, 2),
                "window_basis_1": first["window_basis"],
                "window_basis_2": second["window_basis"],
            })

            for call_id in (
                first["port_call_id"],
                second["port_call_id"],
            ):
                add_flag(
                    call_id,
                    "Berth Window Conflict",
                    "Coordinate berth allocation and verify both time windows",
                )

    for _, row in df.iterrows():
        call_id = str(row["port_call_id"])

        if not flags_by_call[call_id]:
            if row["call_status"] == "Completed":
                add_flag(
                    call_id,
                    "No Delay Flag",
                    "No delay above the configured threshold was detected",
                )
            else:
                add_flag(
                    call_id,
                    "Awaiting Actuals",
                    "Monitor upcoming milestones and update actual times",
                )

        df.loc[
            df["port_call_id"].astype(str) == call_id,
            "coordination_flags",
        ] = "; ".join(dict.fromkeys(flags_by_call[call_id]))

        df.loc[
            df["port_call_id"].astype(str) == call_id,
            "recommended_action",
        ] = "; ".join(dict.fromkeys(actions_by_call[call_id]))

    df["coordination_priority"] = df["coordination_flags"].apply(
        lambda value: (
            "High"
            if any(
                flag in value
                for flag in [
                    "Berth Window Conflict",
                    "Overdue Arrival",
                    "Overdue Berthing",
                ]
            )
            else (
                "Medium"
                if any(
                    flag in value
                    for flag in [
                        "Arrival Delay",
                        "Berthing Delay",
                        "Departure Delay",
                        "Overdue Departure",
                    ]
                )
                else "Low"
            )
        )
    )

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    df["_priority_order"] = df["coordination_priority"].map(priority_order)
    df = df.sort_values(
        ["_priority_order", "estimated_arrival"],
        na_position="last",
    ).drop(columns=["_priority_order"])

    conflict_df = pd.DataFrame(
        conflict_rows,
        columns=[
            "port_call_id_1",
            "vessel_1",
            "port_call_id_2",
            "vessel_2",
            "berth",
            "overlap_start",
            "overlap_end",
            "overlap_hours",
            "window_basis_1",
            "window_basis_2",
        ],
    )

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    CONFLICTS.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(RESULTS, index=False)
    conflict_df.to_csv(CONFLICTS, index=False)

    flagged_count = int(
        df["coordination_flags"].apply(
            lambda value: value != "No Delay Flag"
            and value != "Awaiting Actuals"
        ).sum()
    )
    high_count = int((df["coordination_priority"] == "High").sum())
    medium_count = int((df["coordination_priority"] == "Medium").sum())
    low_count = int((df["coordination_priority"] == "Low").sum())

    report_lines = [
        "PORTPULSE AI - PORT-CALL COORDINATION SUMMARY",
        "=" * 48,
        f"Generated at: {now}",
        f"Input records: {len(df)}",
        f"Calls with coordination flags: {flagged_count}",
        f"High-priority calls: {high_count}",
        f"Medium-priority calls: {medium_count}",
        f"Low-priority calls: {low_count}",
        f"Berth conflict pairs detected: {len(conflict_df)}",
        f"Delay threshold: more than {DELAY_THRESHOLD_HOURS} hours",
        "",
        "FLAG COUNTS",
        "-" * 48,
    ]

    all_flags = [
        flag
        for value in df["coordination_flags"]
        for flag in value.split("; ")
    ]

    for flag, count in pd.Series(all_flags).value_counts().items():
        report_lines.append(f"{flag}: {count}")

    report_lines.extend([
        "",
        "DATA LIMITATIONS",
        "-" * 48,
        "The input port-call dataset is synthetic demonstration data.",
        "Berth conflicts are based on overlapping actual/estimated windows.",
        "A conflict is a review flag, not proof of an operational conflict.",
        "Overdue checks use the computer's current local time.",
        "Delay thresholds are configurable business rules, not port policy.",
        "",
        f"Results CSV: {RESULTS}",
        f"Conflict pairs CSV: {CONFLICTS}",
    ])

    REPORT.write_text("\n".join(report_lines), encoding="utf-8")

    print("Port-call coordination analysis completed.")
    print(f"Port calls processed: {len(df)}")
    print(f"Calls with coordination flags: {flagged_count}")
    print(f"High-priority calls: {high_count}")
    print(f"Berth conflict pairs: {len(conflict_df)}")
    print(f"Results: {RESULTS}")
    print(f"Conflict pairs: {CONFLICTS}")
    print(f"Summary report: {REPORT}")


if __name__ == "__main__":
    main()
