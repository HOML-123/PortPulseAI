
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

DURATION_PERCENTILE = 0.95
CASE_ELAPSED_PERCENTILE = 0.95
MIN_ACTIVITY_SAMPLE = 20
MIN_TRANSITION_COUNT = 5


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

    print("Loading event and case-level data...")

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
        "End Timestamp",
        "event_duration_seconds"
    ]

    missing = [
        column for column in required_event_columns
        if column not in events.columns
    ]

    if missing:
        raise ValueError(f"Required event columns missing: {missing}")

    if "case_id" not in features.columns or "elapsed_hours" not in features.columns:
        raise ValueError(
            "Case feature file must contain case_id and elapsed_hours."
        )

    events["case_id"] = events["case_id"].astype("string")
    events["activity"] = events["activity"].astype("string")
    events["event_duration_seconds"] = pd.to_numeric(
        events["event_duration_seconds"],
        errors="coerce"
    )

    events = events.sort_values(
        ["case_id", "Start Timestamp", "End Timestamp"],
        kind="mergesort"
    ).reset_index(drop=True)

    print("Detecting unusually long recorded events...")

    activity_stats = (
        events.groupby("activity", observed=True)
        .agg(
            activity_event_count=("event_duration_seconds", "count"),
            activity_median_seconds=("event_duration_seconds", "median"),
            activity_p95_seconds=(
                "event_duration_seconds",
                lambda values: values.quantile(DURATION_PERCENTILE)
            )
        )
        .reset_index()
    )

    events = events.merge(
        activity_stats,
        on="activity",
        how="left",
        validate="many_to_one"
    )

    events["duration_anomaly"] = (
        events["event_duration_seconds"].notna()
        & events["activity_event_count"].ge(MIN_ACTIVITY_SAMPLE)
        & events["activity_p95_seconds"].notna()
        & (events["event_duration_seconds"] > events["activity_p95_seconds"])
    )

    print("Detecting uncommon consecutive activity transitions...")

    grouped = events.groupby("case_id", sort=False, observed=True)

    events["previous_activity"] = grouped["activity"].shift(1)

    has_previous = events["previous_activity"].notna()

    transition_counts = (
        events.loc[has_previous]
        .groupby(
            ["previous_activity", "activity"],
            observed=True
        )
        .size()
        .rename("transition_frequency")
        .reset_index()
    )

    events = events.merge(
        transition_counts,
        on=["previous_activity", "activity"],
        how="left",
        validate="many_to_one"
    )

    events["transition_frequency"] = (
        events["transition_frequency"].fillna(0).astype("int64")
    )

    events["rare_transition"] = (
        events["previous_activity"].notna()
        & (events["transition_frequency"] <= MIN_TRANSITION_COUNT)
    )

    print("Creating event-level anomaly reasons...")

    events["event_risk_score"] = (
        events["duration_anomaly"].astype("int8")
        + events["rare_transition"].astype("int8")
    )

    events["event_risk_reasons"] = ""

    duration_reason = events["duration_anomaly"]
    rare_reason = events["rare_transition"]

    events.loc[duration_reason, "event_risk_reasons"] = (
        "duration_above_activity_p95"
    )

    events.loc[rare_reason, "event_risk_reasons"] = (
        events.loc[rare_reason, "event_risk_reasons"].apply(
            lambda current: (
                f"{current}; rare_activity_transition"
                if current else "rare_activity_transition"
            )
        )
    )

    print("Building case-level risk indicators...")

    case_risk = (
        events.groupby("case_id", observed=True)
        .agg(
            event_count=("activity", "size"),
            duration_anomaly_count=("duration_anomaly", "sum"),
            rare_transition_count=("rare_transition", "sum"),
            maximum_event_risk_score=("event_risk_score", "max")
        )
        .reset_index()
    )

    case_risk["has_duration_anomaly"] = (
        case_risk["duration_anomaly_count"] > 0
    )

    case_risk["has_rare_transition"] = (
        case_risk["rare_transition_count"] > 0
    )

    features["case_id"] = features["case_id"].astype("string")
    features["elapsed_hours"] = pd.to_numeric(
        features["elapsed_hours"],
        errors="coerce"
    )

    valid_elapsed = features["elapsed_hours"].dropna()

    if len(valid_elapsed) > 0:
        elapsed_threshold = float(
            valid_elapsed.quantile(CASE_ELAPSED_PERCENTILE)
        )
        features["long_elapsed_case"] = (
            features["elapsed_hours"].notna()
            & (features["elapsed_hours"] > elapsed_threshold)
        )
    else:
        elapsed_threshold = None
        features["long_elapsed_case"] = False

    case_risk = case_risk.merge(
        features[["case_id", "elapsed_hours", "long_elapsed_case"]],
        on="case_id",
        how="left",
        validate="one_to_one"
    )

    case_risk["long_elapsed_case"] = (
        case_risk["long_elapsed_case"].fillna(False).astype(bool)
    )

    case_risk["risk_score"] = (
        case_risk["has_duration_anomaly"].astype("int8")
        + case_risk["has_rare_transition"].astype("int8")
        + case_risk["long_elapsed_case"].astype("int8")
    )

    case_risk["risk_level"] = "Low"
    case_risk.loc[case_risk["risk_score"] == 1, "risk_level"] = "Review"
    case_risk.loc[case_risk["risk_score"] == 2, "risk_level"] = "Elevated"
    case_risk.loc[case_risk["risk_score"] == 3, "risk_level"] = "High"

    def build_case_reasons(row):
        reasons = []

        if row["has_duration_anomaly"]:
            reasons.append("one_or_more_long_events")

        if row["has_rare_transition"]:
            reasons.append("one_or_more_rare_transitions")

        if row["long_elapsed_case"]:
            reasons.append("elapsed_time_above_global_p95")

        return "; ".join(reasons) if reasons else "no_current_rule_triggered"

    case_risk["risk_reasons"] = case_risk.apply(
        build_case_reasons,
        axis=1
    )

    case_risk = case_risk.sort_values(
        ["risk_score", "elapsed_hours"],
        ascending=[False, False],
        na_position="last"
    )

    flagged_events = events.loc[
        events["event_risk_score"] > 0
    ].copy()

    flagged_cases = case_risk.loc[
        case_risk["risk_score"] > 0
    ].copy()

    transition_summary = (
        transition_counts
        .sort_values("transition_frequency", ascending=True)
        .reset_index(drop=True)
    )

    transition_summary["is_rare_transition"] = (
        transition_summary["transition_frequency"] <= MIN_TRANSITION_COUNT
    )

    print("Saving risk-analysis outputs...")

    events.to_csv(
        OUTPUT_DIR / "event_risk_indicators.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    flagged_events.to_csv(
        OUTPUT_DIR / "flagged_events_for_review.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    case_risk.to_csv(
        OUTPUT_DIR / "case_risk_scores.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    flagged_cases.to_csv(
        OUTPUT_DIR / "flagged_cases_for_review.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    transition_summary.to_csv(
        OUTPUT_DIR / "transition_frequency_analysis.csv",
        index=False
    )

    risk_counts = (
        case_risk["risk_level"]
        .value_counts()
        .reindex(["Low", "Review", "Elevated", "High"], fill_value=0)
        .to_dict()
    )

    report = {
        "project": "PortPulse AI",
        "input_event_file": EVENTS_FILE.name,
        "input_feature_file": FEATURES_FILE.name,
        "event_rows_analysed": int(len(events)),
        "unique_cases_analysed": int(case_risk["case_id"].nunique()),
        "events_with_duration_anomaly": int(events["duration_anomaly"].sum()),
        "events_with_rare_transition": int(events["rare_transition"].sum()),
        "events_flagged_for_review": int(len(flagged_events)),
        "cases_flagged_for_review": int(len(flagged_cases)),
        "risk_level_case_counts": {
            str(key): int(value)
            for key, value in risk_counts.items()
        },
        "duration_percentile_threshold": DURATION_PERCENTILE,
        "minimum_activity_sample": MIN_ACTIVITY_SAMPLE,
        "minimum_transition_count_for_rare_flag": MIN_TRANSITION_COUNT,
        "case_elapsed_percentile_threshold": CASE_ELAPSED_PERCENTILE,
        "case_elapsed_hours_threshold": elapsed_threshold,
        "risk_score_definition": (
            "One point each for at least one duration anomaly, at least "
            "one rare transition, and elapsed hours above the global "
            "95th percentile. Maximum score is 3."
        ),
        "interpretation_notes": [
            "These are rule-based screening indicators, not a trained prediction model.",
            "An event is duration-flagged when its duration is strictly above its activity-specific 95th percentile and the activity has at least 20 events with numeric duration.",
            "A transition is rare when its observed frequency is at most 5.",
            "A long-elapsed case is above the global 95th percentile of case elapsed hours.",
            "Thresholds are initial analytical choices and should be reviewed.",
            "A flagged record is not proof of operational failure or a true bottleneck.",
            "Elapsed hours are not confirmed true container dwell time.",
            "The score is a transparent rule count, not a calibrated probability."
        ]
    }

    with open(
        REPORT_DIR / "risk_analysis_report.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    with open(
        REPORT_DIR / "risk_analysis_report.txt",
        "w",
        encoding="utf-8"
    ) as file:
        file.write("PORTPULSE AI — RISK ANALYSIS REPORT\n")
        file.write("=" * 38 + "\n\n")

        for key, value in report.items():
            file.write(f"{key}: {value}\n")

    print("\nRisk analysis completed.")
    print(f"Events analysed: {len(events):,}")
    print(f"Unique cases analysed: {case_risk['case_id'].nunique():,}")
    print(f"Duration-anomaly events: {int(events['duration_anomaly'].sum()):,}")
    print(f"Rare-transition events: {int(events['rare_transition'].sum()):,}")
    print(f"Flagged events: {len(flagged_events):,}")
    print(f"Flagged cases: {len(flagged_cases):,}")
    print(f"Risk report saved to: {REPORT_DIR}")


if __name__ == "__main__":
    main()
