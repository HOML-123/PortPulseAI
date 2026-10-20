from pathlib import Path
import streamlit as st
from src.ui_theme import apply_page_style

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "processed"
DEMO = ROOT / "data" / "demo"
REPORTS = ROOT / "outputs" / "reports"

st.set_page_config(page_title="PortPulse AI | Port Operations", page_icon="⚓", layout="wide", initial_sidebar_state="expanded")
apply_page_style("PortPulse AI", "Port operations intelligence for vessel coordination, container-flow analysis and disruption recovery.")

st.markdown("""
<div style="background:linear-gradient(115deg,#163247 0%,#205568 62%,#087F8C 100%);border-radius:16px;padding:28px 30px;color:#FFFFFF;margin:0 0 22px 0;">
  <div style="font-size:12px;letter-spacing:2px;font-weight:700;color:#BFE8E8;margin-bottom:12px;">PORT &amp; TERMINAL OPERATIONS</div>
  <div style="font-size:clamp(23px,3vw,32px);font-weight:750;line-height:1.2;margin-bottom:10px;color:#FFFFFF;">See the operation. Find the constraint. Plan the response.</div>
  <div style="font-size:15px;line-height:1.65;max-width:850px;color:#E5F0F4;">Explore recorded container activity, identify operational patterns, review port-call milestones and compare simulated recovery scenarios in one workspace.</div>
</div>
""", unsafe_allow_html=True)

st.subheader("Platform overview")
a, b, c, d = st.columns(4)
a.metric("Analysis areas", "3")
b.metric("Recovery areas", "2")
c.metric("Coordination areas", "2")
d.metric("Operating mode", "Analytical")
st.caption("This workspace combines historical event-log analysis with scenario-based simulation and synthetic port-call demonstration data.")
st.divider()
st.subheader("Operations workspace")
st.write("Choose an area from the cards below or use the navigation sidebar.")

modules = [
    {"number":"01","title":"Risk Dashboard","description":"Review case-level risk scores and investigate records requiring attention.","page":"1_Risk_Dashboard.py","group":"ANALYSE"},
    {"number":"02","title":"Container Journey","description":"Trace recorded activity sequences and inspect gaps across a selected case.","page":"2_Container_Journey.py","group":"ANALYSE"},
    {"number":"03","title":"Bottleneck Analysis","description":"Explore activity duration and time-gap patterns to find possible constraints.","page":"3_Bottleneck_Analysis.py","group":"ANALYSE"},
    {"number":"04","title":"Recovery Simulation","description":"Test queue and capacity behaviour under configurable disruption scenarios.","page":"4_Recovery_Simulation.py","group":"RECOVERY"},
    {"number":"05","title":"Recovery Recommendations","description":"Compare recovery options using the project's defined simulation assumptions.","page":"5_Recovery_Recommendations.py","group":"RECOVERY"},
    {"number":"06","title":"Port-call Coordination","description":"Review vessel milestones, schedule delays and potential berth-window overlaps.","page":"6_Port_Call_Coordination.py","group":"COORDINATION"},
    {"number":"07","title":"Exception Management","description":"Review the exception queue, track statuses and inspect workflow history.","page":"7_Exception_Management.py","group":"COORDINATION"},
]
for group in ["ANALYSE", "RECOVERY", "COORDINATION"]:
    st.markdown(f"**{group}**")
    group_modules = [item for item in modules if item["group"] == group]
    columns = st.columns(2)
    for index, item in enumerate(group_modules):
        with columns[index % 2]:
            with st.container(border=True):
                st.caption(f"MODULE {item['number']}")
                st.markdown(f"### {item['title']}")
                st.write(item["description"])
                if (ROOT / "pages" / item["page"]).is_file():
                    st.page_link(f"pages/{item['page']}", label=f"Open {item['title']}", icon="↗", use_container_width=True)
                else:
                    st.warning("The page file was not found.")
    st.write("")

st.divider()
st.subheader("Project data and outputs")
data_items = [
    ("Cleaned event records", DATA / "cleaned_events.csv.gz"),
    ("Validated event records", DATA / "valid_events.csv.gz"),
    ("Container features", DATA / "container_features.csv.gz"),
    ("Case risk scores", DATA / "case_risk_scores.csv.gz"),
    ("Port-call demo dataset", DEMO / "port_call_milestones_demo.csv"),
    ("Port-call coordination results", DATA / "port_call_coordination_results.csv"),
    ("Port-call exception queue", DATA / "port_call_exception_queue.csv"),
    ("Exception workflow report", REPORTS / "exception_workflow_full_run.txt"),
]
available_count = sum(path.is_file() for _, path in data_items)
left, right = st.columns([1, 2])
with left:
    st.metric("Available tracked outputs", f"{available_count}/{len(data_items)}")
with right:
    st.progress(available_count / len(data_items))
    st.caption("This is a file-availability check, not a measure of data quality or model accuracy.")
with st.expander("View file availability"):
    for label, path in data_items:
        st.write(f"✓ {label}" if path.is_file() else f"— {label} (not generated or not present)")

st.divider()
st.subheader("How to interpret the results")
st.markdown("""
- **Historical analysis:** describes patterns in the available event log.
- **Risk scores:** support prioritisation; they should not be treated as verified operational outcomes.
- **Recovery simulations:** explore defined assumptions, not live terminal conditions.
- **Port-call coordination:** uses synthetic demonstration records. Potential berth overlaps are review flags, not confirmed real-world conflicts.
""")
st.caption("PortPulse AI · Port operations analytics and decision support · Demonstration project, not a live port management system.")
