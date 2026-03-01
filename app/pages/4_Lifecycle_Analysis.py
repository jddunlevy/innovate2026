"""
4_Lifecycle_Analysis.py — EoS/EoL timelines, risk score distribution, lifecycle waves.
GridGuard Network Intelligence — UA Innovate 2026
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.constants import BRAND, RISK_COLORS, LIFECYCLE_STAGE_ORDER, DARK_PLOT_BG, insight_caption
from utils.exceptions import apply_exceptions

st.set_page_config(
    page_title="Lifecycle Analysis | GridGuard",
    page_icon="⚡",
    layout="wide",
)

TODAY = pd.Timestamp("2026-02-28")

if "df" not in st.session_state:
    st.warning("Upload your dataset on the Home page first.")
    st.stop()

raw_df = st.session_state["df"]

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<h3 style='color:{BRAND['accent_orange']}'>Lifecycle Analysis</h3>",
        unsafe_allow_html=True,
    )
    sel_states = st.multiselect("Filter by State", sorted(raw_df["state"].dropna().unique()))
    sel_types  = st.multiselect("Filter by Device Type", sorted(raw_df["device_type"].dropna().unique()))
    show_exc   = st.checkbox("Include Excepted Devices", value=False)

df = apply_exceptions(raw_df.copy(), show_exceptions=show_exc)
if sel_states:
    df = df[df["state"].isin(sel_states)]
if sel_types:
    df = df[df["device_type"].isin(sel_types)]

# ---------------------------------------------------------------------------
# Heading
# ---------------------------------------------------------------------------
st.markdown(
    f"<h1 style='color:{BRAND['white']}'>Lifecycle Analysis</h1>",
    unsafe_allow_html=True,
)
st.caption(f"Showing **{len(df):,}** devices | Reference date: {TODAY.strftime('%B %d, %Y')}")
st.divider()

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
has_dates = df[df["eos_date"].notna() | df["eol_date"].notna()]
no_dates  = df[df["eos_date"].isna()  & df["eol_date"].isna()]

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Devices with Lifecycle Data", f"{len(has_dates):,}")
with col2:
    st.metric("Past End of Life", f"{df['is_past_eol'].sum():,}", delta_color="inverse",
              delta=f"{df['is_past_eol'].mean()*100:.1f}% of fleet")
with col3:
    st.metric("Past End of Sale", f"{df['is_past_eos'].sum():,}", delta_color="inverse",
              delta=f"{df['is_past_eos'].mean()*100:.1f}% of fleet")
with col4:
    st.metric("No Lifecycle Data", f"{len(no_dates):,}",
              delta="Requires manual model lookup", delta_color="off")

st.divider()

# ---------------------------------------------------------------------------
# EoL expiration wave — devices expiring per year
# ---------------------------------------------------------------------------
st.markdown(f"<h2 style='color:{BRAND['white']}'>End-of-Life Expiration Wave</h2>",
            unsafe_allow_html=True)
st.markdown(
    "When will devices expire? This timeline shows leadership when to expect budget pressure."
)

eol_df = df[df["eol_date"].notna()].copy()
eol_df["eol_year"] = pd.to_datetime(eol_df["eol_date"]).dt.year

eol_wave = (
    eol_df.groupby(["eol_year", "device_type"])
    .agg(device_count=("device_id", "count"), total_cost=("total_cost", "sum"))
    .reset_index()
)

if not eol_wave.empty:
    fig_wave = px.bar(
        eol_wave,
        x="eol_year",
        y="device_count",
        color="device_type",
        title="Devices Reaching End of Life by Year",
        labels={
            "eol_year":    "Year",
            "device_count":"Device Count",
            "device_type": "Device Type",
        },
        text_auto=True,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    # Highlight current year
    fig_wave.add_vline(
        x=TODAY.year,
        line_dash="dash",
        line_color=BRAND["accent_orange"],
        annotation_text=f"Today ({TODAY.year})",
        annotation_position="top right",
    )
    fig_wave.update_layout(
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickmode="linear", tick0=eol_wave["eol_year"].min(), dtick=1, gridcolor="#1a3a5c"),
        yaxis=dict(gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40),
        barmode="stack",
    )
    fig_wave.update_traces(textfont_color=BRAND["white"])
    st.plotly_chart(fig_wave, use_container_width=True)
    st.markdown(insight_caption(
        "Bars to the LEFT of the orange line = already expired. "
        "Bars to the RIGHT = upcoming expirations requiring budget planning."
    ), unsafe_allow_html=True)

# EoS wave
st.markdown(f"<h2 style='color:{BRAND['white']}'>End-of-Sale Wave</h2>",
            unsafe_allow_html=True)

eos_df = df[df["eos_date"].notna()].copy()
eos_df["eos_year"] = pd.to_datetime(eos_df["eos_date"]).dt.year

eos_wave = (
    eos_df.groupby(["eos_year", "device_type"])
    .agg(device_count=("device_id", "count"))
    .reset_index()
)

if not eos_wave.empty:
    fig_eos = px.bar(
        eos_wave,
        x="eos_year",
        y="device_count",
        color="device_type",
        title="Devices Reaching End of Sale by Year",
        labels={"eos_year": "Year", "device_count": "Device Count", "device_type": "Device Type"},
        color_discrete_sequence=px.colors.qualitative.Pastel,
        text_auto=True,
    )
    fig_eos.update_traces(textfont_color=BRAND["white"])
    fig_eos.add_vline(
        x=TODAY.year,
        line_dash="dash",
        line_color=BRAND["accent_orange"],
        annotation_text=f"Today ({TODAY.year})",
        annotation_position="top right",
    )
    fig_eos.update_layout(
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickmode="linear", gridcolor="#1a3a5c"),
        yaxis=dict(gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40),
        barmode="stack",
    )
    st.plotly_chart(fig_eos, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Risk score distribution
# ---------------------------------------------------------------------------
st.markdown(f"<h2 style='color:{BRAND['white']}'>Risk Score Distribution</h2>",
            unsafe_allow_html=True)

fig_hist = px.histogram(
    df,
    x="risk_score",
    color="risk_tier",
    color_discrete_map=RISK_COLORS,
    nbins=40,
    title="Risk Score Distribution Across Fleet",
    labels={"risk_score": "Risk Score (0–100)", "count": "Device Count", "risk_tier": "Risk Tier"},
    category_orders={"risk_tier": ["Critical", "High", "Medium", "Low"]},
)
fig_hist.update_layout(
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    plot_bgcolor=DARK_PLOT_BG,
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#1a3a5c"),
    yaxis=dict(gridcolor="#1a3a5c"),
    barmode="overlay",
    margin=dict(t=60, b=40),
)
st.plotly_chart(fig_hist, use_container_width=True)
st.markdown(insight_caption(
    "Risk score (0–100) combines EoL/EoS status (primary) and device uptime (secondary). "
    "Score ≥75 = Critical, ≥50 = High, ≥25 = Medium, <25 = Low."
), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Lifecycle stage vs source — data cross-check
# ---------------------------------------------------------------------------
st.markdown(f"<h2 style='color:{BRAND['white']}'>Lifecycle Stage by Data Source</h2>",
            unsafe_allow_html=True)

stage_source = (
    df.groupby(["source", "lifecycle_stage"])
    .size()
    .reset_index(name="count")
)

stage_color_map = {
    "Critical - Past EoL":          RISK_COLORS["Critical"],
    "High Risk - Past EoS":         RISK_COLORS["High"],
    "Approaching EoL (<1yr)":       "#FF6F00",
    "Approaching EoS (<6mo)":       RISK_COLORS["Medium"],
    "Active - Supported":           RISK_COLORS["Low"],
    "Unknown - No Lifecycle Data":  RISK_COLORS["Unknown"],
}

fig_stage_src = px.bar(
    stage_source,
    x="source",
    y="count",
    color="lifecycle_stage",
    color_discrete_map=stage_color_map,
    title="Lifecycle Stage Breakdown by Source System",
    labels={"source": "Data Source", "count": "Device Count", "lifecycle_stage": "Stage"},
    barmode="stack",
    category_orders={"lifecycle_stage": LIFECYCLE_STAGE_ORDER},
)
fig_stage_src.update_layout(
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    plot_bgcolor=DARK_PLOT_BG,
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#1a3a5c"),
    yaxis=dict(gridcolor="#1a3a5c"),
    margin=dict(t=60, b=40),
)
_src_totals = stage_source.groupby("source")["count"].sum().reset_index()
for _, _row in _src_totals.iterrows():
    fig_stage_src.add_annotation(
        x=_row["source"], y=_row["count"],
        text=f"{_row['count']:,}",
        showarrow=False, yshift=10,
        font=dict(color=BRAND["white"], size=11, family="Arial"),
    )
st.plotly_chart(fig_stage_src, use_container_width=True)
st.markdown(insight_caption(
    "'Unknown - No Lifecycle Data' indicates models not yet in the lifecycle database. "
    "These require manual model lookup or vendor engagement."
), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Support coverage by lifecycle stage
# ---------------------------------------------------------------------------
if "support_level" in df.columns:
    st.divider()
    st.markdown(f"<h2 style='color:{BRAND['white']}'>Support Coverage by Lifecycle Stage</h2>",
                unsafe_allow_html=True)
    st.markdown(
        "Devices with no support coverage **AND** a critical lifecycle status represent compounded risk — "
        "no vendor fallback with active end-of-life exposure."
    )

    support_stage = (
        df.assign(support_display=df["support_level"].fillna("Not Available"))
        .groupby(["lifecycle_stage", "support_display"])
        .size().reset_index(name="count")
    )

    fig_sup_stage = px.bar(
        support_stage,
        x="lifecycle_stage",
        y="count",
        color="support_display",
        barmode="stack",
        title="Support Level Breakdown by Lifecycle Stage",
        labels={
            "lifecycle_stage": "Lifecycle Stage",
            "count":           "Device Count",
            "support_display": "Support Level",
        },
        category_orders={"lifecycle_stage": LIFECYCLE_STAGE_ORDER},
    )
    fig_sup_stage.update_layout(
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickangle=-20, gridcolor="#1a3a5c"),
        yaxis=dict(gridcolor="#1a3a5c"),
        margin=dict(t=60, b=80),
    )
    _stage_totals = support_stage.groupby("lifecycle_stage")["count"].sum().reset_index()
    for _, _row in _stage_totals.iterrows():
        fig_sup_stage.add_annotation(
            x=_row["lifecycle_stage"], y=_row["count"],
            text=f"{_row['count']:,}",
            showarrow=False, yshift=10,
            font=dict(color=BRAND["white"], size=11, family="Arial"),
        )
    st.plotly_chart(fig_sup_stage, use_container_width=True)
    st.markdown(insight_caption(
        "Focus on devices where Lifecycle Stage = 'Critical - Past EoL' AND Support = 'Not Available' — "
        "these are doubly exposed with no vendor fallback and no active support contract."
    ), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Models with most at-risk devices
# ---------------------------------------------------------------------------
st.divider()
st.markdown(f"<h2 style='color:{BRAND['white']}'>Most At-Risk Models</h2>",
            unsafe_allow_html=True)

model_risk = (
    df[df["is_past_eol"] | df["is_past_eos"]]
    .groupby("model")
    .agg(
        device_count    = ("device_id",    "count"),
        avg_risk_score  = ("risk_score",   "mean"),
        eol_date        = ("eol_date",     "first"),
        eos_date        = ("eos_date",     "first"),
        replacement     = ("replacement_model", "first"),
        device_cost     = ("device_cost",  "first"),
        total_exposure  = ("risk_cost_exposure", "sum"),
    )
    .reset_index()
    .sort_values("device_count", ascending=False)
    .head(20)
)

if not model_risk.empty:
    model_risk["avg_risk_score"] = model_risk["avg_risk_score"].round(1)
    model_risk["eol_date"] = pd.to_datetime(model_risk["eol_date"]).dt.strftime("%Y-%m-%d")
    model_risk["eos_date"] = pd.to_datetime(model_risk["eos_date"]).dt.strftime("%Y-%m-%d")
    model_risk["total_exposure"] = model_risk["total_exposure"].apply(lambda x: f"${x:,.0f}")
    model_risk["device_cost"]    = model_risk["device_cost"].apply(
        lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
    )
    model_risk = model_risk.rename(columns={
        "model":         "Model",
        "device_count":  "Devices",
        "avg_risk_score":"Avg Risk",
        "eol_date":      "End of Life",
        "eos_date":      "End of Sale",
        "replacement":   "Replacement Model",
        "device_cost":   "Unit Cost",
        "total_exposure":"Risk Exposure",
    })
    st.dataframe(model_risk, use_container_width=True)
    csv = model_risk.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download At-Risk Model List CSV",
        data=csv,
        file_name="gridguard_atrisk_models.csv",
        mime="text/csv",
    )
else:
    st.info("No past EoS/EoL devices found with current filters.")

# ---------------------------------------------------------------------------
# Section 5 — 5-Year Capital Projection (2026–2031)
# ---------------------------------------------------------------------------
st.divider()
st.markdown(
    f"<h2 style='color:{BRAND['white']}'>5-Year Capital Refresh Projection</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "Forward capital commitment for devices with known EoL dates expiring 2026–2031. "
    "Bars are stacked by device type so leadership can plan technology-specific refresh waves."
)

PROJECTION_END = pd.Timestamp("2031-12-31")

proj_df = df[
    df["eol_date"].notna() &
    (pd.to_datetime(df["eol_date"]) > TODAY) &
    (pd.to_datetime(df["eol_date"]) <= PROJECTION_END)
].copy()
proj_df["eol_year"] = pd.to_datetime(proj_df["eol_date"]).dt.year

if proj_df.empty:
    st.info("No devices with EoL dates in the 2026–2031 window under current filters.")
else:
    # --- Annual capital bar chart stacked by device_type ---
    annual = (
        proj_df.groupby(["eol_year", "device_type"])
        .agg(total_cost=("total_cost", "sum"), device_count=("device_id", "count"))
        .reset_index()
    )

    annual_totals = annual.groupby("eol_year")["total_cost"].sum().reset_index(name="year_total")

    fig_proj = px.bar(
        annual,
        x="eol_year",
        y="total_cost",
        color="device_type",
        title="Annual Network Refresh Capital Required (2026–2031)",
        labels={
            "eol_year":   "Year",
            "total_cost": "Replacement Cost ($)",
            "device_type": "Device Type",
        },
        text_auto=False,
        color_discrete_sequence=px.colors.qualitative.Set2,
        barmode="stack",
    )

    # Add $XM text annotation above each bar
    for _, row in annual_totals.iterrows():
        fig_proj.add_annotation(
            x=row["eol_year"],
            y=row["year_total"],
            text=f"${row['year_total'] / 1_000_000:.1f}M",
            showarrow=False,
            yshift=10,
            font=dict(color=BRAND["light_blue"], size=11, family="Arial"),
        )

    fig_proj.update_layout(
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickmode="linear", tick0=2026, dtick=1, gridcolor="#1a3a5c"),
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#1a3a5c"),
        margin=dict(t=70, b=40),
    )
    st.plotly_chart(fig_proj, use_container_width=True)

    # --- Cumulative area chart with threshold lines ---
    cum_by_year = (
        annual_totals.set_index("eol_year")
        .reindex(range(2026, 2032))
        .fillna(0)
        .reset_index()
    )
    cum_by_year.columns = ["eol_year", "year_total"]
    cum_by_year["cumulative_cost"] = cum_by_year["year_total"].cumsum()

    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=cum_by_year["eol_year"],
        y=cum_by_year["cumulative_cost"],
        mode="lines+markers",
        fill="tozeroy",
        name="Cumulative Capital",
        line=dict(color=BRAND["primary_blue"], width=2),
        fillcolor="rgba(0, 117, 190, 0.15)",
        hovertemplate="Year: %{x}<br>Cumulative: $%{y:,.0f}<extra></extra>",
    ))

    # Threshold lines at $10M, $25M, $50M
    for threshold, label in [(10_000_000, "$10M"), (25_000_000, "$25M"), (50_000_000, "$50M")]:
        fig_cum.add_hline(
            y=threshold,
            line_dash="dot",
            line_color=BRAND["accent_orange"],
            annotation_text=label,
            annotation_position="top right",
            annotation_font_color=BRAND["accent_orange"],
        )

    fig_cum.update_layout(
        title="Cumulative 5-Year Capital Commitment",
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickmode="linear", tick0=2026, dtick=1, title="Year", gridcolor="#1a3a5c"),
        yaxis=dict(tickprefix="$", tickformat=",.0f", title="Cumulative Cost ($)", gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40),
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    # Summary caption
    total_5yr = proj_df["total_cost"].sum()
    unknown_count = len(df[df["eos_date"].isna() & df["eol_date"].isna()])
    st.markdown(insight_caption(
        f"This projection represents a **floor** — confirmed refresh cost of **${total_5yr:,.0f}** "
        f"over 5 years for devices with known lifecycle dates. "
        f"An additional **{unknown_count:,} devices** have unknown lifecycle status, "
        f"adding unquantified capital requirements likely exceeding this amount."
    ), unsafe_allow_html=True)

    # Download
    proj_download = proj_df[["hostname", "device_type", "model", "state",
                              "affiliate_code", "eol_year", "total_cost", "risk_tier"]].copy()
    proj_download["eol_year"] = proj_download["eol_year"].astype(str)
    proj_download["total_cost"] = proj_download["total_cost"].round(0)
    csv_proj = proj_download.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download 5-Year Projection CSV",
        data=csv_proj,
        file_name="gridguard_5yr_projection.csv",
        mime="text/csv",
    )
