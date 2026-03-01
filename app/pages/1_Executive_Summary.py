"""
1_Executive_Summary.py — Fleet-wide KPIs, risk breakdown, and prioritization matrix.
GridGuard Network Intelligence — UA Innovate 2026
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.constants import BRAND, RISK_COLORS, RISK_TIER_ORDER, LIFECYCLE_STAGE_ORDER, DARK_PLOT_BG, insight_caption

st.set_page_config(
    page_title="Executive Summary | GridGuard",
    page_icon="⚡",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
def _render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.markdown(
            f"<h3 style='color:{BRAND['accent_orange']}'>Executive Summary</h3>",
            unsafe_allow_html=True,
        )
        states = sorted(df["state"].dropna().unique())
        sel_states = st.multiselect("Filter by State", states)

        types = sorted(df["device_type"].dropna().unique())
        sel_types = st.multiselect("Filter by Device Type", types)

        sel_risk = st.multiselect(
            "Filter by Risk Tier",
            ["Critical", "High", "Medium", "Low"],
        )

        support_levels = (
            sorted(df["support_level"].dropna().unique().tolist()) + ["Not Available"]
            if "support_level" in df.columns else []
        )
        sel_support = st.multiselect("Filter by Support Level", support_levels)

        from utils.exceptions import apply_exceptions
        show_exc = st.checkbox("Include Excepted Devices", value=False)
        df = apply_exceptions(df, show_exceptions=show_exc)

    if sel_states:
        df = df[df["state"].isin(sel_states)]
    if sel_types:
        df = df[df["device_type"].isin(sel_types)]
    if sel_risk:
        df = df[df["risk_tier"].isin(sel_risk)]
    if sel_support and "support_level" in df.columns:
        disp = df["support_level"].fillna("Not Available")
        df = df[disp.isin(sel_support)]
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if "df" not in st.session_state:
    st.warning("Upload your dataset on the Home page first.")
    st.stop()

raw_df = st.session_state["df"]
df = _render_sidebar(raw_df.copy())

st.markdown(
    f"<h1 style='color:{BRAND['white']}'>Executive Summary</h1>",
    unsafe_allow_html=True,
)
st.caption(f"Showing **{len(df):,}** devices after filters")
st.divider()

# ---------------------------------------------------------------------------
# KPI Cards
# ---------------------------------------------------------------------------
total     = len(df)
critical  = (df["risk_tier"] == "Critical").sum()
high      = (df["risk_tier"] == "High").sum()
past_eol  = df["is_past_eol"].sum()
past_eos  = df["is_past_eos"].sum()
exposure  = df["risk_cost_exposure"].sum()
total_rep = df["total_cost"].sum()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Active Devices", f"{total:,}")
with col2:
    ml_analyzed = (df["lifecycle_stage"] == "Unknown - No Lifecycle Data").sum()
    st.metric(
        "Scored by ML Analysis",
        f"{ml_analyzed:,}",
        delta=f"{ml_analyzed/total*100:.1f}% — no lifecycle data" if total else "—",
        delta_color="off",
        help="Devices with no EoS/EoL data in Cisco's lifecycle database. "
             "Risk scores for these devices are predicted by the ML model on page 7.",
    )
with col3:
    st.metric("Risk Cost Exposure", f"${exposure:,.0f}")
with col4:
    st.metric(
        "Past End of Life", f"{past_eol:,}",
        delta="Unsupported in production",
        delta_color="inverse",
    )

col5, col6, col7, col8 = st.columns(4)
with col5:
    st.metric("High Risk Devices", f"{high:,}")
with col6:
    st.metric("Past End of Sale", f"{past_eos:,}")
with col7:
    st.metric("Total Replacement Cost", f"${total_rep:,.0f}")
with col8:
    no_support = int(df["support_level"].isna().sum()) if "support_level" in df.columns else 0
    st.metric(
        "Without Support Coverage",
        f"{no_support:,}",
        delta=f"{no_support/total*100:.1f}% of fleet" if total else "—",
        delta_color="inverse",
        help="Devices from Network Analytics and Cisco Prime sources where SmartNet/support contract data is not available. CatCtr is the authoritative source for support level.",
    )

st.divider()

# ---------------------------------------------------------------------------
# Row 1 — Fleet Risk Tier Distribution (donut)
# ---------------------------------------------------------------------------
tier_counts = (
    df["risk_tier"]
    .value_counts()
    .reindex(RISK_TIER_ORDER)
    .dropna()
    .reset_index()
)
tier_counts.columns = ["Risk Tier", "Count"]

fig_donut = px.pie(
    tier_counts,
    names="Risk Tier",
    values="Count",
    color="Risk Tier",
    color_discrete_map=RISK_COLORS,
    hole=0.55,
    title="Fleet Risk Tier Distribution",
)
fig_donut.update_traces(
    textposition="outside",
    textinfo="label+percent",
)
fig_donut.update_layout(
    showlegend=True,
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=50, b=20),
)
st.plotly_chart(fig_donut, use_container_width=True)
st.markdown(insight_caption("Every device is scored from 0 to 100 based on whether its Cisco support has expired. This chart shows how the entire fleet breaks down — the bigger the red slice, the more devices need urgent replacement."), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Row 2 — Devices by Lifecycle Stage (horizontal bar, simplified 3-bucket)
# ---------------------------------------------------------------------------
STAGE_BUCKET_MAP = {
    "Critical - Past EoL":         "Critical",
    "High Risk - Past EoS":        "At Risk",
    "Approaching EoL (<1yr)":      "At Risk",
    "Approaching EoS (<6mo)":      "At Risk",
    "Active - Supported":          "At Risk",
    "Unknown - No Lifecycle Data": "Unknown",
}
STAGE_BUCKET_ORDER = ["Critical", "At Risk", "Unknown"]
STAGE_BUCKET_COLORS = {
    "Critical": RISK_COLORS["Critical"],
    "At Risk":  RISK_COLORS["High"],
    "Unknown":  RISK_COLORS["Unknown"],
}

stage_counts = (
    df["lifecycle_stage"]
    .map(STAGE_BUCKET_MAP)
    .value_counts()
    .reindex(STAGE_BUCKET_ORDER)
    .dropna()
    .reset_index()
)
stage_counts.columns = ["Lifecycle Stage", "Count"]

fig_stage = px.bar(
    stage_counts,
    x="Count",
    y="Lifecycle Stage",
    orientation="h",
    color="Lifecycle Stage",
    color_discrete_map=STAGE_BUCKET_COLORS,
    title="Devices by Lifecycle Stage",
    text="Count",
)
fig_stage.update_traces(textposition="outside", textfont_color=BRAND["white"])
fig_stage.update_layout(
    showlegend=False,
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    plot_bgcolor=DARK_PLOT_BG,
    paper_bgcolor="rgba(0,0,0,0)",
    yaxis=dict(categoryorder="array", categoryarray=list(reversed(STAGE_BUCKET_ORDER)), gridcolor="#1a3a5c"),
    xaxis=dict(gridcolor="#1a3a5c"),
    margin=dict(t=50, b=20),
    xaxis_title="Device Count",
    yaxis_title="",
)
st.plotly_chart(fig_stage, use_container_width=True)
st.markdown(insight_caption("'Critical' devices are already past their official end-of-life date and running without Cisco support today. The gray 'Unknown' bar shows devices with no lifecycle record on file at all — those are evaluated by the machine learning model on page 7."), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Investment Prioritization Matrix — THE WOW MOMENT
# ---------------------------------------------------------------------------
st.markdown(
    f"<h2 style='color:{BRAND['white']}'>Investment Prioritization Matrix</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "Quadrant view: states in the **upper-right** require immediate refresh investment. "
    "Bubble size = device count. Color = critical device count."
)

state_matrix = (
    df.groupby("state")
    .agg(
        avg_risk_score  = ("risk_score",   "mean"),
        total_cost      = ("total_cost",   "sum"),
        device_count    = ("device_id",    "count"),
        critical_count  = ("risk_tier",    lambda x: (x == "Critical").sum()),
        exposure        = ("risk_cost_exposure", "sum"),
    )
    .reset_index()
    .query("device_count >= 1")
)

if not state_matrix.empty:
    med_risk = state_matrix["avg_risk_score"].median()
    med_cost = state_matrix["total_cost"].median()

    fig_matrix = px.scatter(
        state_matrix,
        x="total_cost",
        y="avg_risk_score",
        size="device_count",
        color="critical_count",
        hover_name="state",
        hover_data={
            "device_count":   True,
            "critical_count": True,
            "exposure":       ":,.0f",
            "total_cost":     ":,.0f",
            "avg_risk_score": ":.1f",
        },
        color_continuous_scale=[BRAND["dark_blue"], BRAND["light_blue"]],
        size_max=60,
        title="Investment Prioritization Matrix by State",
        labels={
            "total_cost":     "Total Replacement Cost ($)",
            "avg_risk_score": "Average Risk Score (0–100)",
            "critical_count": "Critical Devices",
        },
    )

    # Shade the upper-right (high cost, high risk) priority quadrant
    x_max = state_matrix["total_cost"].max() * 1.15
    y_max = state_matrix["avg_risk_score"].max() * 1.15
    fig_matrix.add_shape(
        type="rect",
        x0=med_cost, x1=x_max,
        y0=med_risk, y1=y_max,
        xref="x", yref="y",
        fillcolor="rgba(211, 47, 47, 0.10)",
        line=dict(width=0),
        layer="below",
    )

    fig_matrix.add_hline(y=med_risk, line_dash="dash", line_color=BRAND["accent_orange"],
                         annotation_text="Median risk", annotation_position="top right")
    fig_matrix.add_vline(x=med_cost, line_dash="dash", line_color=BRAND["accent_orange"],
                         annotation_text="Median cost", annotation_position="top right")

    fig_matrix.update_layout(
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#1a3a5c"),
        yaxis=dict(gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40),
    )
    st.plotly_chart(fig_matrix, use_container_width=True)
    st.markdown(insight_caption(
        "States in the shaded red zone have both above-average risk and above-average replacement cost — "
        "they need budget attention first. Each bubble is a state; bigger means more devices. "
        "Hover any bubble to see exact device counts and cost figures."
    ), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Risk by Device Type
# ---------------------------------------------------------------------------
st.markdown(f"<h2 style='color:{BRAND['white']}'>Risk by Device Type</h2>",
            unsafe_allow_html=True)

type_risk = (
    df.groupby(["device_type", "risk_tier"])
    .size()
    .reset_index(name="count")
)
type_risk["risk_tier"] = pd.Categorical(
    type_risk["risk_tier"], categories=RISK_TIER_ORDER, ordered=True
)
type_risk = type_risk.sort_values(["device_type", "risk_tier"])

fig_type = px.bar(
    type_risk,
    x="device_type",
    y="count",
    color="risk_tier",
    color_discrete_map=RISK_COLORS,
    barmode="stack",
    title="Risk Tier by Device Type",
    labels={"device_type": "Device Type", "count": "Device Count", "risk_tier": "Risk Tier"},
    category_orders={"risk_tier": RISK_TIER_ORDER},
)
fig_type.update_layout(
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    plot_bgcolor=DARK_PLOT_BG,
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#1a3a5c"),
    yaxis=dict(gridcolor="#1a3a5c"),
    legend=dict(title="Risk Tier"),
    margin=dict(t=50, b=40),
)
_type_totals = type_risk.groupby("device_type")["count"].sum().reset_index()
for _, _row in _type_totals.iterrows():
    fig_type.add_annotation(
        x=_row["device_type"], y=_row["count"],
        text=f"{_row['count']:,}",
        showarrow=False, yshift=10,
        font=dict(color=BRAND["white"], size=11, family="Arial"),
    )
st.plotly_chart(fig_type, use_container_width=True)
st.markdown(insight_caption("Each bar represents a device category — switches, routers, access points, and so on. The colors show the urgency breakdown within each type. A large red section means that category has many devices already past their end-of-life date and needing replacement now."), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Support coverage vs risk tier
# ---------------------------------------------------------------------------
if "support_level" in df.columns:
    st.divider()
    st.markdown(f"<h2 style='color:{BRAND['white']}'>Support Coverage vs Risk Tier</h2>",
                unsafe_allow_html=True)
    st.markdown(
        "Devices without support coverage AND a high risk tier represent compounded exposure — "
        "no vendor fallback and active lifecycle risk."
    )

    support_risk = (
        df.assign(support_level_display=df["support_level"].fillna("Not Available"))
        .groupby(["support_level_display", "risk_tier"])
        .size().reset_index(name="count")
    )
    support_risk["risk_tier"] = pd.Categorical(
        support_risk["risk_tier"], categories=RISK_TIER_ORDER, ordered=True
    )

    fig_support = px.bar(
        support_risk,
        x="support_level_display",
        y="count",
        color="risk_tier",
        color_discrete_map=RISK_COLORS,
        barmode="stack",
        title="Device Count by Support Level and Risk Tier",
        labels={
            "support_level_display": "Support Level",
            "count": "Device Count",
            "risk_tier": "Risk Tier",
        },
        category_orders={"risk_tier": RISK_TIER_ORDER},
    )
    fig_support.update_layout(
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#1a3a5c"),
        yaxis=dict(gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40),
    )
    _sup_totals = support_risk.groupby("support_level_display")["count"].sum().reset_index()
    for _, _row in _sup_totals.iterrows():
        fig_support.add_annotation(
            x=_row["support_level_display"], y=_row["count"],
            text=f"{_row['count']:,}",
            showarrow=False, yshift=10,
            font=dict(color=BRAND["white"], size=11, family="Arial"),
        )
    st.plotly_chart(fig_support, use_container_width=True)
    st.markdown(insight_caption(
        "'Not Available' means no active support contract is on record for that device. "
        "When those same devices are also high-risk, there is no vendor safety net if something fails — "
        "that is the most dangerous and costly combination to leave unaddressed."
    ), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Top 10 highest-risk devices table
# ---------------------------------------------------------------------------
st.divider()
st.markdown(f"<h2 style='color:{BRAND['white']}'>Top 10 Highest-Risk Devices</h2>",
            unsafe_allow_html=True)

top10 = (
    df.sort_values("risk_score", ascending=False)
    .head(10)[["hostname", "device_type", "model", "state", "site_name",
               "lifecycle_stage", "risk_score", "risk_tier", "total_cost"]]
    .reset_index(drop=True)
)
top10.index += 1
top10.columns = ["Hostname", "Type", "Model", "State", "Site",
                 "Lifecycle Stage", "Risk Score", "Risk Tier", "Replacement Cost ($)"]
top10["Replacement Cost ($)"] = top10["Replacement Cost ($)"].apply(
    lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
)

st.dataframe(
    top10.style.map(
        lambda v: f"background-color:{RISK_COLORS.get(v, 'white')}; color:white"
        if v in RISK_COLORS else "",
        subset=["Risk Tier"],
    ),
    use_container_width=True,
)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download Full Dataset as CSV",
    data=csv,
    file_name="gridguard_devices.csv",
    mime="text/csv",
)
