
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "outputs" / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

files = {
    "Cleaned events": ROOT / "data/processed/cleaned_events.csv.gz",
    "Valid events": ROOT / "data/processed/valid_events.csv.gz",
    "Container features": ROOT / "data/processed/container_features.csv.gz",
    "Case risk scores": ROOT / "data/processed/case_risk_scores.csv.gz",
    "Model metrics": REPORTS / "baseline_model_metrics.json",
    "Model evaluation": REPORTS / "baseline_model_comparison.csv",
    "Model explanation": REPORTS / "model_explainability_report.json",
}

results = []
for name, path in files.items():
    row = {"Component": name, "Status": "Available" if path.is_file() else "Missing", "Details": ""}
    if path.is_file() and path.suffix == ".gz":
        try:
            data = pd.read_csv(path, compression="gzip", nrows=5)
            row["Details"] = f"Readable CSV; {len(data.columns)} columns"
        except Exception as error:
            row["Status"] = "Unreadable"
            row["Details"] = str(error)[:150]
    elif path.is_file() and path.suffix == ".json":
        try:
            with path.open(encoding="utf-8") as file:
                json.load(file)
            row["Details"] = "Valid JSON"
        except Exception as error:
            row["Status"] = "Unreadable"
            row["Details"] = str(error)[:150]
    results.append(row)

report = pd.DataFrame(results)
report.to_csv(REPORTS / "data_readiness_report.csv", index=False)

print("PORTPULSE AI - DATA READINESS")
print(report.to_string(index=False))
print(f"\nReport saved: {REPORTS / 'data_readiness_report.csv'}")
