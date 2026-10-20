from pathlib import Path
import sys
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import port_call_coordination
from src.ui_theme import apply_page_style, style_plotly

DATA = ROOT / "data" / "demo" / "port_call_milestones_demo.csv"
RESULTS = ROOT / "data" / "processed" / "port_call_coordination_results.csv"
CONFLICTS = ROOT / "data" / "processed" / "berth_conflict_pairs.csv"
REPORT = ROOT / "outputs" / "reports" / "port_call_coordination_summary.txt"

st.set_page_config(page_title="Port-Call Coordination | PortPulse AI", page_icon="⚓", layout="wide")
apply_page_style("Port-Call Coordination", "Review vessel milestones, schedule delays and potential berth-window overlaps.")
st.warning("This module uses synthetic demonstration data. Detected overlaps and priority levels are review indicators, not confirmation of live operational conflicts.")

if not DATA.exists():
    st.error("The port-call demonstration dataset was not found.")
    st.code("python src\\create_port_call_demo_data.py", language="bat")
    st.stop()

demo = pd.read_csv(DATA)
left, right = st.columns([3, 1])
with left:
    st.caption(f"Input dataset: {DATA.name} · {len(demo):,} rows")
with right:
    if st.button("Run coordination analysis", type="primary", use_container_width=True):
        try:
            port_call_coordination.main()
            st.success("Coordination analysis completed.")
            st.rerun()
        except Exception as error:
            st.error(f"Analysis failed: {error}")

if not RESULTS.exists():
    st.info("Run the coordination analysis to generate the results.")
    st.subheader("Demonstration data preview")
    st.dataframe(demo.head(20), use_container_width=True, hide_index=True)
    st.stop()

results = pd.read_csv(RESULTS)
conflicts = pd.read_csv(CONFLICTS) if CONFLICTS.exists() else pd.DataFrame()
if results.empty:
    st.info("The coordination output exists but contains no records.")
    st.stop()

for column in ["coordination_priority", "coordination_flags", "recommended_action"]:
    if column not in results.columns:
        results[column] = "Unknown"
total_calls = len(results)
high_count = int(results["coordination_priority"].eq("High").sum())
medium_count = int(results["coordination_priority"].eq("Medium").sum())
low_count = int(results["coordination_priority"].eq("Low").sum())
flagged_mask = ~results["coordination_flags"].fillna("").isin(["No Delay Flag", "Awaiting Actuals"])
flagged_count = int(flagged_mask.sum())
conflict_count = len(conflicts)

st.subheader("Coordination overview")
a, b, c, d, e = st.columns(5)
a.metric("Port calls", f"{total_calls:,}")
b.metric("Calls with flags", f"{flagged_count:,}")
c.metric("High priority", f"{high_count:,}")
d.metric("Medium priority", f"{medium_count:,}")
e.metric("Berth overlap pairs", f"{conflict_count:,}")
st.divider()
overview_tab, schedule_tab, conflicts_tab, report_tab = st.tabs(["Priority overview", "Port-call schedule", "Berth overlaps", "Analysis report"])

with overview_tab:
    st.subheader("Calls by coordination priority")
    priority_counts = results["coordination_priority"].fillna("Unknown").value_counts().reindex(["High", "Medium", "Low", "Unknown"], fill_value=0).rename_axis("Priority").reset_index(name="Port calls")
    fig = px.bar(priority_counts, x="Priority", y="Port calls", color="Priority", color_discrete_map={"High":"#C65353", "Medium":"#D69A35", "Low":"#16877D", "Unknown":"#8496A5"}, template="plotly_white", text_auto=True)
    fig.update_layout(showlegend=False, xaxis_title=None)
    st.plotly_chart(style_plotly(fig, 340), use_container_width=True)
    st.subheader("Calls requiring review")
    review_columns = [c for c in ["port_call_id", "vessel_name", "berth", "coordination_priority", "coordination_flags", "recommended_action"] if c in results.columns]
    review = results.loc[flagged_mask, review_columns]
    if review.empty:
        st.success("No coordination flags were found in this result set.")
    else:
        st.dataframe(review, use_container_width=True, hide_index=True)

with schedule_tab:
    st.subheader("Port-call schedule and milestones")
    selected_priority = st.selectbox("Filter by priority", ["All", "High", "Medium", "Low", "Unknown"], key="coordination_priority_filter")
    filtered = results.copy()
    if selected_priority != "All":
        filtered = filtered[filtered["coordination_priority"].fillna("Unknown") == selected_priority]
    visible_columns = [c for c in ["port_call_id", "vessel_name", "voyage_number", "berth", "estimated_arrival", "actual_arrival", "estimated_berthing", "actual_berthing", "estimated_departure", "actual_departure", "call_status", "arrival_delay_hours", "berthing_delay_hours", "departure_delay_hours", "coordination_priority", "coordination_flags", "recommended_action"] if c in filtered.columns]
    st.caption(f"Showing {len(filtered):,} port calls.")
    st.dataframe(filtered[visible_columns], use_container_width=True, hide_index=True)
    st.download_button("Download coordination results CSV", results.to_csv(index=False).encode("utf-8"), "port_call_coordination_results.csv", "text/csv", use_container_width=True)

with conflicts_tab:
    st.subheader("Potential berth-window overlaps")
    if conflicts.empty:
        st.info("No berth overlap pairs are available. Run the coordination analysis to refresh this result.")
    else:
        st.write("Each row represents two port calls with overlapping actual or estimated berth windows on the same berth.")
        st.dataframe(conflicts, use_container_width=True, hide_index=True)
        st.download_button("Download berth overlap pairs CSV", conflicts.to_csv(index=False).encode("utf-8"), "berth_conflict_pairs.csv", "text/csv", use_container_width=True)

with report_tab:
    st.subheader("Coordination summary report")
    if REPORT.exists():
        st.code(REPORT.read_text(encoding="utf-8"), language="text")
    else:
        st.info("The text report has not been generated yet.")
st.caption("Priority and delay rules are configurable business rules. Validate all findings against confirmed operational records before using them for decisions.")
