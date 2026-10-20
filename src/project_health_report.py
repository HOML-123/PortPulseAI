
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "outputs" / "reports"

checks = {
    "Main application": "app.py",
    "Risk dashboard": "src/risk_dashboard.py",
    "Container journey": "src/container_journey.py",
    "Bottleneck analysis": "src/bottleneck_dashboard.py",
    "Recovery simulation": "src/recovery_simulation.py",
    "Recovery recommendations": "src/recovery_recommender.py",
    "Risk navigation page": "pages/1_Risk_Dashboard.py",
    "Journey navigation page": "pages/2_Container_Journey.py",
    "Bottleneck navigation page": "pages/3_Bottleneck_Analysis.py",
    "Simulation navigation page": "pages/4_Recovery_Simulation.py",
    "Recommendations navigation page": "pages/5_Recovery_Recommendations.py",
    "Cleaned events": "data/processed/cleaned_events.csv.gz",
    "Valid events": "data/processed/valid_events.csv.gz",
    "Container features": "data/processed/container_features.csv.gz",
    "Case risk scores": "data/processed/case_risk_scores.csv.gz",
    "Baseline model": "models/baseline_elapsed_time_classifier.joblib",
    "Baseline metrics": "outputs/reports/baseline_model_metrics.json",
    "Integration test": "outputs/reports/integration_test_report.csv",
    "Data readiness report": "outputs/reports/data_readiness_report.csv",
}

results = []
for name, relative in checks.items():
    path = ROOT / relative
    status = "PASS" if path.is_file() else "MISSING"
    details = "File found" if status == "PASS" else "File not found"
    if status == "PASS" and path.suffix == ".gz":
        try:
            sample = pd.read_csv(path, compression="gzip", nrows=3)
            details = f"Readable CSV; {len(sample.columns)} columns"
        except Exception as error:
            status, details = "ERROR", str(error)[:120]
    results.append({"Component": name, "Status": status, "Details": details})

report = pd.DataFrame(results)
REPORTS.mkdir(parents=True, exist_ok=True)
report.to_csv(REPORTS / "project_health_report.csv", index=False)

print("PORTPULSE AI - PROJECT HEALTH")
print(report.to_string(index=False))
print(f"\nPassed: {(report['Status'] == 'PASS').sum()}/{len(report)}")
print(f"Report: {REPORTS / 'project_health_report.csv'}")
