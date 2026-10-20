
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Recovery Recommender | PortPulse AI", page_icon="⚓", layout="wide")
st.markdown("""
<style>
.block-container {padding-top:1.8rem;padding-bottom:2rem;}
[data-testid="stMetric"] {background:#fff;padding:16px;border:1px solid #dce5ee;border-radius:12px;}
h1,h2,h3 {color:#12304a;}
</style>
""", unsafe_allow_html=True)

st.title("Recovery Strategy Intelligence")
st.caption("PORTPULSE AI  /  ADAPTIVE RECOVERY PLANNING")
st.write("Compare five simulated recovery strategies and identify which performs best under your selected assumptions.")

st.sidebar.header("Planning Assumptions")
arrivals = st.sidebar.slider("Containers arriving per hour", 5, 100, 30)
capacity = st.sidebar.slider("Normal service capacity per hour", 5, 120, 40)
hours = st.sidebar.slider("Simulation duration (hours)", 12, 96, 48)
start = st.sidebar.slider("Disruption starts at hour", 1, 24, 8)
length = st.sidebar.slider("Disruption duration (hours)", 2, 24, 8)
reduced = st.sidebar.slider("Disruption capacity (%)", 10, 90, 50)
extra = st.sidebar.slider("Additional service capacity per hour", 0, 60, 15)

def simulate(strategy):
    queue, rows = 0, []
    for hour in range(hours):
        disrupted = start <= hour < start + length
        service = capacity
        if strategy != "Baseline" and disrupted:
            service = round(capacity * reduced / 100)
        if strategy in ["Extra During Disruption", "Combined Recovery"] and disrupted:
            service += extra
        if strategy in ["Extra After Disruption", "Combined Recovery"] and hour >= start + length:
            service += extra
        queue += arrivals
        served = min(queue, service)
        queue -= served
        rows.append({"Hour": hour + 1, "Strategy": strategy, "Queue": queue, "Served": served})
    return pd.DataFrame(rows)

strategies = ["Baseline", "Disruption Only", "Extra During Disruption", "Extra After Disruption", "Combined Recovery"]
results = pd.concat([simulate(strategy) for strategy in strategies], ignore_index=True)
summary = results.groupby("Strategy", as_index=False).agg(
    Final_Queue=("Queue", "last"),
    Peak_Queue=("Queue", "max"),
    Queue_Hours=("Queue", "sum"),
    Total_Served=("Served", "sum")
).sort_values(["Queue_Hours", "Final_Queue"]).reset_index(drop=True)
summary.insert(0, "Rank", range(1, len(summary) + 1))

best = summary.iloc[0]

st.subheader("Recommended Strategy")
st.success(f"Top-ranked strategy: {best['Strategy']}")
st.write(f"Lowest simulated cumulative queue: **{best['Queue_Hours']:,.0f} container-hours**.")

a, b, c = st.columns(3)
a.metric("Top Strategy", best["Strategy"])
b.metric("Final Queue", f"{best['Final_Queue']:,.0f}")
c.metric("Peak Queue", f"{best['Peak_Queue']:,.0f}")

st.caption("Ranking uses cumulative queue-hours first and final queue as the tie-breaker.")

st.divider()
st.subheader("Queue Performance Over Time")
fig = px.line(
    results, x="Hour", y="Queue", color="Strategy",
    template="plotly_white",
    labels={"Hour": "Simulation hour", "Queue": "Containers waiting"}
)
fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), legend_title_text="Strategy")
st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Strategy Ranking")
left, right = st.columns([1, 1.2], gap="large")
with left:
    st.dataframe(summary, use_container_width=True, hide_index=True)
with right:
    fig = px.bar(
        summary.sort_values("Queue_Hours", ascending=True),
        x="Queue_Hours", y="Strategy", orientation="h",
        template="plotly_white",
        labels={"Queue_Hours": "Cumulative queue (container-hours)", "Strategy": "Strategy"},
        hover_data=["Rank", "Final_Queue", "Peak_Queue", "Total_Served"]
    )
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Export Results")
a, b = st.columns(2)
with a:
    st.download_button("Download Strategy Ranking", summary.to_csv(index=False), "portpulse_recovery_ranking.csv", "text/csv", use_container_width=True)
with b:
    st.download_button("Download Hourly Results", results.to_csv(index=False), "portpulse_recovery_hourly.csv", "text/csv", use_container_width=True)

st.caption("Recommendations are based on simplified simulation assumptions, not live terminal data or operational forecasts.")
