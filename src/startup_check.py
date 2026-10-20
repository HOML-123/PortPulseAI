from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
required = [
    "app.py",
    "pages/1_Risk_Dashboard.py",
    "pages/2_Container_Journey.py",
    "pages/3_Bottleneck_Analysis.py",
    "pages/4_Recovery_Simulation.py",
    "pages/5_Recovery_Recommendations.py",
    "src/risk_dashboard.py",
    "src/container_journey.py",
    "src/bottleneck_dashboard.py",
    "src/recovery_simulation.py",
    "src/recovery_recommender.py",
    "data/raw",
    "data/processed",
    "outputs/reports",
    "models",]
missing = [item for item in required if not (ROOT / item).exists()]
print("PORTPULSE AI STARTUP CHECK")
print(f"Python: {sys.version.split()[0]}")
print(f"Project: {ROOT}")
if missing:
    print("\nCHECK FAILED - Missing components:")
    for item in missing:
        print(f"- {item}")
    sys.exit(1)
print(f"\nCHECK PASSED - All {len(required)} components found.")
print("Launch the application with: streamlit run app.py")
