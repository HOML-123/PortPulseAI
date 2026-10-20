
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

HISTORY_FILE = ROOT / "data" / "processed" / "exception_status_history.csv"

DAILY_OUTPUT = ROOT / "data" / "processed" / "exception_history_daily_summary.csv"
EVENT_OUTPUT = ROOT / "data" / "processed" / "exception_history_event_summary.csv"
TRANSITION_OUTPUT = ROOT / "data" / "processed" / "exception_history_transition_summary.csv"
REPORT_FILE = ROOT / "outputs" / "reports" / "exception_workflow_history_analytics.txt"

REQUIRED_COLUMNS = {
    "event_timestamp_utc",
    "exception_id",
    "event_type",
    "previous_status",
    "new_status",
    "details",
}


def read_history():
    if not HISTORY_FILE.exists():
        raise FileNotFoundError(f"History file not found: {HISTORY_FILE}")

    history = pd.read_csv(
        HISTORY_FILE,
        dtype={"exception_id": "string"},
    )

    missing_columns = REQUIRED_COLUMNS - set(history.columns)

    if missing_columns:
        raise ValueError(
            "History file is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    history["event_timestamp_utc"] = pd.to_datetime(
        history["event_timestamp_utc"],
        errors="coerce",
        utc=True,
    )

    for column in [
        "exception_id",
        "event_type",
        "previous_status",
        "new_status",
    ]:
        history[column] = (
            history[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    return history


def build_daily_summary(history):
    valid = history.dropna(subset=["event_timestamp_utc"]).copy()

    if valid.empty:
        return pd.DataFrame(
            columns=[
                "event_date_utc",
                "total_events",
                "unique_exceptions",
                "status_changes",
                "registrations",
            ]
        )

    valid["event_date_utc"] = (
        valid["event_timestamp_utc"].dt.strftime("%Y-%m-%d")
    )

    valid["is_status_change"] = valid["event_type"].eq("STATUS_CHANGED")
    valid["is_registration"] = valid["event_type"].eq("EXCEPTION_REGISTERED")

    daily = (
        valid.groupby("event_date_utc", as_index=False)
        .agg(
            total_events=("event_type", "size"),
            unique_exceptions=("exception_id", lambda values: values[values.ne("")].nunique()),
            status_changes=("is_status_change", "sum"),
            registrations=("is_registration", "sum"),
        )
        .sort_values("event_date_utc")
        .reset_index(drop=True)
    )

    return daily


def build_event_summary(history):
    valid = history[history["event_type"].ne("")]

    if valid.empty:
        return pd.DataFrame(
            columns=["event_type", "event_count", "unique_exceptions"]
        )

    summary = (
        valid.groupby("event_type", as_index=False)
        .agg(
            event_count=("exception_id", "size"),
            unique_exceptions=("exception_id", lambda values: values[values.ne("")].nunique()),
        )
        .sort_values(
            ["event_count", "event_type"],
            ascending=[False, True],
        )
        .reset_index(drop=True)
    )

    return summary


def build_transition_summary(history):
    valid = history[
        history["event_type"].eq("STATUS_CHANGED")
        & history["previous_status"].ne("")
        & history["new_status"].ne("")
    ].copy()

    if valid.empty:
        return pd.DataFrame(
            columns=[
                "previous_status",
                "new_status",
                "transition_count",
                "unique_exceptions",
            ]
        )

    summary = (
        valid.groupby(
            ["previous_status", "new_status"],
            as_index=False,
        )
        .agg(
            transition_count=("exception_id", "size"),
            unique_exceptions=("exception_id", lambda values: values[values.ne("")].nunique()),
        )
        .sort_values(
            ["transition_count", "previous_status", "new_status"],
            ascending=[False, True, True],
        )
        .reset_index(drop=True)
    )

    return summary


def main():
    history = read_history()

    daily = build_daily_summary(history)
    event_summary = build_event_summary(history)
    transition_summary = build_transition_summary(history)

    invalid_timestamps = int(history["event_timestamp_utc"].isna().sum())
    missing_ids = int(history["exception_id"].eq("").sum())
    missing_event_types = int(history["event_type"].eq("").sum())

    unique_exceptions = int(
        history.loc[
            history["exception_id"].ne(""),
            "exception_id",
        ].nunique()
    )

    status_change_count = int(
        history["event_type"].eq("STATUS_CHANGED").sum()
    )

    registration_count = int(
        history["event_type"].eq("EXCEPTION_REGISTERED").sum()
    )

    DAILY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    EVENT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TRANSITION_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    daily.to_csv(DAILY_OUTPUT, index=False)
    event_summary.to_csv(EVENT_OUTPUT, index=False)
    transition_summary.to_csv(TRANSITION_OUTPUT, index=False)

    report_lines = [
        "PORTPULSEAI EXCEPTION WORKFLOW HISTORY ANALYTICS",
        "",
        "OVERALL COUNTS",
        f"Total history events: {len(history)}",
        f"Unique exceptions recorded in history: {unique_exceptions}",
        f"Registration events: {registration_count}",
        f"Status change events: {status_change_count}",
        f"Events with invalid timestamps: {invalid_timestamps}",
        f"Events with empty exception IDs: {missing_ids}",
        f"Events with empty event types: {missing_event_types}",
        "",
        "EVENT TYPE SUMMARY",
    ]

    if event_summary.empty:
        report_lines.append("No event types available.")
    else:
        for _, row in event_summary.iterrows():
            report_lines.append(
                f"{row['event_type']}: {int(row['event_count'])} events, "
                f"{int(row['unique_exceptions'])} unique exceptions"
            )

    report_lines.extend(["", "STATUS TRANSITION SUMMARY"])

    if transition_summary.empty:
        report_lines.append("No complete status transitions available.")
    else:
        for _, row in transition_summary.iterrows():
            report_lines.append(
                f"{row['previous_status']} -> {row['new_status']}: "
                f"{int(row['transition_count'])} events"
            )

    report_lines.extend([
        "",
        "INTERPRETATION",
        "Daily counts use valid UTC event timestamps.",
        "Status transition counts include STATUS_CHANGED events with both statuses recorded.",
        "History events measure recorded system activity, not necessarily completed real-world work.",
        "An absent exception or a missing history event does not prove resolution.",
        "",
        "OUTPUT FILES",
        str(DAILY_OUTPUT),
        str(EVENT_OUTPUT),
        str(TRANSITION_OUTPUT),
        str(REPORT_FILE),
    ])

    REPORT_FILE.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print("\n".join(report_lines))
    print("\nAnalytics files generated successfully.")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as error:
        print(f"History analytics could not be generated: {error}")
        raise SystemExit(1)
