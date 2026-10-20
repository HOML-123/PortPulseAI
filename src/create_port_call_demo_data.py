from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "demo" / "port_call_milestones_demo.csv"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
base = pd.Timestamp("2026-10-10 00:00:00")
rows = []
vessels = [
    "MV Ocean Crest", "MV Blue Horizon", "MV Pacific Star",
    "MV Eastern Tide", "MV Silver Wave", "MV Coral Bay",
    "MV Atlantic Pearl", "MV Northern Light"]
for i in range(24):
    eta = base + pd.Timedelta(hours=i * 4)
    berth = f"Berth {i % 3 + 1}"
    estimated_berthing = eta + pd.Timedelta(hours=2)
    estimated_departure = estimated_berthing + pd.Timedelta(hours=18)
    completed = i < 14
    arrival_delay = [1, 3, -1, 5, 0, 2, 6][i % 7]
    berthing_delay = [2, 5, 1, 8, 0, 4, 7][i % 7]
    actual_arrival = eta + pd.Timedelta(hours=arrival_delay) if completed else pd.NaT
    actual_berthing = estimated_berthing + pd.Timedelta(hours=berthing_delay) if completed else pd.NaT
    actual_departure = actual_berthing + pd.Timedelta(hours=18 + i % 4) if completed else pd.NaT
    rows.append({
        "port_call_id": f"PC-{1001 + i}",
        "vessel_name": vessels[i % len(vessels)],
        "voyage_number": f"V-{2600 + i}",
        "berth": berth,
        "estimated_arrival": eta,
        "actual_arrival": actual_arrival,
        "estimated_berthing": estimated_berthing,
        "actual_berthing": actual_berthing,
        "estimated_departure": estimated_departure,
        "actual_departure": actual_departure,
        "call_status": "Completed" if completed else "Planned",
        "data_source": "SYNTHETIC_DEMO"})
df = pd.DataFrame(rows)
df.to_csv(OUTPUT, index=False)
print(f"Demo port calls created: {len(df)}")
print(f"Completed calls: {(df['call_status'] == 'Completed').sum()}")
print(f"Planned calls: {(df['call_status'] == 'Planned').sum()}")
print(f"Output: {OUTPUT}")
