import streamlit as st

NAVY = "#163247"
TEAL = "#087F8C"
TEXT = "#172B3A"
MUTED = "#607586"
GRID = "#E4EBF0"
SURFACE = "#FFFFFF"
BACKGROUND = "#F3F6F9"


def apply_page_style(page_title, subtitle=None):
    st.markdown(
        """
        <style>
        :root { color-scheme: light; }
        .stApp { background: #F3F6F9; color: #172B3A; }
        [data-testid="stHeader"] { background: rgba(243,246,249,.96); }
        .main .block-container { max-width: 1480px; padding: 1.5rem 2rem 3rem; }
        section[data-testid="stSidebar"] { background: #EAF0F5; border-right: 1px solid #DCE5EC; }
        section[data-testid="stSidebar"] * { color: #172B3A; }
        h1,h2,h3,h4 { color: #163247 !important; letter-spacing: -.025em; }
        p, label, .stMarkdown, [data-testid="stCaptionContainer"] { color: #344D5D; }
        div[data-testid="stMetric"] { background:#FFFFFF; border:1px solid #DFE7ED; border-radius:12px; padding:16px 18px; box-shadow:0 2px 7px rgba(22,50,71,.04); }
        div[data-testid="stMetricLabel"] { color:#607586; font-size:.85rem; }
        div[data-testid="stMetricValue"] { color:#163247; font-weight:700; overflow-wrap:anywhere; }
        div[data-testid="stDataFrame"], div[data-testid="stTable"] { border:1px solid #DFE7ED; border-radius:10px; overflow:hidden; background:#FFFFFF; }
        div[data-testid="stVerticalBlockBorderWrapper"] { border-color:#DFE7ED; border-radius:12px; }
        div[data-testid="stAlert"] { border-radius:10px; }
        div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea { background:#FFFFFF; color:#172B3A; }
        div[data-baseweb="select"] > div { background:#FFFFFF; border-color:#CFDCE5; }
        div[data-testid="stSlider"] label, div[data-testid="stSelectbox"] label, div[data-testid="stTextInput"] label { color:#344D5D; }
        .stButton > button, .stDownloadButton > button { border-radius:8px; font-weight:600; min-height:2.5rem; }
        .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] { background:#087F8C; border-color:#087F8C; color:#FFFFFF; }
        .stButton > button:hover, .stDownloadButton > button:hover { border-color:#087F8C; color:#087F8C; }
        div[data-testid="stPlotlyChart"] { background:#FFFFFF; border:1px solid #DFE7ED; border-radius:12px; padding:8px; }
        hr { border-color:#DFE7ED; }
        .pp-eyebrow { color:#087F8C; font-size:.75rem; font-weight:750; letter-spacing:.12em; text-transform:uppercase; margin-bottom:.3rem; }
        .pp-page-title { color:#163247; font-size:2rem; font-weight:750; letter-spacing:-.04em; line-height:1.2; margin:0 0 .45rem; }
        .pp-page-subtitle { color:#607586; font-size:1rem; line-height:1.6; margin:0 0 1.5rem; }
        .pp-panel { background:#FFFFFF; border:1px solid #DFE7ED; border-radius:12px; padding:1rem 1.15rem; }
        @media(max-width:768px) { .main .block-container { padding-left:1rem; padding-right:1rem; } .pp-page-title { font-size:1.6rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="pp-eyebrow">PORTPULSE AI / OPERATIONS INTELLIGENCE</div>'
        f'<div class="pp-page-title">{page_title}</div>'
        f'<div class="pp-page-subtitle">{subtitle or "Operational visibility, analysis and decision support."}</div>',
        unsafe_allow_html=True,
    )


def style_plotly(fig, height=None):
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family="Arial, sans-serif", size=12, color=TEXT),
        title=dict(font=dict(size=17, color=NAVY), x=0.02, xanchor="left"),
        margin=dict(l=24, r=24, t=58, b=30),
        legend=dict(bgcolor="rgba(255,255,255,0.85)", borderwidth=0, font=dict(color=TEXT)),
        hoverlabel=dict(bgcolor=NAVY, bordercolor=NAVY, font=dict(color="#FFFFFF", size=12)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID, tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, linecolor=GRID, tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    if height is not None:
        fig.update_layout(height=height)
    return fig


def show_data_notice(message="Historical data and simulation outputs should be interpreted within their stated data limitations."):
    st.caption(message)
