
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parent.parent
checks = {
    "Main application": "app.py",
    "Risk dashboard": "src/risk_dashboard.py",
    "Container journey": "src/container_journey.py",
    "Bottleneck analysis": "src/bottleneck_dashboard.py",
    "Recovery simulation": "src/recovery_simulation.py",
    "Recovery recommendations": "src/recovery_recommender.py",
    "Risk dashboard page": "pages/1_Risk_Dashboard.py",
    "Container journey page": "pages/2_Container_Journey.py",
    "Bottleneck page": "pages/3_Bottleneck_Analysis.py",
    "Recovery simulation page": "pages/4_Recovery_Simulation.py",
    "Recommendations page": "pages/5_Recovery_Recommendations.py",
    "Source dataset": "data/raw/Dataset of Dwelling Time Process Fix.xlsx",
    "Cleaned events": "data/processed/cleaned_events.csv.gz",
    "Valid events": "data/processed/valid_events.csv.gz",
    "Container features": "data/processed/container_features.csv.gz",
    "Case risk scores": "data/processed/case_risk_scores.csv.gz",
    "Baseline model": "models/baseline_elapsed_time_classifier.joblib",
}

results = [{"Component": name, "Status": "PASS" if (ROOT / path).is_file() else "MISSING", "Path": path} for name, path in checks.items()]
report = ROOT / "outputs" / "reports" / "integration_test_report.csv"
report.parent.mkdir(parents=True, exist_ok=True)

with report.open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=["Component", "Status", "Path"])
    writer.writeheader()
    writer.writerows(results)

passed = sum(item["Status"] == "PASS" for item in results)
print(f"Integration check: {passed}/{len(results)} files found")
print(f"Report saved: {report}")
for item in results:
    print(f"{item['Status']}: {item['Component']}")
