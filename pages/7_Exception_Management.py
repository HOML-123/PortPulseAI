from pathlib import Path
import sys
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import port_call_exception_management as exception_manager
from src import exception_status_management as status_manager
from src import exception_workflow_history_analytics as history_analytics
from src.ui_theme import apply_page_style

PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "outputs" / "reports"
SOURCE_QUEUE = PROCESSED / "port_call_exception_queue.csv"
MANAGED_QUEUE = PROCESSED / "port_call_exception_queue_managed.csv"
HISTORY_FILE = PROCESSED / "exception_status_history.csv"
REGISTRY_FILE = PROCESSED / "exception_status_registry.csv"
DAILY_FILE = PROCESSED / "exception_history_daily_summary.csv"
EVENT_FILE = PROCESSED / "exception_history_event_summary.csv"
TRANSITION_FILE = PROCESSED / "exception_history_transition_summary.csv"
STATUS_REPORT = REPORTS / "exception_status_summary.txt"
HISTORY_REPORT = REPORTS / "exception_workflow_history_analytics.txt"
VALID_STATUSES = status_manager.VALID_STATUSES

st.set_page_config(page_title="Exception Management | PortPulse AI", page_icon="📋", layout="wide")
apply_page_style("Exception Management", "Review port-call exceptions, update workflow statuses and inspect recorded status history.")
st.warning("Exceptions are generated from the current coordination dataset. Team assignments and recommended actions are rule-based suggestions, not verified live operational instructions.")

if not SOURCE_QUEUE.exists():
    st.info("The exception queue has not been created yet. Run Port-Call Coordination first.")
    st.code("python src\\port_call_coordination.py\npython src\\port_call_exception_management.py", language="bat")
    if st.button("Build exception queue", type="primary"):
        try:
            exception_manager.main()
            status_manager.sync_queue()
            st.success("Exception queue created and synchronised.")
            st.rerun()
        except Exception as error:
            st.error(f"Could not build the exception queue: {error}")
    st.stop()

left, right = st.columns(2)
with left:
    if st.button("Refresh exception queue", use_container_width=True):
        try:
            exception_manager.main()
            status_manager.sync_queue()
            st.success("Queue refreshed and statuses synchronised.")
            st.rerun()
        except Exception as error:
            st.error(f"Queue refresh failed: {error}")
with right:
    if st.button("Synchronise saved statuses", use_container_width=True):
        try:
            status_manager.sync_queue()
            st.success("Saved statuses synchronised.")
            st.rerun()
        except Exception as error:
            st.error(f"Status synchronisation failed: {error}")

# Deliberately read current workflow files on each run; status updates must not be hidden by stale cache.
if MANAGED_QUEUE.exists():
    queue = pd.read_csv(MANAGED_QUEUE, dtype=str).fillna("")
else:
    queue = pd.read_csv(SOURCE_QUEUE, dtype=str).fillna("")
    queue["queue_status"] = "Open"
if queue.empty:
    st.info("The exception queue is currently empty.")
    st.stop()
for column in ["coordination_priority", "queue_status", "exception_type", "responsible_team"]:
    if column not in queue.columns:
        queue[column] = ""

total = len(queue)
open_count = int(queue["queue_status"].eq("Open").sum())
progress_count = int(queue["queue_status"].eq("In Progress").sum())
resolved_count = int(queue["queue_status"].eq("Resolved").sum())
closed_count = int(queue["queue_status"].eq("Closed").sum())
high_count = int(queue["coordination_priority"].eq("High").sum())
st.subheader("Exception overview")
a, b, c, d, e, f = st.columns(6)
a.metric("Total exceptions", f"{total:,}")
b.metric("High priority", f"{high_count:,}")
c.metric("Open", f"{open_count:,}")
d.metric("In progress", f"{progress_count:,}")
e.metric("Resolved", f"{resolved_count:,}")
f.metric("Closed", f"{closed_count:,}")
st.divider()
queue_tab, update_tab, history_tab, reports_tab = st.tabs(["Exception queue", "Update status", "Event history", "Reports and analytics"])

