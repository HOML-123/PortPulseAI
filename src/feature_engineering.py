
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = ROOT / "data" / "processed" / "valid_events.csv.gz"
OUTPUT_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "outputs" / "reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def first_non_missing(series):
    values = series.dropna()
    if values.empty:
        return pd.NA
    return values.iloc[0]


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}\n"
            "Run python src\\clean_data.py first."
        )

    print("Loading valid event records...")

    df = pd.read_csv(
        INPUT_FILE,
        compression="gzip",
        parse_dates=["Start Timestamp", "End Timestamp"]
    )

    required_columns = [
        "case_id",
        "activity",
        "Start Timestamp",
        "End Timestamp",
        "event_duration_seconds"
    ]

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Required columns are missing: {missing_columns}"
        )

    df["case_id"] = df["case_id"].astype("string")
    df["activity"] = df["activity"].astype("string")
    df["event_duration_seconds"] = pd.to_numeric(
        df["event_duration_seconds"],
        errors="coerce"
    )

    sort_columns = [
        "case_id",
        "Start Timestamp",
        "End Timestamp"
    ]

    if "source_row_number" in df.columns:
        sort_columns.append("source_row_number")

    df = df.sort_values(
        sort_columns,
        kind="mergesort"
    ).reset_index(drop=True)

    print("Building container-level features...")

    grouped = df.groupby("case_id", sort=False, observed=True)

    features = grouped.agg(
        case_start_timestamp=("Start Timestamp", "min"),
        case_end_timestamp=("End Timestamp", "max"),
        event_count=("activity", "size"),
        unique_activity_count=("activity", "nunique"),
        first_activity=("activity", "first"),
        last_activity=("activity", "last"),
        total_recorded_event_seconds=(
            "event_duration_seconds", "sum"
        ),
        average_event_seconds=(
            "event_duration_seconds", "mean"
        ),
        longest_event_seconds=(
            "event_duration_seconds", "max"
        )
    ).reset_index()

    features["elapsed_seconds"] = (
        features["case_end_timestamp"]
        - features["case_start_timestamp"]
    ).dt.total_seconds()

    features["elapsed_hours"] = (
        features["elapsed_seconds"] / 3600
    )

    features["elapsed_days"] = (
        features["elapsed_seconds"] / 86400
    )

    optional_case_columns = [
        "CTR_SIZE",
        "CTR_TYPE",
        "GROSS",
        "YARD_BLOCK",
        "YARD_SLOT",
        "JOB_DEL_DOCTYPE"
    ]

    for column in optional_case_columns:
        if column in df.columns:
            case_attribute = grouped[column].agg(
                first_non_missing
            ).rename(f"representative_{column}").reset_index()

            features = features.merge(
                case_attribute,
                on="case_id",
                how="left",
                validate="one_to_one"
            )

    if "Role" in df.columns:
        role_counts = grouped["Role"].nunique().rename(
            "unique_role_count"
        ).reset_index()

        features = features.merge(
            role_counts,
            on="case_id",
            how="left",
            validate="one_to_one"
        )

    activity_sequences = (
        grouped["activity"]
        .agg(lambda values: " -> ".join(values.astype(str)))
        .rename("activity_sequence")
        .reset_index()
    )

    sequence_output = activity_sequences.merge(
        features[[
            "case_id",
            "event_count",
            "case_start_timestamp",
            "case_end_timestamp",
            "elapsed_hours"
        ]],
        on="case_id",
        how="left",
        validate="one_to_one"
    )

    print("Counting activities per case...")

    case_activity_counts = (
        df.groupby(
            ["case_id", "activity"],
            observed=True,
            sort=False
        )
        .size()
        .reset_index(name="event_count")
        .sort_values(["case_id", "event_count"], ascending=[True, False])
    )

    print("Building activity transition summary...")

    df["previous_activity"] = grouped["activity"].shift(1)

    transition_rows = df.loc[
        df["previous_activity"].notna(),
        ["previous_activity", "activity"]
    ].copy()

    transition_summary = (
        transition_rows
        .groupby(
            ["previous_activity", "activity"],
            observed=True
        )
        .size()
        .reset_index(name="transition_count")
        .rename(columns={
            "previous_activity": "from_activity",
            "activity": "to_activity"
        })
        .sort_values("transition_count", ascending=False)
    )

    print("Summarising activity by date...")

    df["activity_date"] = df["Start Timestamp"].dt.strftime("%Y-%m-%d")

    daily_activity_summary = (
        df.groupby(
            ["activity_date", "activity"],
            observed=True
        )
        .size()
        .reset_index(name="event_count")
        .sort_values(["activity_date", "event_count"], ascending=[True, False])
    )

    print("Saving feature-engineering outputs...")

    features.to_csv(
        OUTPUT_DIR / "container_features.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    sequence_output.to_csv(
        OUTPUT_DIR / "case_activity_sequences.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    case_activity_counts.to_csv(
        OUTPUT_DIR / "case_activity_counts.csv.gz",
        index=False,
        compression="gzip"
    )

    transition_summary.to_csv(
        OUTPUT_DIR / "activity_transitions.csv",
        index=False
    )

    daily_activity_summary.to_csv(
        OUTPUT_DIR / "daily_activity_summary.csv",
        index=False
    )

    zero_elapsed_cases = int(
        (features["elapsed_seconds"] == 0).sum()
    )

    report = {
        "project": "PortPulse AI",
        "source_file": INPUT_FILE.name,
        "input_valid_event_rows": int(len(df)),
        "unique_cases": int(features["case_id"].nunique()),
        "container_feature_rows": int(len(features)),
        "case_sequence_rows": int(len(sequence_output)),
        "case_activity_count_rows": int(len(case_activity_counts)),
        "distinct_activities": int(df["activity"].nunique()),
        "distinct_activity_transitions": int(len(transition_summary)),
        "daily_activity_summary_rows": int(len(daily_activity_summary)),
        "cases_with_zero_elapsed_seconds": zero_elapsed_cases,
        "median_case_elapsed_hours": (
            float(features["elapsed_hours"].median())
            if not features.empty else None
        ),
        "mean_case_elapsed_hours": (
            float(features["elapsed_hours"].mean())
            if not features.empty else None
        ),
        "elapsed_time_definition": (
            "Difference between the earliest recorded event start "
            "and latest recorded event end for each case_id."
        ),
        "duration_definition": (
            "Total recorded event seconds is the sum of individual "
            "event durations and can differ from case elapsed time."
        ),
        "case_attribute_note": (
            "Representative container attributes use the first "
            "non-missing value in timestamp-sorted records. "
            "Conflicting values within a case are not resolved here."
        ),
        "dwell_time_note": (
            "Elapsed time is not confirmed to be true container dwell "
            "time until case_id semantics and terminal entry/exit "
            "activity meanings are verified."
        )
    }

    with open(
        REPORT_DIR / "feature_engineering_report.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    with open(
        REPORT_DIR / "feature_engineering_report.txt",
        "w",
        encoding="utf-8"
    ) as file:
        file.write("PORTPULSE AI — FEATURE ENGINEERING REPORT\n")
        file.write("=" * 44 + "\n\n")

        for key, value in report.items():
            file.write(f"{key}: {value}\n")

    print("\nFeature engineering completed.")
    print(f"Valid event rows analysed: {len(df):,}")
    print(f"Unique cases: {features['case_id'].nunique():,}")
    print(f"Distinct activities: {df['activity'].nunique():,}")
    print(f"Activity transitions: {len(transition_summary):,}")
    print(f"Cases with zero elapsed time: {zero_elapsed_cases:,}")
    print(f"Processed outputs saved to: {OUTPUT_DIR}")
    print(f"Report saved to: {REPORT_DIR}")


if __name__ == "__main__":
    main()
