from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from src.ui_theme import apply_page_style, style_plotly

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed" / "valid_events.csv.gz"

st.set_page_config(page_title="Container Journey | PortPulse AI", page_icon="⚓", layout="wide")
apply_page_style("Container Journey", "Trace recorded activity sequences and examine the time between consecutive events.")

@st.cache_data(show_spinner="Loading event log...")
def load_events(path_text, modified_time):
    frame = pd.read_csv(path_text, parse_dates=["Start Timestamp", "End Timestamp"])
    needed = [c for c in ["case_id", "activity", "Start Timestamp", "End Timestamp", "Role", "Duration", "CTR_SIZE", "CTR_TYPE", "YARD_BLOCK", "YARD_SLOT", "JOB_DEL_DOCTYPE"] if c in frame.columns]
    return frame[needed]

if not DATA.is_file():
    st.error("Event data not found. Run: python src\\clean_data.py")
    st.stop()
df = load_events(str(DATA), DATA.stat().st_mtime)
if not {"case_id", "activity"}.issubset(df.columns):
    st.error(f"Required columns are missing. Available columns: {list(df.columns)}")
    st.stop()
df["case_id"] = df["case_id"].astype(str)

st.subheader("Find a case")
query = st.text_input("Search case ID", placeholder="Enter all or part of a case ID")
if not query.strip():
    st.info("Enter a case ID to explore its recorded journey.")
    st.stop()
# Search before sorting so the entire event log is not repeatedly sorted on each rerun.
matches = df[df["case_id"].str.contains(query.strip(), case=False, na=False, regex=False)]
if matches.empty:
    st.warning("No matching case found.")
    st.stop()
case_ids = sorted(matches["case_id"].unique())
st.caption(f"{len(case_ids):,} matching case IDs")
selected = st.selectbox("Select a case", case_ids)
journey = matches[matches["case_id"] == selected].copy().sort_values("Start Timestamp", na_position="last")
journey["Gap (hours)"] = (journey["Start Timestamp"] - journey["End Timestamp"].shift(1)).dt.total_seconds() / 3600
valid_times = journey.dropna(subset=["Start Timestamp"])
elapsed = None
if not valid_times.empty and valid_times["End Timestamp"].notna().any():
    elapsed = (valid_times["End Timestamp"].max() - valid_times["Start Timestamp"].min()).total_seconds() / 3600

a, b, c = st.columns(3)
a.metric("Recorded events", f"{len(journey):,}")
b.metric("Activities", f"{journey['activity'].nunique():,}")
c.metric("First-to-last span", f"{elapsed:,.1f} hours" if elapsed is not None else "Unavailable")
st.divider()
st.subheader("Recorded activity timeline")
if not valid_times.empty:
    fig = px.scatter(valid_times, x="Start Timestamp", y="activity", color="Role" if "Role" in valid_times.columns else None, hover_data=[c for c in ["End Timestamp", "Duration"] if c in valid_times.columns], template="plotly_white", labels={"Start Timestamp":"Recorded start time", "activity":"Activity"})
    fig.update_traces(marker=dict(size=10, opacity=0.82))
    st.plotly_chart(style_plotly(fig, 430), use_container_width=True)
else:
    st.info("No valid start timestamps are available for this case.")
with st.expander("View all recorded event details"):
    st.dataframe(journey, use_container_width=True, hide_index=True)
st.subheader("Time between recorded activities")
gaps = journey.dropna(subset=["Gap (hours)"])
if not gaps.empty:
    st.dataframe(gaps[[c for c in ["activity", "Start Timestamp", "Gap (hours)"] if c in gaps.columns]], use_container_width=True, hide_index=True)
    st.caption("Positive gaps indicate time between the previous recorded event's end and the next event's start. Negative gaps indicate overlapping recorded times.")
else:
    st.info("Not enough timestamped activities to calculate gaps.")
st.download_button("Download journey CSV", journey.to_csv(index=False).encode("utf-8"), "container_journey.csv", "text/csv", use_container_width=True)
st.caption("This page displays recorded event sequences. Time gaps and elapsed spans are descriptive measures, not verified container dwell times or proof of operational waiting.")