with queue_tab:
    st.subheader("Filter exceptions")
    filter_a, filter_b, filter_c = st.columns(3)
    with filter_a:
        priority_options = ["All"] + sorted(v for v in queue["coordination_priority"].unique() if v)
        selected_priority = st.selectbox("Priority", priority_options)
    with filter_b:
        selected_status = st.selectbox("Workflow status", ["All"] + list(VALID_STATUSES))
    with filter_c:
        team_options = ["All"] + sorted(v for v in queue["responsible_team"].unique() if v)
        selected_team = st.selectbox("Responsible team", team_options)
    filtered = queue.copy()
    if selected_priority != "All":
        filtered = filtered[filtered["coordination_priority"] == selected_priority]
    if selected_status != "All":
        filtered = filtered[filtered["queue_status"] == selected_status]
    if selected_team != "All":
        filtered = filtered[filtered["responsible_team"] == selected_team]
    visible_columns = [c for c in ["exception_id", "port_call_id", "vessel_name", "voyage_number", "berth", "exception_type", "exception_description", "coordination_priority", "responsible_team", "recommended_action", "queue_status", "last_known_milestone", "data_source"] if c in filtered.columns]
    st.caption(f"{len(filtered):,} exceptions match your filters.")
    st.dataframe(filtered[visible_columns], use_container_width=True, hide_index=True)
    st.download_button("Download filtered exception queue", filtered.to_csv(index=False).encode("utf-8"), "port_pulse_filtered_exception_queue.csv", "text/csv", use_container_width=True)

with update_tab:
    st.subheader("Change an exception's status")
    st.write("Select an exception, review its current status and choose a new status. Changes are recorded by the existing workflow manager.")
    if not REGISTRY_FILE.exists():
        st.info("Synchronise saved statuses before making your first status update.")
    if "exception_id" not in queue.columns or queue["exception_id"].empty:
        st.info("No exception IDs are available to update.")
    else:
        ids = queue["exception_id"].astype(str).tolist()
        def exception_label(exception_id):
            match = queue[queue["exception_id"].astype(str) == exception_id]
            if match.empty:
                return exception_id
            row = match.iloc[0]
            return f"{exception_id} | {row.get('vessel_name', '')} | {row.get('exception_type', '')}"
        selected_id = st.selectbox("Exception", ids, format_func=exception_label)
        selected_row = queue[queue["exception_id"].astype(str) == selected_id].iloc[0]
        current_status = selected_row.get("queue_status", "Open")
        st.write(f"Current status: **{current_status}**")
        new_status = st.selectbox("New status", VALID_STATUSES, index=VALID_STATUSES.index(current_status) if current_status in VALID_STATUSES else 0, key="new_exception_status")
        if st.button("Save status change", type="primary"):
            try:
                status_manager.update_status(selected_id, new_status)
                st.success("Status update processed.")
                st.rerun()
            except Exception as error:
                st.error(f"Status update failed: {error}")

with history_tab:
    st.subheader("Recorded workflow events")
    if HISTORY_FILE.exists():
        history = pd.read_csv(HISTORY_FILE, dtype=str).fillna("")
        if history.empty:
            st.info("The event history file exists but contains no events.")
        else:
            if "event_timestamp_utc" in history.columns:
                history = history.sort_values("event_timestamp_utc", ascending=False)
            st.dataframe(history, use_container_width=True, hide_index=True)
            st.download_button("Download event history", history.to_csv(index=False).encode("utf-8"), "exception_status_history.csv", "text/csv", use_container_width=True)
    else:
        st.info("No event history exists yet. Synchronise the exception queue to register the current exceptions.")

with reports_tab:
    st.subheader("Workflow analytics")
    if st.button("Generate history analytics", type="primary"):
        try:
            if not HISTORY_FILE.exists():
                status_manager.sync_queue()
            history_analytics.main()
            st.success("History analytics generated.")
            st.rerun()
        except Exception as error:
            st.error(f"Analytics generation failed: {error}")
    for label, path in [("Daily event summary", DAILY_FILE), ("Event type summary", EVENT_FILE), ("Status transition summary", TRANSITION_FILE)]:
        st.markdown(f"**{label}**")
        if path.exists():
            st.dataframe(pd.read_csv(path), use_container_width=True, hide_index=True)
        else:
            st.caption("Not generated yet.")
    if STATUS_REPORT.exists():
        with st.expander("Status summary report"):
            st.code(STATUS_REPORT.read_text(encoding="utf-8"), language="text")
    if HISTORY_REPORT.exists():
        with st.expander("History analytics report"):
            st.code(HISTORY_REPORT.read_text(encoding="utf-8"), language="text")
st.caption("A missing source exception is not automatically resolved or closed. Review the event history and confirm operational facts independently.")
