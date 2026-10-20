
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

ACTIVITY_KEYWORDS = [
    "gate in",
    "gate out",
    "arrival",
    "departure",
    "arrive",
    "depart",
    "entry",
    "exit",
    "release",
    "out gate",
    "in gate"
]


def find_activity_candidates(activity_values):
    candidates = []

    for activity in activity_values:
        activity_text = str(activity)
        activity_lower = activity_text.lower()

        matched_keywords = [
            keyword for keyword in ACTIVITY_KEYWORDS
            if keyword in activity_lower
        ]

        if matched_keywords:
            candidates.append({
                "activity": activity_text,
                "matched_keywords": "; ".join(matched_keywords)
            })

    return candidates


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

    print("Loading validated events and case features...")

    events = pd.read_csv(
        EVENTS_FILE,
        compression="gzip",
        parse_dates=["Start Timestamp", "End Timestamp"]
    )

    features = pd.read_csv(
        FEATURES_FILE,
        compression="gzip",
        parse_dates=["case_start_timestamp", "case_end_timestamp"]
    )

    required_event_columns = [
        "case_id",
        "activity",
        "Start Timestamp",
        "End Timestamp"
    ]

    missing_event_columns = [
        column for column in required_event_columns
        if column not in events.columns
    ]

    if missing_event_columns:
        raise ValueError(
            f"Required event columns missing: {missing_event_columns}"
        )

    required_feature_columns = [
        "case_id",
        "case_start_timestamp",
        "case_end_timestamp",
        "elapsed_hours",
        "event_count",
        "unique_activity_count"
    ]

    missing_feature_columns = [
        column for column in required_feature_columns
        if column not in features.columns
    ]

    if missing_feature_columns:
        raise ValueError(
            f"Required feature columns missing: {missing_feature_columns}"
        )

    events["case_id"] = events["case_id"].astype("string")
    events["activity"] = events["activity"].astype("string")
    features["case_id"] = features["case_id"].astype("string")

    events = events.sort_values(
        ["case_id", "Start Timestamp", "End Timestamp"],
        kind="mergesort"
    ).reset_index(drop=True)

    print("Checking case-level target candidates...")

    features["elapsed_hours"] = pd.to_numeric(
        features["elapsed_hours"],
        errors="coerce"
    )

    features["observed_elapsed_days"] = (
        features["elapsed_hours"] / 24
    )

    features["has_positive_elapsed_time"] = (
        features["elapsed_hours"] > 0
    )

    features["has_zero_elapsed_time"] = (
        features["elapsed_hours"] == 0
    )

    features["has_negative_elapsed_time"] = (
        features["elapsed_hours"] < 0
    )

    features["elapsed_time_available"] = (
        features["elapsed_hours"].notna()
    )

    features["elapsed_time_candidate_p95"] = False

    valid_elapsed = features["elapsed_hours"].dropna()

    if not valid_elapsed.empty:
        elapsed_p95 = float(valid_elapsed.quantile(0.95))
        features["elapsed_time_candidate_p95"] = (
            features["elapsed_hours"] > elapsed_p95
        )
    else:
        elapsed_p95 = None

    print("Inspecting activity labels and event coverage...")

    activity_counts = (
        events["activity"]
        .fillna("[MISSING ACTIVITY]")
        .value_counts(dropna=False)
        .rename_axis("activity")
        .reset_index(name="event_count")
    )

    activity_counts["share_of_events_percent"] = (
        activity_counts["event_count"] / max(len(events), 1) * 100
    ).round(3)

    activity_candidates = find_activity_candidates(
        activity_counts["activity"].tolist()
    )

    activity_candidate_df = pd.DataFrame(
        activity_candidates,
        columns=["activity", "matched_keywords"]
    )

    if not activity_candidate_df.empty:
        activity_candidate_df = activity_candidate_df.merge(
            activity_counts,
            on="activity",
            how="left",
            validate="one_to_one"
        )

    print("Checking case consistency...")

    per_case_check = (
        events.groupby("case_id", observed=True)
        .agg(
            event_rows=("activity", "size"),
            distinct_activities=("activity", "nunique"),
            earliest_event_start=("Start Timestamp", "min"),
            latest_event_end=("End Timestamp", "max"),
            missing_start_timestamps=("Start Timestamp", lambda values: int(values.isna().sum())),
            missing_end_timestamps=("End Timestamp", lambda values: int(values.isna().sum()))
        )
        .reset_index()
    )

    per_case_check["recalculated_elapsed_hours"] = (
        per_case_check["latest_event_end"]
        - per_case_check["earliest_event_start"]
    ).dt.total_seconds() / 3600

    case_comparison = features[
        [
            "case_id",
            "elapsed_hours",
            "event_count",
            "unique_activity_count",
            "case_start_timestamp",
            "case_end_timestamp"
        ]
    ].merge(
        per_case_check,
        on="case_id",
        how="outer",
        suffixes=("_feature", "_event"),
        indicator=True
    )

    case_comparison["case_presence_match"] = (
        case_comparison["_merge"] == "both"
    )

    case_comparison["elapsed_hours_difference"] = (
        case_comparison["elapsed_hours"]
        - case_comparison["recalculated_elapsed_hours"]
    )

    case_comparison["elapsed_hours_match_with_tolerance"] = (
        case_comparison["elapsed_hours_difference"].abs() < 0.000001
    )

    print("Building a retrospective modelling candidate table...")

    candidate_columns = [
        "case_id",
        "case_start_timestamp",
        "case_end_timestamp",
        "event_count",
        "unique_activity_count",
        "first_activity",
        "last_activity",
        "elapsed_hours",
        "observed_elapsed_days",
        "elapsed_time_available",
        "elapsed_time_candidate_p95"
    ]

    optional_columns = [
        "representative_CTR_SIZE",
        "representative_CTR_TYPE",
        "representative_GROSS",
        "representative_JOB_DEL_DOCTYPE"
    ]

    candidate_columns.extend([
        column for column in optional_columns
        if column in features.columns
    ])

    retrospective_table = features[candidate_columns].copy()

    retrospective_table["target_status"] = (
        "retrospective_elapsed_time_candidate_not_validated_dwell_time"
    )

    retrospective_table["prediction_readiness"] = (
        "not_ready_requires_target_and_prediction_time_definition"
    )

    print("Saving audit tables and report...")

    features.to_csv(
        OUTPUT_DIR / "case_target_audit.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    retrospective_table.to_csv(
        OUTPUT_DIR / "retrospective_modelling_candidate.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    activity_counts.to_csv(
        OUTPUT_DIR / "target_audit_activity_counts.csv",
        index=False
    )

    activity_candidate_df.to_csv(
        OUTPUT_DIR / "possible_entry_exit_activity_labels.csv",
        index=False
    )

    case_comparison.to_csv(
        OUTPUT_DIR / "case_feature_consistency_check.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    numeric_elapsed = features["elapsed_hours"].dropna()

    report = {
        "project": "PortPulse AI",
        "input_event_file": EVENTS_FILE.name,
        "input_feature_file": FEATURES_FILE.name,
        "valid_event_rows": int(len(events)),
        "event_log_unique_cases": int(events["case_id"].nunique()),
        "feature_table_rows": int(len(features)),
        "feature_table_unique_cases": int(features["case_id"].nunique()),
        "distinct_activity_labels": int(events["activity"].nunique()),
        "activity_labels_matching_entry_exit_keywords": int(len(activity_candidate_df)),
        "case_elapsed_time_available": int(features["elapsed_hours"].notna().sum()),
        "case_elapsed_time_missing": int(features["elapsed_hours"].isna().sum()),
        "cases_with_positive_elapsed_time": int((features["elapsed_hours"] > 0).sum()),
        "cases_with_zero_elapsed_time": int((features["elapsed_hours"] == 0).sum()),
        "cases_with_negative_elapsed_time": int((features["elapsed_hours"] < 0).sum()),
        "case_elapsed_time_p95_hours": elapsed_p95,
        "cases_above_elapsed_time_p95": int(features["elapsed_time_candidate_p95"].sum()),
        "case_feature_rows_present_in_both_tables": int(
            (case_comparison["_merge"] == "both").sum()
        ),
        "case_feature_rows_only_in_features": int(
            (case_comparison["_merge"] == "left_only").sum()
        ),
        "case_rows_only_in_events": int(
            (case_comparison["_merge"] == "right_only").sum()
        ),
        "elapsed_time_match_count_with_tolerance": int(
            case_comparison["elapsed_hours_match_with_tolerance"].fillna(False).sum()
        ),
        "median_observed_elapsed_hours": (
            float(numeric_elapsed.median())
            if not numeric_elapsed.empty else None
        ),
        "mean_observed_elapsed_hours": (
            float(numeric_elapsed.mean())
            if not numeric_elapsed.empty else None
        ),
        "candidate_target": (
            "Observed elapsed time from earliest recorded event start "
            "to latest recorded event end per case."
        ),
        "target_validation_status": (
            "Not confirmed as true container dwell time or future delay."
        ),
        "prediction_leakage_warning": [
            "case_end_timestamp and last_activity may reveal future information.",
            "event_count and unique_activity_count are full-case features and may be unavailable at prediction time.",
            "Container attributes selected from all events may contain future information if they change over a case.",
            "A global elapsed-time percentile is a retrospective relative label, not an independently validated delay threshold."
        ],
        "activity_keyword_warning": (
            "Keyword matches are investigation candidates only; activity meanings "
            "must be confirmed from a data dictionary or domain knowledge."
        ),
        "model_training_performed": False
    }

    with open(
        REPORT_DIR / "model_readiness_report.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    with open(
        REPORT_DIR / "model_readiness_report.txt",
        "w",
        encoding="utf-8"
    ) as file:
        file.write("PORTPULSE AI — MODEL READINESS REPORT\n")
        file.write("=" * 40 + "\n\n")

        for key, value in report.items():
            file.write(f"{key}: {value}\n")

    print("\nModel readiness audit completed.")
    print(f"Valid event rows: {len(events):,}")
    print(f"Unique event-log cases: {events['case_id'].nunique():,}")
    print(f"Case feature rows: {len(features):,}")
    print(f"Activity labels matching entry/exit keywords: {len(activity_candidate_df):,}")
    print(f"Cases with elapsed time available: {features['elapsed_hours'].notna().sum():,}")
    print(f"Cases above elapsed-time p95: {features['elapsed_time_candidate_p95'].sum():,}")
    print("Model training performed: No")
    print(f"Outputs saved to: {OUTPUT_DIR}")
    print(f"Report saved to: {REPORT_DIR}")
if __name__ == "__main__":
    main()