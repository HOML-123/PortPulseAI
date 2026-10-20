
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "raw" / "Dataset of Dwelling Time Process Fix.xlsx"
REPORT_DIR = ROOT / "outputs" / "reports"

REPORT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATA_FILE}\n"
            "Copy the Excel file into data/raw and run this program again."
        )

    print("Reading Excel dataset...")
    df = pd.read_excel(DATA_FILE, sheet_name="Sheet1", engine="openpyxl")

    original_rows = len(df)
    original_columns = len(df.columns)

    df.columns = [str(column).strip() for column in df.columns]

    required_columns = [
        "case_id",
        "activity",
        "Start Timestamp",
        "End Timestamp",
    ]

    missing_required = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_required:
        raise ValueError(
            f"Required columns not found: {missing_required}\n"
            f"Available columns: {df.columns.tolist()}"
        )

    for column in ["Start Timestamp", "End Timestamp"]:
        df[column] = pd.to_datetime(df[column], errors="coerce")

    if "Duration" in df.columns:
        df["Duration_numeric"] = pd.to_numeric(
            df["Duration"], errors="coerce"
        )
    else:
        df["Duration_numeric"] = pd.NA

    missing_counts = df.isna().sum()
    missing_percentages = (missing_counts / max(original_rows, 1) * 100).round(2)

    quality = pd.DataFrame({
        "column": df.columns,
        "data_type": [str(df[column].dtype) for column in df.columns],
        "missing_count": [int(df[column].isna().sum()) for column in df.columns],
        "missing_percentage": [
            round(float(df[column].isna().mean() * 100), 2)
            for column in df.columns
        ],
        "unique_values": [
            int(df[column].nunique(dropna=True))
            for column in df.columns
        ],
    })

    quality.to_csv(REPORT_DIR / "column_quality.csv", index=False)

    duplicate_rows = int(df.duplicated(subset=list(
        column for column in df.columns if column != "Duration_numeric"
    )).sum())

    invalid_start = int(df["Start Timestamp"].isna().sum())
    invalid_end = int(df["End Timestamp"].isna().sum())

    reversed_timestamps = int(
        (
            df["Start Timestamp"].notna()
            & df["End Timestamp"].notna()
            & (df["End Timestamp"] < df["Start Timestamp"])
        ).sum()
    )

    duration_seconds = (
        df["End Timestamp"] - df["Start Timestamp"]
    ).dt.total_seconds()

    negative_calculated_duration = int((duration_seconds < 0).sum())
    zero_calculated_duration = int((duration_seconds == 0).sum())

    case_count = int(df["case_id"].nunique(dropna=True))
    missing_case_ids = int(df["case_id"].isna().sum())
    missing_activities = int(df["activity"].isna().sum())

    activity_summary = (
        df["activity"]
        .fillna("[MISSING ACTIVITY]")
        .value_counts(dropna=False)
        .rename_axis("activity")
        .reset_index(name="event_count")
    )
    activity_summary.to_csv(
        REPORT_DIR / "activity_summary.csv", index=False
    )

    if "Role" in df.columns:
        role_summary = (
            df["Role"]
            .fillna("[MISSING ROLE]")
            .value_counts(dropna=False)
            .rename_axis("role")
            .reset_index(name="event_count")
        )
        role_summary.to_csv(
            REPORT_DIR / "role_summary.csv", index=False
        )

    if "CTR_TYPE" in df.columns:
        container_type_summary = (
            df["CTR_TYPE"]
            .fillna("[MISSING TYPE]")
            .value_counts(dropna=False)
            .rename_axis("container_type")
            .reset_index(name="event_count")
        )
        container_type_summary.to_csv(
            REPORT_DIR / "container_type_summary.csv", index=False
        )

    timestamp_summary = {
        "earliest_start_timestamp": (
            str(df["Start Timestamp"].min())
            if df["Start Timestamp"].notna().any() else None
        ),
        "latest_start_timestamp": (
            str(df["Start Timestamp"].max())
            if df["Start Timestamp"].notna().any() else None
        ),
        "earliest_end_timestamp": (
            str(df["End Timestamp"].min())
            if df["End Timestamp"].notna().any() else None
        ),
        "latest_end_timestamp": (
            str(df["End Timestamp"].max())
            if df["End Timestamp"].notna().any() else None
        ),
    }

    report = {
        "project": "PortPulse AI",
        "source_file": DATA_FILE.name,
        "sheet": "Sheet1",
        "row_count": original_rows,
        "column_count": original_columns,
        "columns": [str(column) for column in df.columns
                    if column != "Duration_numeric"],
        "case_count": case_count,
        "missing_case_ids": missing_case_ids,
        "missing_activities": missing_activities,
        "exact_duplicate_rows": duplicate_rows,
        "missing_start_timestamps": invalid_start,
        "missing_or_invalid_end_timestamps": invalid_end,
        "end_before_start_rows": reversed_timestamps,
        "negative_calculated_duration_rows": negative_calculated_duration,
        "zero_calculated_duration_rows": zero_calculated_duration,
        "duration_values_not_parsed": int(df["Duration_numeric"].isna().sum()),
        "timestamp_range": timestamp_summary,
        "missing_values_by_column": {
            str(column): int(missing_counts[column])
            for column in missing_counts.index
            if column != "Duration_numeric"
        },
        "missing_percentages_by_column": {
            str(column): round(float(missing_percentages[column]), 2)
            for column in missing_percentages.index
            if column != "Duration_numeric"
        },
    }

    with open(
        REPORT_DIR / "dataset_audit.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    with open(
        REPORT_DIR / "dataset_audit.txt",
        "w",
        encoding="utf-8"
    ) as file:
        file.write("PORTPULSE AI — DATASET AUDIT\n")
        file.write("=" * 36 + "\n\n")

        for key, value in report.items():
            file.write(f"{key}: {value}\n")

    print("\nAudit completed.")
    print(f"Rows: {original_rows:,}")
    print(f"Columns: {original_columns}")
    print(f"Unique case IDs: {case_count:,}")
    print(f"Exact duplicate rows: {duplicate_rows:,}")
    print(f"Missing/invalid start timestamps: {invalid_start:,}")
    print(f"Missing/invalid end timestamps: {invalid_end:,}")
    print(f"End before start: {reversed_timestamps:,}")
    print(f"Reports saved to: {REPORT_DIR}")


if __name__ == "__main__":
    main()
