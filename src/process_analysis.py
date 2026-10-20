
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EVENTS_FILE = ROOT / "data" / "processed" / "valid_events.csv.gz"
FEATURES_FILE = ROOT / "data" / "processed" / "container_features.csv.gz"
OUTPUT_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "outputs" / "reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

MIN_EVENTS_FOR_CANDIDATE = 20


def main():
    if not EVENTS_FILE.exists():
        raise FileNotFoundError(
            f"Event file not found: {EVENTS_FILE}\n"
            "Run python src\\clean_data.py first."
        )

    if not FEATURES_FILE.exists():
        raise FileNotFoundError(
            f"Feature file not found: {FEATURES_FILE}\n"
            "Run python src\\feature_engineering.py first."
        )

    print("Loading event and case-level datasets...")

    df = pd.read_csv(
        EVENTS_FILE,
        compression="gzip",
        parse_dates=["Start Timestamp", "End Timestamp"]
    )

    features = pd.read_csv(
        FEATURES_FILE,
        compression="gzip",
        parse_dates=["case_start_timestamp", "case_end_timestamp"]
    )

    required = [
        "case_id",
        "activity",
        "Start Timestamp",
        "End Timestamp",
        "event_duration_seconds"
    ]

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Required event columns missing: {missing}")

    if "case_id" not in features.columns or "elapsed_hours" not in features.columns:
        raise ValueError(
            "The case-level feature file is missing required columns."
        )

    df["case_id"] = df["case_id"].astype("string")
    df["activity"] = df["activity"].astype("string")
    df["event_duration_seconds"] = pd.to_numeric(
        df["event_duration_seconds"],
        errors="coerce"
    )

    df = df.sort_values(
        ["case_id", "Start Timestamp", "End Timestamp"],
        kind="mergesort"
    ).reset_index(drop=True)

    print("Calculating activity duration statistics...")

    activity_duration = (
        df.groupby("activity", observed=True)
        .agg(
            event_count=("event_duration_seconds", "count"),
            median_duration_seconds=("event_duration_seconds", "median"),
            mean_duration_seconds=("event_duration_seconds", "mean"),
            p90_duration_seconds=(
                "event_duration_seconds",
                lambda values: values.quantile(0.90)
            ),
            maximum_duration_seconds=("event_duration_seconds", "max"),
            total_recorded_seconds=("event_duration_seconds", "sum")
        )
        .reset_index()
    )

    activity_duration["median_duration_minutes"] = (
        activity_duration["median_duration_seconds"] / 60
    )
    activity_duration["p90_duration_minutes"] = (
        activity_duration["p90_duration_seconds"] / 60
    )
    activity_duration["total_recorded_hours"] = (
        activity_duration["total_recorded_seconds"] / 3600
    )

    total_events_with_duration = activity_duration["event_count"].sum()

    if total_events_with_duration > 0:
        activity_duration["share_of_events_with_duration_percent"] = (
            activity_duration["event_count"]
            / total_events_with_duration * 100
        )
    else:
        activity_duration["share_of_events_with_duration_percent"] = 0.0

    activity_duration = activity_duration.sort_values(
        "p90_duration_seconds",
        ascending=False,
        na_position="last"
    )

    print("Identifying potential bottleneck candidates...")

    candidates = activity_duration.loc[
        activity_duration["event_count"] >= MIN_EVENTS_FOR_CANDIDATE
    ].copy()

    candidates["investigation_rank"] = range(1, len(candidates) + 1)

    candidates["interpretation"] = (
        "High recorded event-duration percentile; investigate operational context"
    )

    candidates["minimum_sample_size"] = MIN_EVENTS_FOR_CANDIDATE

    print("Summarising activity volumes over time...")

    df["start_hour"] = df["Start Timestamp"].dt.floor("h")
    df["start_date"] = df["Start Timestamp"].dt.strftime("%Y-%m-%d")

    hourly_volume = (
        df.groupby(["start_hour", "activity"], observed=True)
        .size()
        .reset_index(name="event_count")
        .sort_values(["start_hour", "event_count"], ascending=[True, False])
    )

    daily_volume = (
        df.groupby(["start_date", "activity"], observed=True)
        .size()
        .reset_index(name="event_count")
        .sort_values(["start_date", "event_count"], ascending=[True, False])
    )

    daily_totals = (
        df.groupby("start_date", observed=True)
        .size()
        .reset_index(name="total_events")
        .sort_values("start_date")
    )

    print("Analysing activity transitions and time gaps...")

    grouped = df.groupby("case_id", sort=False, observed=True)

    df["previous_activity"] = grouped["activity"].shift(1)
    df["previous_end_timestamp"] = grouped["End Timestamp"].shift(1)

    df["gap_seconds"] = (
        df["Start Timestamp"] - df["previous_end_timestamp"]
    ).dt.total_seconds()

    transition_rows = df.loc[
        df["previous_activity"].notna(),
        [
            "previous_activity",
            "activity",
            "gap_seconds"
        ]
    ].copy()

    transition_summary = (
        transition_rows
        .groupby(
            ["previous_activity", "activity"],
            observed=True
        )
        .agg(
            transition_count=("gap_seconds", "size"),
            median_gap_seconds=("gap_seconds", "median"),
            mean_gap_seconds=("gap_seconds", "mean"),
            p90_gap_seconds=(
                "gap_seconds",
                lambda values: values.quantile(0.90)
            ),
            negative_gap_count=(
                "gap_seconds",
                lambda values: int((values < 0).sum())
            ),
            zero_gap_count=(
                "gap_seconds",
                lambda values: int((values == 0).sum())
            )
        )
        .reset_index()
        .rename(columns={
            "previous_activity": "from_activity",
            "activity": "to_activity"
        })
        .sort_values("transition_count", ascending=False)
    )

    transition_summary["median_gap_minutes"] = (
        transition_summary["median_gap_seconds"] / 60
    )
    transition_summary["p90_gap_minutes"] = (
        transition_summary["p90_gap_seconds"] / 60
    )

    positive_gaps = transition_rows.loc[
        transition_rows["gap_seconds"] >= 0
    ].copy()

    positive_gap_summary = (
        positive_gaps
        .groupby(
            ["previous_activity", "activity"],
            observed=True
        )
        .agg(
            nonnegative_gap_count=("gap_seconds", "count"),
            median_nonnegative_gap_seconds=("gap_seconds", "median"),
            p90_nonnegative_gap_seconds=(
                "gap_seconds",
                lambda values: values.quantile(0.90)
            )
        )
        .reset_index()
        .rename(columns={
            "previous_activity": "from_activity",
            "activity": "to_activity"
        })
    )

    transition_summary = transition_summary.merge(
        positive_gap_summary,
        on=["from_activity", "to_activity"],
        how="left",
        validate="one_to_one"
    )

    negative_gap_count = int(
        (transition_rows["gap_seconds"] < 0).sum()
    )
    zero_gap_count = int(
        (transition_rows["gap_seconds"] == 0).sum()
    )
    positive_gap_count = int(
        (transition_rows["gap_seconds"] > 0).sum()
    )

    print("Reviewing case-level elapsed-time distribution...")

    elapsed = pd.to_numeric(features["elapsed_hours"], errors="coerce")
    elapsed = elapsed.dropna()

    if not elapsed.empty:
        elapsed_summary = {
            "case_count_with_elapsed_time": int(elapsed.count()),
            "minimum_elapsed_hours": float(elapsed.min()),
            "median_elapsed_hours": float(elapsed.median()),
            "mean_elapsed_hours": float(elapsed.mean()),
            "p90_elapsed_hours": float(elapsed.quantile(0.90)),
            "maximum_elapsed_hours": float(elapsed.max()),
            "zero_elapsed_case_count": int((elapsed == 0).sum())
        }
    else:
        elapsed_summary = {
            "case_count_with_elapsed_time": 0,
            "minimum_elapsed_hours": None,
            "median_elapsed_hours": None,
            "mean_elapsed_hours": None,
            "p90_elapsed_hours": None,
            "maximum_elapsed_hours": None,
            "zero_elapsed_case_count": 0
        }

    print("Saving analysis outputs...")

    activity_duration.to_csv(
        OUTPUT_DIR / "activity_duration_analysis.csv",
        index=False
    )

    candidates.to_csv(
        OUTPUT_DIR / "bottleneck_candidates.csv",
        index=False
    )

    hourly_volume.to_csv(
        OUTPUT_DIR / "hourly_activity_volume.csv",
        index=False,
        date_format="%Y-%m-%d %H:%M:%S"
    )

    daily_volume.to_csv(
        OUTPUT_DIR / "daily_activity_volume.csv",
        index=False
    )

    daily_totals.to_csv(
        OUTPUT_DIR / "daily_total_event_volume.csv",
        index=False
    )

    transition_summary.to_csv(
        OUTPUT_DIR / "transition_gap_analysis.csv",
        index=False
    )

    report = {
        "project": "PortPulse AI",
        "input_event_file": EVENTS_FILE.name,
        "input_case_feature_file": FEATURES_FILE.name,
        "valid_event_rows_analysed": int(len(df)),
        "unique_cases_in_events": int(df["case_id"].nunique()),
        "distinct_activities": int(df["activity"].nunique()),
        "activity_duration_groups": int(len(activity_duration)),
        "bottleneck_candidates_reported": int(len(candidates)),
        "minimum_events_for_candidate": MIN_EVENTS_FOR_CANDIDATE,
        "hourly_activity_rows": int(len(hourly_volume)),
        "daily_activity_rows": int(len(daily_volume)),
        "distinct_activity_transitions": int(len(transition_summary)),
        "consecutive_event_transitions": int(len(transition_rows)),
        "negative_inter_event_gaps": negative_gap_count,
        "zero_inter_event_gaps": zero_gap_count,
        "positive_inter_event_gaps": positive_gap_count,
        "case_elapsed_time_summary": elapsed_summary,
        "interpretation_notes": [
            "A high event duration is a candidate for investigation, not proof of a bottleneck.",
            "Event duration and inter-event gap are different measurements.",
            "Negative inter-event gaps indicate overlap between consecutive recorded events; they are not automatically data errors.",
            "Elapsed time is measured from the first recorded start to the last recorded end for a case.",
            "True container dwell time has not been confirmed from the available field definitions.",
            "The event-count threshold is a screening choice, not a validated operational threshold."
        ]
    }

    with open(
        REPORT_DIR / "process_analysis_report.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    with open(
        REPORT_DIR / "process_analysis_report.txt",
        "w",
        encoding="utf-8"
    ) as file:
        file.write("PORTPULSE AI — PROCESS ANALYSIS REPORT\n")
        file.write("=" * 42 + "\n\n")

        for key, value in report.items():
            file.write(f"{key}: {value}\n")

    print("\nProcess analysis completed.")
    print(f"Valid events analysed: {len(df):,}")
    print(f"Unique cases: {df['case_id'].nunique():,}")
    print(f"Activities analysed: {len(activity_duration):,}")
    print(f"Potential bottleneck candidates: {len(candidates):,}")
    print(f"Activity transitions: {len(transition_summary):,}")
    print(f"Negative inter-event gaps: {negative_gap_count:,}")
    print(f"Outputs saved to: {OUTPUT_DIR}")
    print(f"Report saved to: {REPORT_DIR}")


if __name__ == "__main__":
    main()
