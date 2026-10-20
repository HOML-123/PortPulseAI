from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from src.ui_theme import apply_page_style, style_plotly

ROOT = Path(__file__).resolve().parent.parent
RISK = ROOT / "data" / "processed" / "case_risk_scores.csv.gz"
FEATURES = ROOT / "data" / "processed" / "container_features.csv.gz"

st.set_page_config(page_title="Risk Dashboard | PortPulse AI", page_icon="⚓", layout="wide")
apply_page_style("Risk Intelligence", "Review rule-based case risk indicators and investigate records that may need attention.")

@st.cache_data(show_spinner="Loading risk records...")
def load_csv(path_text, modified_time):
    return pd.read_csv(path_text)

if not RISK.is_file():
    st.error("Risk data not found. Run: python src\\risk_analysis.py")
    st.stop()

risk = load_csv(str(RISK), RISK.stat().st_mtime)
features = load_csv(str(FEATURES), FEATURES.stat().st_mtime) if FEATURES.is_file() else pd.DataFrame()
if risk.empty:
    st.warning("The risk dataset contains no records.")
    st.stop()

case_col = next((c for c in ["case_id", "Case ID", "CASE_ID"] if c in risk.columns), None)
level_col = next((c for c in ["risk_level", "Risk_Level", "risk_category"] if c in risk.columns), None)
score_col = next((c for c in ["risk_score", "Risk_Score", "total_risk_score"] if c in risk.columns), None)
if not case_col:
    st.error(f"Case ID column not found. Available columns: {list(risk.columns)}")
    st.stop()

if level_col:
    risk[level_col] = risk[level_col].fillna("Unknown").astype(str)
    counts = risk[level_col].value_counts().rename_axis("Risk Level").reset_index(name="Cases")
    high_cases = risk.loc[risk[level_col].str.lower() == "high", case_col].nunique()
else:
    counts = pd.DataFrame()
    high_cases = None
average_score = pd.to_numeric(risk[score_col], errors="coerce").mean() if score_col else None

a, b, c = st.columns(3)
a.metric("Cases analysed", f"{risk[case_col].nunique():,}")
b.metric("High-risk cases", f"{high_cases:,}" if high_cases is not None else "Unavailable")
c.metric("Average risk score", f"{average_score:.2f}" if pd.notna(average_score) else "Unavailable")
st.divider()
left, right = st.columns([1, 1.2], gap="large")
with left:
    st.subheader("Risk distribution")
    if not counts.empty:
        order = [x for x in ["High", "Medium", "Low", "Unknown"] if x in counts["Risk Level"].tolist()]
        fig = px.bar(counts, x="Risk Level", y="Cases", color="Risk Level", category_orders={"Risk Level": order}, color_discrete_map={"High":"#C65353", "Medium":"#D69A35", "Low":"#16877D", "Unknown":"#8496A5"}, template="plotly_white", text_auto=True)
        fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Cases")
        st.plotly_chart(style_plotly(fig, 360), use_container_width=True)
    else:
        st.info("No recognised risk-level column was found.")
with right:
    st.subheader("Recent risk records")
    st.dataframe(risk.head(10), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Case investigation")
query = st.text_input("Search by case ID", placeholder="Enter all or part of a case ID")
if query.strip():
    matches = risk[risk[case_col].astype(str).str.contains(query.strip(), case=False, na=False, regex=False)]
    if matches.empty:
        st.warning("No matching case found.")
    else:
        st.caption(f"{len(matches):,} matching records")
        st.dataframe(matches, use_container_width=True, hide_index=True)
        feature_case_col = next((c for c in ["case_id", "Case ID", "CASE_ID"] if c in features.columns), None)
        if feature_case_col:
            ids = matches[case_col].astype(str).unique()
            details = features[features[feature_case_col].astype(str).isin(ids)]
            if not details.empty:
                st.subheader("Related case features")
                st.dataframe(details, use_container_width=True, hide_index=True)
st.download_button("Download risk data", risk.to_csv(index=False).encode("utf-8"), "portpulse_risk_data.csv", "text/csv", use_container_width=True)
st.caption("Risk scores are rule-based screening indicators, not confirmed delay predictions. Historical records do not represent live terminal conditions.")
