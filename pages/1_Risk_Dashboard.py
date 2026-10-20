from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parent.parent
runpy.run_path(str(ROOT / "src" / "risk_dashboard.py"))
