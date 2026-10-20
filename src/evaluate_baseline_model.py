
from pathlib import Path
import json
import pandas as pd

from sklearn.dummy import DummyClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report
)


ROOT = Path(__file__).resolve().parent.parent
FEATURES_FILE = ROOT / "data" / "processed" / "container_features.csv.gz"
PREDICTIONS_FILE = ROOT / "data" / "processed" / "baseline_model_test_predictions.csv"
OUTPUT_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "outputs" / "reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_PERCENTILE = 0.95
TEST_FRACTION = 0.20


def calculate_metrics(y_true, y_pred, probabilities=None):
    auc = None

    if probabilities is not None and pd.Series(y_true).nunique() == 2:
        auc = float(roc_auc_score(y_true, probabilities))

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(
            precision_score(y_true, y_pred, zero_division=0)
        ),
        "recall": float(
            recall_score(y_true, y_pred, zero_division=0)
        ),
        "f1_score": float(
            f1_score(y_true, y_pred, zero_division=0)
        ),
        "roc_auc": auc,
        "confusion_matrix": confusion_matrix(
            y_true,
            y_pred,
            labels=[0, 1]
        ).tolist()
    }


def main():
    if not FEATURES_FILE.exists():
        raise FileNotFoundError(
            f"Feature file not found: {FEATURES_FILE}\n"
            "Run python src\\feature_engineering.py first."
        )

    if not PREDICTIONS_FILE.exists():
        raise FileNotFoundError(
            f"Day 7 predictions not found: {PREDICTIONS_FILE}\n"
            "Run python src\\train_baseline_model.py first."
        )

    print("Loading case features and Day 7 test predictions...")

    df = pd.read_csv(
        FEATURES_FILE,
        compression="gzip",
        parse_dates=["case_start_timestamp"],
        low_memory=False
    )

    predictions_df = pd.read_csv(
        PREDICTIONS_FILE,
        parse_dates=["case_start_timestamp"]
    )

    required_feature_columns = [
        "case_id",
        "case_start_timestamp",
        "elapsed_hours"
    ]

    missing_features = [
        column for column in required_feature_columns
        if column not in df.columns
    ]

    if missing_features:
        raise ValueError(
            f"Required feature columns missing: {missing_features}"
        )

    required_prediction_columns = [
        "case_id",
        "elapsed_hours",
        "target_long_elapsed",
        "predicted_long_elapsed",
        "predicted_probability"
    ]

    missing_predictions = [
        column for column in required_prediction_columns
        if column not in predictions_df.columns
    ]

    if missing_predictions:
        raise ValueError(
            f"Required prediction columns missing: {missing_predictions}"
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

    split_index = int(len(df) * (1 - TEST_FRACTION))

    if split_index <= 0 or split_index >= len(df):
        raise ValueError("Unable to recreate a valid chronological split.")

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
            "A meaningful binary comparison cannot be performed."
        )

    print("Recreating the Day 7 test set...")

    expected_test = test_df[
        [
            "case_id",
            "case_start_timestamp",
            "elapsed_hours",
            "target_long_elapsed"
        ]
    ].copy()

    predictions_df["case_id"] = predictions_df["case_id"].astype("string")
    predictions_df["elapsed_hours"] = pd.to_numeric(
        predictions_df["elapsed_hours"],
        errors="coerce"
    )
    predictions_df["target_long_elapsed"] = pd.to_numeric(
        predictions_df["target_long_elapsed"],
        errors="coerce"
    )
    predictions_df["predicted_long_elapsed"] = pd.to_numeric(
        predictions_df["predicted_long_elapsed"],
        errors="coerce"
    )
    predictions_df["predicted_probability"] = pd.to_numeric(
        predictions_df["predicted_probability"],
        errors="coerce"
    )

    if predictions_df["case_id"].duplicated().any():
        raise ValueError(
            "The Day 7 prediction file contains duplicate case IDs."
        )

    aligned = expected_test.merge(
        predictions_df[
            [
                "case_id",
                "target_long_elapsed",
                "predicted_long_elapsed",
                "predicted_probability"
            ]
        ],
        on="case_id",
        how="outer",
        suffixes=("_recreated", "_saved"),
        indicator=True,
        validate="one_to_one"
    )

    if not aligned["_merge"].eq("both").all():
        raise ValueError(
            "The saved Day 7 predictions do not match the recreated "
            "test cases. Rerun Day 7 and then rerun Day 8."
        )

    labels_match = (
        aligned["target_long_elapsed_recreated"].astype(int)
        == aligned["target_long_elapsed_saved"].astype(int)
    )

    if not labels_match.all():
        raise ValueError(
            "The saved Day 7 test labels do not match the recreated "
            "target. Rerun Day 7 and then rerun Day 8."
        )

    y_train = train_df["target_long_elapsed"].astype("int8")
    y_test = aligned["target_long_elapsed_recreated"].astype("int8")
    model_predictions = aligned["predicted_long_elapsed"].astype("int8")
    model_probabilities = aligned["predicted_probability"].astype(float)

    print("Training a most-frequent dummy baseline...")

    dummy = DummyClassifier(strategy="most_frequent")
    dummy.fit(
        train_df[["elapsed_hours"]].iloc[:, :0],
        y_train
    )

    dummy_predictions = dummy.predict(
        test_df[["elapsed_hours"]].iloc[:, :0]
    )

    model_metrics = calculate_metrics(
        y_test,
        model_predictions,
        model_probabilities
    )

    dummy_metrics = calculate_metrics(
        y_test,
        dummy_predictions
    )

    comparison = pd.DataFrame([
        {
            "model": "Day 7 Logistic Regression",
            **model_metrics
        },
        {
            "model": "Most-Frequent Dummy Baseline",
            **dummy_metrics
        }
    ])

    comparison.to_csv(
        OUTPUT_DIR / "model_benchmark_comparison.csv",
        index=False
    )

    print("Classifying test prediction errors...")

    error_analysis = aligned[
        [
            "case_id",
            "case_start_timestamp",
            "elapsed_hours",
            "target_long_elapsed_recreated",
            "predicted_long_elapsed",
            "predicted_probability"
        ]
    ].copy()

    error_analysis = error_analysis.rename(
        columns={
            "target_long_elapsed_recreated": "actual_label"
        }
    )

    error_analysis["actual_label"] = error_analysis[
        "actual_label"
    ].astype(int)

    error_analysis["predicted_long_elapsed"] = error_analysis[
        "predicted_long_elapsed"
    ].astype(int)

    error_analysis["prediction_result"] = "True Negative"

    error_analysis.loc[
        (error_analysis["actual_label"] == 1)
        & (error_analysis["predicted_long_elapsed"] == 1),
        "prediction_result"
    ] = "True Positive"

    error_analysis.loc[
        (error_analysis["actual_label"] == 0)
        & (error_analysis["predicted_long_elapsed"] == 1),
        "prediction_result"
    ] = "False Positive"

    error_analysis.loc[
        (error_analysis["actual_label"] == 1)
        & (error_analysis["predicted_long_elapsed"] == 0),
        "prediction_result"
    ] = "False Negative"

    error_analysis.to_csv(
        OUTPUT_DIR / "model_prediction_error_analysis.csv",
        index=False
    )

    errors_only = error_analysis.loc[
        error_analysis["prediction_result"].isin(
            ["False Positive", "False Negative"]
        )
    ].copy()

    errors_only.to_csv(
        OUTPUT_DIR / "model_misclassified_cases.csv",
        index=False
    )

    result_counts = (
        error_analysis["prediction_result"]
        .value_counts()
        .to_dict()
    )

    f1_difference = (
        model_metrics["f1_score"] - dummy_metrics["f1_score"]
    )

    accuracy_difference = (
        model_metrics["accuracy"] - dummy_metrics["accuracy"]
    )

    if model_metrics["f1_score"] > dummy_metrics["f1_score"]:
        f1_verdict = "Logistic regression has higher F1 than the dummy baseline."
    elif model_metrics["f1_score"] < dummy_metrics["f1_score"]:
        f1_verdict = "Logistic regression has lower F1 than the dummy baseline."
    else:
        f1_verdict = "Logistic regression and the dummy baseline have equal F1."

    report = {
        "project": "PortPulse AI",
        "evaluation": "Chronological held-out test set",
        "usable_cases": int(len(df)),
        "training_cases": int(len(train_df)),
        "test_cases": int(len(test_df)),
        "training_elapsed_time_threshold_hours": threshold,
        "training_positive_cases": int(y_train.sum()),
        "training_negative_cases": int((y_train == 0).sum()),
        "test_positive_cases": int(y_test.sum()),
        "test_negative_cases": int((y_test == 0).sum()),
        "logistic_regression_metrics": model_metrics,
        "dummy_baseline_metrics": dummy_metrics,
        "f1_difference_model_minus_dummy": float(f1_difference),
        "accuracy_difference_model_minus_dummy": float(accuracy_difference),
        "f1_comparison": f1_verdict,
        "prediction_result_counts": {
            str(key): int(value)
            for key, value in result_counts.items()
        },
        "misclassified_test_cases": int(len(errors_only)),
        "target_definition": (
            "Observed case elapsed hours above the 95th percentile "
            "calculated on the training subset."
        ),
        "interpretation_notes": [
            "The dummy baseline predicts the most frequent training class.",
            "The dummy baseline is fitted using training labels only.",
            "Accuracy must be interpreted carefully because the positive class is rare.",
            "Higher F1 alone does not establish operational usefulness.",
            "The target is not confirmed true container dwell time or a validated delay label.",
            "The candidate features must be validated for availability at prediction time."
        ]
    }

    with open(
        REPORT_DIR / "model_benchmark_report.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    with open(
        REPORT_DIR / "model_benchmark_report.txt",
        "w",
        encoding="utf-8"
    ) as file:
        file.write("PORTPULSE AI — MODEL BENCHMARK AND ERROR ANALYSIS\n")
        file.write("=" * 52 + "\n\n")

        for key, value in report.items():
            file.write(f"{key}: {value}\n")

        file.write("\nLogistic regression classification report:\n")
        file.write(
            classification_report(
                y_test,
                model_predictions,
                labels=[0, 1],
                target_names=[
                    "Not above threshold",
                    "Above threshold"
                ],
                zero_division=0
            )
        )

    print("\nDay 8 evaluation completed.")
    print(f"Training cases: {len(train_df):,}")
    print(f"Test cases: {len(test_df):,}")
    print(f"Logistic regression F1: {model_metrics['f1_score']:.4f}")
    print(f"Dummy baseline F1: {dummy_metrics['f1_score']:.4f}")
    print(f"Logistic regression accuracy: {model_metrics['accuracy']:.4f}")
    print(f"Dummy baseline accuracy: {dummy_metrics['accuracy']:.4f}")
    print(f"Misclassified cases: {len(errors_only):,}")
    print(f"Outputs saved to: {OUTPUT_DIR}")
    print(f"Report saved to: {REPORT_DIR}")


if __name__ == "__main__":
    main()
