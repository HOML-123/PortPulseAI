
from pathlib import Path
import pandas as pd
import csv

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "outputs" / "reports" / "final_project_test.csv"

files = {
    "Main app": "app.py",
    "Risk dashboard": "src/risk_dashboard.py",
    "Container journey": "src/container_journey.py",
    "Bottleneck analysis": "src/bottleneck_dashboard.py",
    "Recovery simulation": "src/recovery_simulation.py",
    "Recovery recommendations": "src/recovery_recommender.py",
    "Risk page": "pages/1_Risk_Dashboard.py",
    "Journey page": "pages/2_Container_Journey.py",
    "Bottleneck page": "pages/3_Bottleneck_Analysis.py",
    "Simulation page": "pages/4_Recovery_Simulation.py",
    "Recommendations page": "pages/5_Recovery_Recommendations.py",
    "Cleaned events": "data/processed/cleaned_events.csv.gz",
    "Valid events": "data/processed/valid_events.csv.gz",
    "Container features": "data/processed/container_features.csv.gz",
    "Case risk scores": "data/processed/case_risk_scores.csv.gz",
}

results = []
for name, relative in files.items():
    path = ROOT / relative
    status, details = ("PASS", "File found") if path.is_file() else ("FAIL", "File missing")
    if status == "PASS" and path.suffix == ".gz":
        try:
            sample = pd.read_csv(path, compression="gzip", nrows=3)
            details = f"Readable; {len(sample.columns)} columns"
        except Exception as error:
            status, details = "FAIL", str(error)[:120]
    results.append({"Component": name, "Status": status, "Details": details})

REPORT.parent.mkdir(parents=True, exist_ok=True)
with REPORT.open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=["Component", "Status", "Details"])
    writer.writeheader()
    writer.writerows(results)

passed = sum(row["Status"] == "PASS" for row in results)
print(f"Passed: {passed}/{len(results)}")
for row in results:
    print(f"{row['Status']}: {row['Component']} - {row['Details']}")
print(f"\nReport: {REPORT}")
