import pandas as pd
import plotly.express as px
import streamlit as st
from src.ui_theme import apply_page_style, style_plotly

st.set_page_config(page_title="Recovery Simulation | PortPulse AI", page_icon="⚓", layout="wide")
apply_page_style("Recovery Planning", "Explore how reduced service capacity and additional recovery resources affect a simulated container queue.")

st.sidebar.header("Simulation settings")
arrivals = st.sidebar.slider("Containers arriving per hour", 5, 100, 30)
capacity = st.sidebar.slider("Normal service capacity per hour", 5, 120, 40)
hours = st.sidebar.slider("Simulation duration (hours)", 12, 96, 48)
disruption_start = st.sidebar.slider("Disruption starts at hour", 1, 24, 8)
disruption_length = st.sidebar.slider("Disruption duration (hours)", 2, 24, 8)
reduced_capacity = st.sidebar.slider("Capacity during disruption (%)", 10, 90, 50)
extra_capacity = st.sidebar.slider("Extra recovery capacity per hour", 0, 60, 15)


def simulate(scenario):
    queue, rows = 0.0, []
    for hour in range(hours):
        disrupted = disruption_start <= hour < disruption_start + disruption_length
        service = float(capacity)
        if scenario != "Baseline" and disrupted:
            service = capacity * reduced_capacity / 100
        if scenario == "Recovery" and hour >= disruption_start + disruption_length:
            service += extra_capacity
        queue += arrivals
        served = min(queue, service)
        queue -= served
        rows.append({"Hour": hour + 1, "Scenario": scenario, "Arrivals": arrivals, "Containers Served": round(served, 2), "Remaining Queue": round(queue, 2), "Service Capacity": round(service, 2)})
    return pd.DataFrame(rows)

results = pd.concat([simulate(name) for name in ["Baseline", "Disruption", "Recovery"]], ignore_index=True)
summary = results.groupby("Scenario", as_index=False).agg(Final_Queue=("Remaining Queue", "last"), Total_Served=("Containers Served", "sum"))
summary[["Final_Queue", "Total_Served"]] = summary[["Final_Queue", "Total_Served"]].round(2)

columns = st.columns(3)
for column, scenario in zip(columns, ["Baseline", "Disruption", "Recovery"]):
    row = summary[summary["Scenario"] == scenario].iloc[0]
    with column:
        st.metric(f"{scenario} · final queue", f"{row['Final_Queue']:,.0f}")
        st.caption(f"Total containers served: {row['Total_Served']:,.0f}")
st.divider()
st.subheader("Queue growth and recovery")
fig = px.line(results, x="Hour", y="Remaining Queue", color="Scenario", template="plotly_white", color_discrete_map={"Baseline":"#087F8C", "Disruption":"#C65353", "Recovery":"#D69A35"}, labels={"Remaining Queue":"Containers waiting", "Hour":"Simulation hour"})
fig.update_traces(line=dict(width=3))
st.plotly_chart(style_plotly(fig, 430), use_container_width=True)
st.subheader("Compare scenarios")
left, right = st.columns([1, 1.2], gap="large")
with left:
    st.dataframe(summary, use_container_width=True, hide_index=True)
with right:
    fig = px.bar(summary, x="Scenario", y="Final_Queue", color="Scenario", template="plotly_white", color_discrete_map={"Baseline":"#087F8C", "Disruption":"#C65353", "Recovery":"#D69A35"}, labels={"Final_Queue":"Containers remaining"})
    fig.update_layout(showlegend=False)
    st.plotly_chart(style_plotly(fig, 360), use_container_width=True)
st.divider()
left, right = st.columns(2)
with left:
    st.download_button("Download hourly simulation CSV", results.to_csv(index=False).encode("utf-8"), "portpulse_recovery_simulation.csv", "text/csv", use_container_width=True)
with right:
    st.download_button("Download scenario summary CSV", summary.to_csv(index=False).encode("utf-8"), "portpulse_scenario_summary.csv", "text/csv", use_container_width=True)
st.caption("Illustrative simulation only. Arrivals and service capacities are simplified assumptions, not forecasts of actual terminal performance.")
