from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
FILES = {"Dataset audit": "outputs/reports/dataset_audit.txt",
    "Cleaned events": "data/processed/valid_events.csv.gz",
    "Container features": "data/processed/container_features.csv.gz",
    "Activity analysis": "outputs/reports/activity_duration_analysis.csv",
    "Risk scores": "data/processed/case_risk_scores.csv.gz",
    "Baseline model": "models/baseline_elapsed_time_classifier.joblib",
    "Model predictions": "data/processed/baseline_model_test_predictions.csv",
    "Risk dashboard": "src/risk_dashboard.py",
    "Container journey": "src/container_journey.py",
    "Bottleneck analysis": "src/bottleneck_dashboard.py",
    "Recovery simulation": "src/recovery_simulation.py",
    "Recovery recommender": "src/recovery_recommender.py"}
results = []
for name, relative_path in FILES.items():
    path = ROOT / relative_path
    status = "Available" if path.exists() else "Missing"
    details = ""
    if path.exists() and path.suffix == ".gz":
        try:
            details = f"{len(pd.read_csv(path, usecols=lambda c: True, nrows=5).columns)} columns"
        except Exception as error:
            status = "Unreadable"
            details = str(error)
    results.append({"Component": name, "Status": status, "Path": relative_path, "Details": details})
report = pd.DataFrame(results)
output = ROOT / "outputs" / "reports" / "project_health_check.csv"
output.parent.mkdir(parents=True, exist_ok=True)
report.to_csv(output, index=False)
print("\nPORTPULSE AI - PROJECT HEALTH CHECK")
print(report[["Component", "Status", "Details"]].to_string(index=False))
print(f"\nReport saved to: {output}")
print(f"Available: {(report['Status'] == 'Available').sum()} / {len(report)}")
print(f"Missing or unreadable: {(report['Status'] != 'Available').sum()}")