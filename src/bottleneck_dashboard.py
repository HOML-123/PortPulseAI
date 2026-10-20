from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from src.ui_theme import apply_page_style, style_plotly

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "processed" / "valid_events.csv.gz"

st.set_page_config(page_title="Bottleneck Analysis | PortPulse AI", page_icon="⚓", layout="wide")
apply_page_style("Operational Intelligence", "Explore historical activity durations and gaps between consecutive recorded events.")

@st.cache_data(show_spinner="Loading event log and calculating activity summaries...")
def analyse_events(path_text, modified_time):
    df = pd.read_csv(path_text, parse_dates=["Start Timestamp", "End Timestamp"], usecols=lambda c: c in {"case_id", "activity", "Start Timestamp", "End Timestamp"})
    required = {"case_id", "activity", "Start Timestamp", "End Timestamp"}
    if not required.issubset(df.columns):
        return None, None, None, f"Missing required columns: {sorted(required - set(df.columns))}"
    df = df.dropna(subset=["case_id", "activity", "Start Timestamp", "End Timestamp"]).copy()
    df["event_hours"] = (df["End Timestamp"] - df["Start Timestamp"]).dt.total_seconds() / 3600
    df = df[df["event_hours"] >= 0].copy()
    duration = df.groupby("activity", as_index=False).agg(Events=("event_hours", "size"), Average_Hours=("event_hours", "mean"), Median_Hours=("event_hours", "median"), P95_Hours=("event_hours", lambda x: x.quantile(0.95))).sort_values("Median_Hours", ascending=False)
    df = df.sort_values(["case_id", "Start Timestamp"])
    df["previous_end"] = df.groupby("case_id")["End Timestamp"].shift()
    df["gap_hours"] = (df["Start Timestamp"] - df["previous_end"]).dt.total_seconds() / 3600
    gaps = df.dropna(subset=["gap_hours"])
    gap_summary = gaps[gaps["gap_hours"] >= 0].groupby("activity", as_index=False).agg(Cases_With_Gaps=("case_id", "nunique"), Average_Gap_Hours=("gap_hours", "mean"), Median_Gap_Hours=("gap_hours", "median")).sort_values("Median_Gap_Hours", ascending=False)
    return df, duration, gap_summary, None

if not EVENTS.is_file():
    st.error("Event data not found. Run: python src\\clean_data.py")
    st.stop()
df, duration, gap_summary, error = analyse_events(str(EVENTS), EVENTS.stat().st_mtime)
if error:
    st.error(error)
    st.stop()

st.caption("This page summarises recorded event-log patterns; it does not identify verified causes of terminal delays.")
a, b, c = st.columns(3)
a.metric("Valid events", f"{len(df):,}")
b.metric("Activities", f"{df['activity'].nunique():,}")
c.metric("Cases", f"{df['case_id'].nunique():,}")
st.divider()
st.subheader("Activity duration")
st.caption("Activities are ranked by median recorded duration.")
if not duration.empty:
    top_duration = duration.head(15).sort_values("Median_Hours")
    fig = px.bar(top_duration, x="Median_Hours", y="activity", orientation="h", hover_data=["Events", "Average_Hours", "P95_Hours"], labels={"Median_Hours":"Median duration (hours)", "activity":"Activity"}, template="plotly_white")
    fig.update_traces(marker_color="#087F8C")
    st.plotly_chart(style_plotly(fig, max(360, 24 * len(top_duration) + 100)), use_container_width=True)
    with st.expander("View full activity duration table"):
        st.dataframe(duration, use_container_width=True, hide_index=True)
else:
    st.info("No valid activity durations are available.")
st.divider()
st.subheader("Time between recorded activities")
st.caption("Only non-negative gaps are included in this summary.")
if not gap_summary.empty:
    top_gaps = gap_summary.head(15).sort_values("Median_Gap_Hours")
    fig = px.bar(top_gaps, x="Median_Gap_Hours", y="activity", orientation="h", hover_data=["Cases_With_Gaps", "Average_Gap_Hours"], labels={"Median_Gap_Hours":"Median preceding gap (hours)", "activity":"Next activity"}, template="plotly_white")
    fig.update_traces(marker_color="#205568")
    st.plotly_chart(style_plotly(fig, max(360, 24 * len(top_gaps) + 100)), use_container_width=True)
    with st.expander("View full time-gap table"):
        st.dataframe(gap_summary, use_container_width=True, hide_index=True)
else:
    st.info("No non-negative gaps could be calculated from the available timestamps.")
left, right = st.columns(2)
with left:
    st.download_button("Download activity duration CSV", duration.to_csv(index=False).encode("utf-8"), "activity_duration_summary.csv", "text/csv", use_container_width=True)
with right:
    st.download_button("Download time-gap CSV", gap_summary.to_csv(index=False).encode("utf-8"), "activity_gap_summary.csv", "text/csv", use_container_width=True)
st.caption("These are historical event-log patterns, not confirmed causes of terminal delays. A time gap is not automatically operational waiting.")
