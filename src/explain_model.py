
from pathlib import Path
import json
import warnings

import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "baseline_elapsed_time_classifier.joblib"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "outputs" / "reports"

COEFFICIENTS_PATH = PROCESSED_DIR / "model_feature_coefficients.csv"
REPORT_JSON_PATH = REPORT_DIR / "model_explainability_report.json"
REPORT_TEXT_PATH = REPORT_DIR / "model_explainability_report.txt"
CHART_PATH = REPORT_DIR / "model_feature_influence.png"


def stop(message):
    raise SystemExit(f"\nDay 9 cannot continue: {message}")


def get_feature_names(pipeline, preprocessor, classifier, coefficient_count):
    candidates = []

    try:
        candidates.append(pipeline[:-1].get_feature_names_out())
    except (AttributeError, ValueError, TypeError):
        pass

    try:
        candidates.append(preprocessor.get_feature_names_out())
    except (AttributeError, ValueError, TypeError):
        pass

    for names in candidates:
        names = [str(name) for name in names]
        if len(names) == coefficient_count:
            return names

    return [f"feature_{index + 1}" for index in range(coefficient_count)]


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not MODEL_PATH.exists():
        stop(
            f"Trained model not found at {MODEL_PATH}. "
            "Run python src\\train_baseline_model.py first."
        )

    print("Loading the trained model...")
    pipeline = joblib.load(MODEL_PATH)

    if not hasattr(pipeline, "named_steps"):
        stop("The saved model is not a supported scikit-learn pipeline.")

    steps = list(pipeline.named_steps.values())
    classifier = steps[-1]

    if not hasattr(classifier, "coef_"):
        stop(
            "The final pipeline step does not expose model coefficients. "
            "This Day 9 script expects the Logistic Regression model from Day 7."
        )

    if not hasattr(classifier, "classes_"):
        stop("The classifier does not contain its trained class labels.")

    if len(classifier.classes_) != 2:
        stop("This script currently supports binary classification only.")

    if not hasattr(classifier, "coef_") or classifier.coef_.shape[0] != 1:
        stop("The model does not have the expected binary coefficient structure.")

    preprocessor = None

    for name, step in pipeline.named_steps.items():
        if step is classifier:
            break
        if hasattr(step, "get_feature_names_out"):
            preprocessor = step

    if preprocessor is None:
        stop("Could not locate the preprocessing step in the saved pipeline.")

    coefficients = np.asarray(classifier.coef_[0], dtype=float)
    feature_names = get_feature_names(
        pipeline, preprocessor, classifier, len(coefficients)
    )

    if len(feature_names) != len(coefficients):
        stop("The feature names do not match the model coefficient count.")

    positive_class = classifier.classes_[1]
    negative_class = classifier.classes_[0]

    odds_ratios = np.exp(np.clip(coefficients, -50, 50))

    results = pd.DataFrame(
        {
            "feature": feature_names,
            "coefficient": coefficients,
            "odds_ratio": odds_ratios,
            "direction": np.where(
                coefficients > 0,
                "Higher odds of positive class",
                np.where(
                    coefficients < 0,
                    "Lower odds of positive class",
                    "No linear effect"
                )
            ),
            "absolute_coefficient": np.abs(coefficients)
        }
    )

    results = results.sort_values(
        "absolute_coefficient", ascending=False
    ).reset_index(drop=True)

    results.to_csv(COEFFICIENTS_PATH, index=False)

    positive_features = (
        results[results["coefficient"] > 0]
        .sort_values("coefficient", ascending=False)
        .head(10)
    )

    negative_features = (
        results[results["coefficient"] < 0]
        .sort_values("coefficient", ascending=True)
        .head(10)
    )

    chart_data = pd.concat(
        [
            negative_features.sort_values("coefficient"),
            positive_features.sort_values("coefficient")
        ]
    ).drop_duplicates(subset=["feature"])

    if not chart_data.empty:
        chart_height = max(5, len(chart_data) * 0.38)
        fig, ax = plt.subplots(figsize=(12, chart_height))

        ax.barh(
            chart_data["feature"],
            chart_data["coefficient"]
        )

        ax.axvline(0, linewidth=1)
        ax.set_title("PortPulse AI: Logistic Regression Feature Coefficients")
        ax.set_xlabel(
            "Coefficient (positive = higher odds of the positive class)"
        )
        ax.set_ylabel("Transformed model feature")
        ax.tick_params(axis="y", labelsize=8)
        fig.tight_layout()
        fig.savefig(CHART_PATH, dpi=180, bbox_inches="tight")
        plt.close(fig)

    def feature_records(frame):
        records = []
        for _, row in frame.iterrows():
            records.append(
                {
                    "feature": str(row["feature"]),
                    "coefficient": round(float(row["coefficient"]), 6),
                    "odds_ratio": round(float(row["odds_ratio"]), 6),
                    "direction": str(row["direction"])
                }
            )
        return records

    report = {
        "project": "PortPulse AI",
        "analysis": "Logistic Regression coefficient-based explainability",
        "model_file": str(MODEL_PATH.relative_to(ROOT)),
        "positive_class": str(positive_class),
        "negative_class": str(negative_class),
        "number_of_model_features": int(len(results)),
        "number_of_positive_coefficients": int(
            (results["coefficient"] > 0).sum()
        ),
        "number_of_negative_coefficients": int(
            (results["coefficient"] < 0).sum()
        ),
        "top_features_by_absolute_coefficient": feature_records(
            results.head(10)
        ),
        "strongest_positive_coefficients": feature_records(
            positive_features
        ),
        "strongest_negative_coefficients": feature_records(
            negative_features
        ),
        "interpretation_limitations": [
            "The target is a provisional high-elapsed-time label, not a validated operational delay label.",
            "Coefficients describe model associations, not causal effects.",
            "Numeric features may be standardised, so their coefficients refer to the transformed feature scale.",
            "Categorical coefficients depend on the encoding and reference categories.",
            "Correlated features can make individual coefficient interpretations unstable.",
            "Odds ratios describe conditional model associations and should not be interpreted as percentage changes in elapsed time."
        ],
        "outputs": {
            "feature_coefficients": str(COEFFICIENTS_PATH.relative_to(ROOT)),
            "chart": str(CHART_PATH.relative_to(ROOT)),
            "json_report": str(REPORT_JSON_PATH.relative_to(ROOT)),
            "text_report": str(REPORT_TEXT_PATH.relative_to(ROOT))
        }
    }

    with open(REPORT_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    lines = [
        "PORTPULSE AI - DAY 9 MODEL EXPLAINABILITY REPORT",
        "=" * 55,
        "",
        f"Model file: {MODEL_PATH.relative_to(ROOT)}",
        f"Positive class: {positive_class}",
        f"Negative class: {negative_class}",
        f"Total model features: {len(results)}",
        f"Positive coefficients: {report['number_of_positive_coefficients']}",
        f"Negative coefficients: {report['number_of_negative_coefficients']}",
        "",
        "TOP FEATURES BY ABSOLUTE COEFFICIENT",
        "-" * 40
    ]

    for _, row in results.head(10).iterrows():
        lines.append(
            f"{row['feature']}: coefficient={row['coefficient']:.6f}, "
            f"odds ratio={row['odds_ratio']:.6f}"
        )

    lines.extend(
        [
            "",
            "FEATURES ASSOCIATED WITH HIGHER ODDS OF THE POSITIVE CLASS",
            "-" * 55
        ]
    )

    if positive_features.empty:
        lines.append("No positive coefficients were found.")
    else:
        for _, row in positive_features.iterrows():
            lines.append(
                f"{row['feature']}: coefficient={row['coefficient']:.6f}, "
                f"odds ratio={row['odds_ratio']:.6f}"
            )

    lines.extend(
        [
            "",
            "FEATURES ASSOCIATED WITH LOWER ODDS OF THE POSITIVE CLASS",
            "-" * 55
        ]
    )

    if negative_features.empty:
        lines.append("No negative coefficients were found.")
    else:
        for _, row in negative_features.iterrows():
            lines.append(
                f"{row['feature']}: coefficient={row['coefficient']:.6f}, "
                f"odds ratio={row['odds_ratio']:.6f}"
            )

    lines.extend(
        [
            "",
            "INTERPRETATION LIMITATIONS",
            "-" * 30,
            "1. The target is a provisional high-elapsed-time label.",
            "2. Coefficients show model associations, not causes.",
            "3. Numeric coefficients refer to transformed feature scales.",
            "4. Categorical effects depend on encoding and reference categories.",
            "5. Correlated inputs can make individual coefficients unstable.",
            "6. Odds ratios are not percentage changes in elapsed time.",
            "",
            "OUTPUT FILES",
            "-" * 20,
            str(COEFFICIENTS_PATH.relative_to(ROOT)),
            str(CHART_PATH.relative_to(ROOT)),
            str(REPORT_JSON_PATH.relative_to(ROOT)),
            str(REPORT_TEXT_PATH.relative_to(ROOT))
        ]
    )

    REPORT_TEXT_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )

    print("\nDay 9 explainability analysis completed.")
    print(f"Feature table: {COEFFICIENTS_PATH}")
    print(f"Feature chart: {CHART_PATH}")
    print(f"Text report: {REPORT_TEXT_PATH}")
    print(f"JSON report: {REPORT_JSON_PATH}")


if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("default")
        main()
