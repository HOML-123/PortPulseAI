from pathlib import Path
import json
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "raw" / "Dataset of Dwelling Time Process Fix.xlsx"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "outputs" / "reports"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)
def add_flag(flags, condition, label):
    flags.loc[condition] = flags.loc[condition].apply(
        lambda current: f"{current}; {label}" if current else label)
def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATA_FILE}")
    print("Loading source dataset...")
    df = pd.read_excel(
        DATA_FILE,
        sheet_name="Sheet1",
        engine="openpyxl")
    original_row_count = len(df)
    df.columns = [str(column).strip() for column in df.columns]
    source_columns = list(df.columns)
    required_columns = [
        "case_id",
        "activity",
        "Start Timestamp",
        "End Timestamp"]
    missing_columns = [
        column for column in required_columns
        if column not in df.columns]
    if missing_columns:
        raise ValueError(
            f"Required columns are missing: {missing_columns}")
    df.insert(0, "source_row_number", range(2, len(df) + 2))
    print("Standardising text and timestamps...")
    for column in df.select_dtypes(include=["object", "string"]).columns:
        df[column] = df[column].map(
            lambda value: value.strip()
            if isinstance(value, str) else value)
        df[column] = df[column].replace("", pd.NA)
    for column in ["Start Timestamp", "End Timestamp"]:
        df[column] = pd.to_datetime(
            df[column],
            errors="coerce"
        )

    exact_duplicate_mask = df.duplicated(
        subset=source_columns,
        keep="first"
    )

    flags = pd.Series("", index=df.index, dtype="object")

    missing_case = df["case_id"].isna()
    missing_activity = df["activity"].isna()
    missing_start = df["Start Timestamp"].isna()
    missing_end = df["End Timestamp"].isna()

    reversed_timestamps = (
        df["Start Timestamp"].notna()
        & df["End Timestamp"].notna()
        & (df["End Timestamp"] < df["Start Timestamp"])
    )

    add_flag(flags, missing_case, "missing_case_id")
    add_flag(flags, missing_activity, "missing_activity")
    add_flag(flags, missing_start, "missing_start_timestamp")
    add_flag(flags, missing_end, "missing_end_timestamp")
    add_flag(flags, reversed_timestamps, "end_before_start")
    add_flag(flags, exact_duplicate_mask, "exact_duplicate")

    df["event_duration_seconds"] = (
        df["End Timestamp"] - df["Start Timestamp"]
    ).dt.total_seconds()

    df["quality_flags"] = flags
    df["is_valid_event"] = (
        df["case_id"].notna()
        & df["activity"].notna()
        & df["Start Timestamp"].notna()
        & df["End Timestamp"].notna()
        & (df["End Timestamp"] >= df["Start Timestamp"])
        & ~exact_duplicate_mask
    )

    print("Creating cleaned and review datasets...")

    deduplicated = df.loc[~exact_duplicate_mask].copy()
    valid_events = deduplicated.loc[
        deduplicated["is_valid_event"]
    ].copy()

    review_events = df.loc[
        ~df["is_valid_event"]
    ].copy()

    deduplicated.to_csv(
        PROCESSED_DIR / "cleaned_events.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    valid_events.to_csv(
        PROCESSED_DIR / "valid_events.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    review_events.to_csv(
        PROCESSED_DIR / "events_for_review.csv.gz",
        index=False,
        compression="gzip",
        date_format="%Y-%m-%d %H:%M:%S"
    )

    original_missing = {
        str(column): int(df[column].isna().sum())
        for column in source_columns
    }

    report = {
        "source_file": DATA_FILE.name,
        "worksheet": "Sheet1",
        "original_rows": int(original_row_count),
        "original_columns": int(len(source_columns)),
        "rows_removed_as_exact_duplicates": int(exact_duplicate_mask.sum()),
        "rows_after_duplicate_removal": int(len(deduplicated)),
        "valid_event_rows": int(len(valid_events)),
        "rows_for_review": int(len(review_events)),
        "missing_case_id_rows": int(missing_case.sum()),
        "missing_activity_rows": int(missing_activity.sum()),
        "missing_start_timestamp_rows": int(missing_start.sum()),
        "missing_end_timestamp_rows": int(missing_end.sum()),
        "end_before_start_rows": int(reversed_timestamps.sum()),
        "original_column_missing_values": original_missing,
        "valid_event_definition": [
            "case_id present",
            "activity present",
            "start timestamp present",
            "end timestamp present",
            "end timestamp is not earlier than start timestamp",
            "not an exact duplicate after standardisation"
        ],
        "duration_note": (
            "event_duration_seconds is derived from the start and end "
            "timestamps. The units and meaning of the original Duration "
            "column have not been assumed."
        ),
        "source_file_modified": False
    }

    with open(
        REPORT_DIR / "cleaning_report.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    with open(
        REPORT_DIR / "cleaning_report.txt",
        "w",
        encoding="utf-8"
    ) as file:
        file.write("PORTPULSE AI — DATA CLEANING REPORT\n")
        file.write("=" * 40 + "\n\n")

        for key, value in report.items():
            file.write(f"{key}: {value}\n")

    print("\nCleaning pipeline completed.")
    print(f"Original rows: {original_row_count:,}")
    print(f"Exact duplicates removed: {int(exact_duplicate_mask.sum()):,}")
    print(f"Rows after deduplication: {len(deduplicated):,}")
    print(f"Valid event rows: {len(valid_events):,}")
    print(f"Rows requiring review: {len(review_events):,}")
    print(f"Processed data saved to: {PROCESSED_DIR}")
    print(f"Cleaning report saved to: {REPORT_DIR}")
if __name__ == "__main__":
    main()
