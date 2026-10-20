import pandas as pd
import plotly.express as px
import streamlit as st
from src.ui_theme import apply_page_style, style_plotly

st.set_page_config(page_title="Recovery Recommender | PortPulse AI", page_icon="⚓", layout="wide")
apply_page_style("Recovery Strategy Intelligence", "Compare simulated recovery strategies under your selected assumptions.")
st.sidebar.header("Planning assumptions")
arrivals = st.sidebar.slider("Containers arriving per hour", 5, 100, 30)
capacity = st.sidebar.slider("Normal service capacity per hour", 5, 120, 40)
hours = st.sidebar.slider("Simulation duration (hours)", 12, 96, 48)
start = st.sidebar.slider("Disruption starts at hour", 1, 24, 8)
length = st.sidebar.slider("Disruption duration (hours)", 2, 24, 8)
reduced = st.sidebar.slider("Disruption capacity (%)", 10, 90, 50)
extra = st.sidebar.slider("Additional service capacity per hour", 0, 60, 15)


def simulate(strategy):
    queue, rows = 0.0, []
    for hour in range(hours):
        disrupted = start <= hour < start + length
        service = float(capacity)
        if strategy != "Baseline" and disrupted:
            service = round(capacity * reduced / 100)
        if strategy in ["Extra During Disruption", "Combined Recovery"] and disrupted:
            service += extra
        if strategy in ["Extra After Disruption", "Combined Recovery"] and hour >= start + length:
            service += extra
        queue += arrivals
        served = min(queue, service)
        queue -= served
        rows.append({"Hour": hour + 1, "Strategy": strategy, "Queue": round(queue, 2), "Served": round(served, 2)})
    return pd.DataFrame(rows)

strategies = ["Baseline", "Disruption Only", "Extra During Disruption", "Extra After Disruption", "Combined Recovery"]
results = pd.concat([simulate(strategy) for strategy in strategies], ignore_index=True)
summary = results.groupby("Strategy", as_index=False).agg(Final_Queue=("Queue", "last"), Peak_Queue=("Queue", "max"), Queue_Hours=("Queue", "sum"), Total_Served=("Served", "sum")).sort_values(["Queue_Hours", "Final_Queue"]).reset_index(drop=True)
summary.insert(0, "Rank", range(1, len(summary) + 1))
best = summary.iloc[0]

st.success(f"Top-ranked strategy under these assumptions: {best['Strategy']}")
st.write(f"Lowest simulated cumulative queue: **{best['Queue_Hours']:,.0f} container-hours**.")
a, b, c = st.columns(3)
a.metric("Top strategy", best["Strategy"])
b.metric("Final queue", f"{best['Final_Queue']:,.0f}")
c.metric("Peak queue", f"{best['Peak_Queue']:,.0f}")
st.caption("Ranking uses cumulative queue-hours first and final queue as the tie-breaker.")
st.divider()
st.subheader("Queue performance over time")
fig = px.line(results, x="Hour", y="Queue", color="Strategy", template="plotly_white", labels={"Hour":"Simulation hour", "Queue":"Containers waiting"})
fig.update_traces(line=dict(width=2.5))
st.plotly_chart(style_plotly(fig, 440), use_container_width=True)
st.divider()
st.subheader("Strategy ranking")
left, right = st.columns([1, 1.2], gap="large")
with left:
    st.dataframe(summary, use_container_width=True, hide_index=True)
with right:
    chart_data = summary.sort_values("Queue_Hours", ascending=True)
    fig = px.bar(chart_data, x="Queue_Hours", y="Strategy", orientation="h", template="plotly_white", labels={"Queue_Hours":"Cumulative queue (container-hours)", "Strategy":"Strategy"}, hover_data=["Rank", "Final_Queue", "Peak_Queue", "Total_Served"])
    fig.update_traces(marker_color="#087F8C")
    st.plotly_chart(style_plotly(fig, 420), use_container_width=True)
st.subheader("Export results")
a, b = st.columns(2)
with a:
    st.download_button("Download strategy ranking", summary.to_csv(index=False).encode("utf-8"), "portpulse_recovery_ranking.csv", "text/csv", use_container_width=True)
with b:
    st.download_button("Download hourly results", results.to_csv(index=False).encode("utf-8"), "portpulse_recovery_hourly.csv", "text/csv", use_container_width=True)
st.caption("Recommendations are based on simplified simulation assumptions, not live terminal data or operational forecasts.")
