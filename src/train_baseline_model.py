from pathlib import Path
import json
import joblib
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parent.parent
FEATURES_FILE = ROOT / "data" / "processed" / "container_features.csv.gz"
OUTPUT_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "outputs" / "reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_PERCENTILE = 0.95
TEST_FRACTION = 0.20
MINIMUM_ROWS = 100

NUMERIC_ALIASES = {
    "CTR_SIZE": ["ctr_size", "representative_ctr_size"],
    "GROSS": ["gross", "representative_gross"]
}

CATEGORICAL_ALIASES = {
    "CTR_TYPE": ["ctr_type", "representative_ctr_type"],
    "JOB_DEL_DOCTYPE": [
        "job_del_doctype",
        "representative_job_del_doctype"
    ]
}


def normalise_name(name):
    return "".join(
        character.lower()
        for character in str(name)
        if character.isalnum()
    )


def find_existing_column(columns, aliases):
    lookup = {
        normalise_name(column): column
        for column in columns
    }

    for alias in aliases:
        match = lookup.get(normalise_name(alias))
        if match is not None:
            return match

    return None


def main():
    if not FEATURES_FILE.exists():
        raise FileNotFoundError(
            f"Feature file not found: {FEATURES_FILE}\n"
            "Run python src\\feature_engineering.py first."
        )

    print("Loading case-level features...")

    df = pd.read_csv(
        FEATURES_FILE,
        compression="gzip",
        parse_dates=["case_start_timestamp"],
        low_memory=False
    )

    df.columns = [str(column).strip() for column in df.columns]

    print("Available columns:")
    print(", ".join(df.columns))

    required_columns = [
        "case_id",
        "case_start_timestamp",
        "elapsed_hours"
    ]

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Required columns missing: {missing_columns}\n"
            f"Available columns: {list(df.columns)}"
        )

    df["case_id"] = df["case_id"].astype("string")
    df["case_start_timestamp"] = pd.to_datetime(
        df["case_start_timestamp"],
        errors="coerce"
    )
    df["elapsed_hours"] = pd.to_numeric(
        df["elapsed_hours"],
        errors="coerce"
    )

    df = df.dropna(
        subset=[
            "case_id",
            "case_start_timestamp",
            "elapsed_hours"
        ]
    ).copy()

    df = df.loc[df["elapsed_hours"] >= 0].copy()
    df = df.drop_duplicates(subset=["case_id"], keep="first")

    df = df.sort_values(
        ["case_start_timestamp", "case_id"],
        kind="mergesort"
    ).reset_index(drop=True)

    if len(df) < MINIMUM_ROWS:
        raise ValueError(
            f"Only {len(df)} usable cases were found. "
            f"At least {MINIMUM_ROWS} are required."
        )

    print(f"Usable cases: {len(df):,}")

    numeric_features = []
    categorical_features = []
    selected_source_columns = {}

    for feature_name, aliases in NUMERIC_ALIASES.items():
        source_column = find_existing_column(df.columns, aliases)

        if source_column is not None:
            df[feature_name] = pd.to_numeric(
                df[source_column],
                errors="coerce"
            )
            numeric_features.append(feature_name)
            selected_source_columns[feature_name] = source_column

    for feature_name, aliases in CATEGORICAL_ALIASES.items():
        source_column = find_existing_column(df.columns, aliases)

        if source_column is not None:
            # Fixed: convert to standard strings and handle missing values cleanly for sklearn
            cleaned_series = df[source_column].astype(str).str.strip()
            cleaned_series = cleaned_series.replace(["", "nan", "None", "<NA>"], None)
            df[feature_name] = cleaned_series
            
            categorical_features.append(feature_name)
            selected_source_columns[feature_name] = source_column

    df["start_hour"] = df["case_start_timestamp"].dt.hour
    df["start_day_of_week"] = df["case_start_timestamp"].dt.dayofweek
    df["start_month"] = df["case_start_timestamp"].dt.month

    numeric_features.extend([
        "start_hour",
        "start_day_of_week",
        "start_month"
    ])

    feature_columns = numeric_features + categorical_features

    if not feature_columns:
        raise ValueError(
            "No usable input features could be created. "
            f"Available columns: {list(df.columns)}"
        )

    print(f"Selected source columns: {selected_source_columns}")
    print("Added timestamp features: start_hour, start_day_of_week, start_month")
    print(f"Model input features: {feature_columns}")

    split_index = int(len(df) * (1 - TEST_FRACTION))

    if split_index <= 0 or split_index >= len(df):
        raise ValueError("Unable to create a valid chronological split.")

    train_df = df.iloc[:split_index].copy()
    test_df = df.iloc[split_index:].copy()

    threshold = float(
        train_df["elapsed_hours"].quantile(TARGET_PERCENTILE)
    )

    train_df["target_long_elapsed"] = (
        train_df["elapsed_hours"] > threshold
    ).astype("int8")

    test_df["target_long_elapsed"] = (
        test_df["elapsed_hours"] > threshold
    ).astype("int8")

    if train_df["target_long_elapsed"].nunique() < 2:
        raise ValueError(
            "The training target contains only one class. "
            "The classifier cannot train on a single class."
        )

    X_train = train_df[feature_columns].copy()
    X_test = test_df[feature_columns].copy()

    y_train = train_df["target_long_elapsed"]
    y_test = test_df["target_long_elapsed"]

    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler())
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore"))
        ]
    )

    transformers = []

    if numeric_features:
        transformers.append(
            ("numeric", numeric_pipeline, numeric_features)
        )

    if categorical_features:
        transformers.append(
            ("categorical", categorical_pipeline, categorical_features)
        )

    preprocessing = ColumnTransformer(
        transformers=transformers,
        remainder="drop"
    )

    model = Pipeline(
        steps=[
            ("preprocessing", preprocessing),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=42
                )
            )
        ]
    )

    print("Training logistic regression...")

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]

    auc = None

    if y_test.nunique() == 2:
        auc = float(roc_auc_score(y_test, probabilities))

    metrics = {
        "project": "PortPulse AI",
        "model": "Logistic Regression",
        "target_definition": (
            "Observed case elapsed hours greater than the "
            "training-set 95th percentile."
        ),
        "target_percentile": TARGET_PERCENTILE,
        "training_elapsed_hours_threshold": threshold,
        "total_usable_cases": int(len(df)),
        "training_cases": int(len(train_df)),
        "test_cases": int(len(test_df)),
        "training_start": str(train_df["case_start_timestamp"].min()),
        "training_end": str(train_df["case_start_timestamp"].max()),
        "test_start": str(test_df["case_start_timestamp"].min()),
        "test_end": str(test_df["case_start_timestamp"].max()),
        "input_features": feature_columns,
        "selected_source_columns": selected_source_columns,
        "training_positive_cases": int(y_train.sum()),
        "training_negative_cases": int((y_train == 0).sum()),
        "test_positive_cases": int(y_test.sum()),
        "test_negative_cases": int((y_test == 0).sum()),
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision": float(
            precision_score(y_test, predictions, zero_division=0)
        ),
        "recall": float(
            recall_score(y_test, predictions, zero_division=0)
        ),
        "f1_score": float(
            f1_score(y_test, predictions, zero_division=0)
        ),
        "roc_auc": auc,
        "confusion_matrix_labels": [
            "not_above_training_threshold",
            "above_training_threshold"
        ],
        "confusion_matrix": confusion_matrix(
            y_test,
            predictions,
            labels=[0, 1]
        ).tolist(),
        "model_training_completed": True,
        "limitations": [
            "This is a provisional retrospective classification task.",
            "Elapsed time is not confirmed true container dwell time.",
            "The percentile threshold is not a validated operational delay threshold.",
            "Timestamp features describe when a case started and may reflect historical patterns.",
            "Available attributes require confirmation of availability at prediction time.",
            "The model must be compared with a simple baseline before claiming value."
        ]
    }

    test_results = test_df[
        [
            "case_id",
            "case_start_timestamp",
            "elapsed_hours",
            "target_long_elapsed"
        ]
    ].copy()

    test_results["predicted_long_elapsed"] = predictions
    test_results["predicted_probability"] = probabilities

    test_results.to_csv(
        OUTPUT_DIR / "baseline_model_test_predictions.csv",
        index=False
    )

    with open(
        REPORT_DIR / "baseline_model_metrics.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(metrics, file, indent=4, ensure_ascii=False)

    with open(
        REPORT_DIR / "baseline_model_metrics.txt",
        "w",
        encoding="utf-8"
    ) as file:
        file.write("PORTPULSE AI — BASELINE MODEL EVALUATION\n")
        file.write("=" * 42 + "\n\n")

        for key, value in metrics.items():
            file.write(f"{key}: {value}\n")

        file.write("\nClassification report:\n")
        file.write(
            classification_report(
                y_test,
                predictions,
                labels=[0, 1],
                target_names=[
                    "Not above threshold",
                    "Above threshold"
                ],
                zero_division=0
            )
        )

    joblib.dump(
        model,
        MODEL_DIR / "baseline_elapsed_time_classifier.joblib"
    )

    print("\nBaseline model training completed.")
    print(f"Training cases: {len(train_df):,}")
    print(f"Test cases: {len(test_df):,}")
    print(f"Training threshold in hours: {threshold:.4f}")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall: {metrics['recall']:.4f}")
    print(f"F1 score: {metrics['f1_score']:.4f}")
    print(f"ROC-AUC: {auc if auc is not None else 'Not available'}")
    print(f"Predictions saved to: {OUTPUT_DIR}")
    print(f"Metrics saved to: {REPORT_DIR}")
    print(f"Model saved to: {MODEL_DIR}")


if __name__ == "__main__":
    main()