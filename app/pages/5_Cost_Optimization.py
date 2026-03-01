"""
5_Cost_Optimization.py — Replacement cost exposure, savings opportunities, refresh ROI.
GridGuard Network Intelligence — UA Innovate 2026
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.constants import BRAND, RISK_COLORS, RISK_TIER_ORDER, TRUCK_ROLL_SAVINGS_PER_DEVICE, DARK_PLOT_BG, insight_caption
from utils.geo_clustering import cluster_devices_by_radius, build_cluster_summary
from utils.exceptions import apply_exceptions

st.set_page_config(
    page_title="Cost Optimization | GridGuard",
    page_icon="⚡",
    layout="wide",
)

if "df" not in st.session_state:
    st.warning("Upload your dataset on the Home page first.")
    st.stop()

raw_df = st.session_state["df"]

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<h3 style='color:{BRAND['accent_orange']}'>Cost Optimization</h3>",
        unsafe_allow_html=True,
    )
    sel_states = st.multiselect("Filter by State", sorted(raw_df["state"].dropna().unique()))
    sel_types  = st.multiselect("Filter by Device Type", sorted(raw_df["device_type"].dropna().unique()))
    sel_risk   = st.multiselect("Filter by Risk Tier", ["Critical", "High", "Medium", "Low"])
    radius     = st.selectbox("Cluster Radius (miles) for Savings Calc", [1, 5, 10, 25], index=1)
    show_exc   = st.checkbox("Include Excepted Devices", value=False)

df = apply_exceptions(raw_df.copy(), show_exceptions=show_exc)
if sel_states:
    df = df[df["state"].isin(sel_states)]
if sel_types:
    df = df[df["device_type"].isin(sel_types)]
if sel_risk:
    df = df[df["risk_tier"].isin(sel_risk)]

# ---------------------------------------------------------------------------
# Heading
# ---------------------------------------------------------------------------
st.markdown(
    f"<h1 style='color:{BRAND['white']}'>Cost Optimization</h1>",
    unsafe_allow_html=True,
)
st.caption(f"Showing **{len(df):,}** devices")
with st.expander("Cost Estimation Methodology", expanded=False):
    st.markdown("""
**Truck-Roll Savings ($1,500/device):** Estimate based on average field technician dispatch cost per
site visit, including travel time, labor burden, and equipment handling. Batching devices at the same
location eliminates redundant visits — each additional device added to an existing dispatch saves
approximately $1,500.

**Fallback Device Costs** (used when ModelData has no price match):

| Device Type | Est. Unit Cost | Est. Labor |
|-------------|---------------|-----------|
| Switch | $3,500 | $1,200 |
| L3 Switch | $5,000 | $1,500 |
| Router | $5,000 | $1,800 |
| Access Point | $800 | $400 |
| Wireless LAN Controller | $15,000 | $3,000 |
| Voice Gateway | $2,500 | $900 |
| Firewall | $8,000 | $2,500 |
| Unknown | $4,000 | $1,500 |

*Devices with a match in ModelData use the actual Cisco list price from the dataset.*
    """)

st.divider()

# ---------------------------------------------------------------------------
# Top-line cost KPIs
# ---------------------------------------------------------------------------
total_rep_cost   = df["total_cost"].sum()
risk_exposure    = df["risk_cost_exposure"].sum()
crit_cost        = df[df["risk_tier"] == "Critical"]["total_cost"].sum()
past_eol_cost    = df[df["is_past_eol"]]["total_cost"].sum()

geo_df = df[df["latitude"].notna() & df["longitude"].notna()]
if not geo_df.empty:
    clustered = cluster_devices_by_radius(geo_df, radius_miles=radius)
    cluster_summary = build_cluster_summary(clustered)
    truck_savings = int(cluster_summary["estimated_savings"].sum()) if not cluster_summary.empty else 0
else:
    truck_savings = 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Replacement Cost (fleet)", f"${total_rep_cost:,.0f}")
with col2:
    st.metric("Risk-Weighted Exposure", f"${risk_exposure:,.0f}",
              help="Replacement cost × (risk score / 100) — dollars at risk today")
with col3:
    st.metric("Critical Device Cost", f"${crit_cost:,.0f}")
with col4:
    st.metric(
        f"Truck-Roll Savings ({radius}-mi clusters)",
        f"${truck_savings:,}",
        help="Estimated savings from batching co-located devices into one refresh project. "
             "Assumes $1,500 savings per additional device added to an existing dispatch. "
             "See 'Cost Estimation Methodology' above for full assumptions.",
    )

col5, col6, col7, _ = st.columns(4)
with col5:
    st.metric("Past EoL Replacement Cost", f"${past_eol_cost:,.0f}",
              delta="Deferred investment, increasing risk", delta_color="inverse")
with col6:
    pct_exposed = risk_exposure / total_rep_cost * 100 if total_rep_cost else 0
    st.metric("% of Fleet Value at Risk", f"{pct_exposed:.1f}%")
with col7:
    avg_cost = df["total_cost"].mean()
    st.metric("Avg Device Replacement Cost", f"${avg_cost:,.0f}")

st.divider()

# ---------------------------------------------------------------------------
# Cost exposure by state — ranked bar
# ---------------------------------------------------------------------------
st.markdown(f"<h2 style='color:{BRAND['white']}'>Risk Cost Exposure by State</h2>",
            unsafe_allow_html=True)
st.markdown(
    "States ranked by risk-weighted cost exposure — the dollar amount most urgently at risk."
)

state_cost = (
    df.groupby("state")
    .agg(
        total_devices        = ("device_id",           "count"),
        critical_devices     = ("risk_tier",           lambda x: (x == "Critical").sum()),
        total_replacement    = ("total_cost",          "sum"),
        risk_exposure        = ("risk_cost_exposure",  "sum"),
        avg_risk_score       = ("risk_score",          "mean"),
    )
    .reset_index()
    .sort_values("risk_exposure", ascending=False)
)

fig_state_cost = px.bar(
    state_cost.head(20),
    x="risk_exposure",
    y="state",
    orientation="h",
    color="avg_risk_score",
    color_continuous_scale=[BRAND["light_blue"], RISK_COLORS["Critical"]],
    text=state_cost.head(20)["risk_exposure"].apply(lambda x: f"${x:,.0f}"),
    title="Risk Cost Exposure by State (Top 20)",
    labels={
        "risk_exposure":  "Risk-Weighted Exposure ($)",
        "state":          "State",
        "avg_risk_score": "Avg Risk Score",
    },
)
fig_state_cost.update_traces(textposition="outside", textfont_color=BRAND["white"])
fig_state_cost.update_layout(
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    plot_bgcolor=DARK_PLOT_BG,
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#1a3a5c"),
    yaxis=dict(autorange="reversed", gridcolor="#1a3a5c"),
    margin=dict(t=60, b=40, r=120),
    coloraxis_colorbar=dict(title="Avg Risk"),
)
st.plotly_chart(fig_state_cost, use_container_width=True)
st.markdown(insight_caption(
    "Risk exposure = replacement cost × risk score. "
    "States at the top require the most urgent refresh investment."
), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Cost by device type — stacked by risk tier
# ---------------------------------------------------------------------------
st.markdown(f"<h2 style='color:{BRAND['white']}'>Replacement Cost by Device Type & Risk Tier</h2>",
            unsafe_allow_html=True)

type_risk_cost = (
    df.groupby(["device_type", "risk_tier"])["total_cost"]
    .sum()
    .reset_index()
)
type_risk_cost["risk_tier"] = pd.Categorical(
    type_risk_cost["risk_tier"], categories=RISK_TIER_ORDER, ordered=True
)

fig_type_cost = px.bar(
    type_risk_cost,
    x="device_type",
    y="total_cost",
    color="risk_tier",
    color_discrete_map=RISK_COLORS,
    barmode="stack",
    title="Replacement Cost Stack by Device Type",
    labels={
        "device_type": "Device Type",
        "total_cost":  "Total Replacement Cost ($)",
        "risk_tier":   "Risk Tier",
    },
    category_orders={"risk_tier": RISK_TIER_ORDER},
)
fig_type_cost.update_layout(
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    plot_bgcolor=DARK_PLOT_BG,
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#1a3a5c"),
    yaxis=dict(tickformat="$,.0f", gridcolor="#1a3a5c"),
    margin=dict(t=60, b=40),
)
_type_cost_totals = type_risk_cost.groupby("device_type")["total_cost"].sum().reset_index()
for _, _row in _type_cost_totals.iterrows():
    _val = _row["total_cost"]
    _label = f"${_val/1_000_000:.1f}M" if _val >= 1_000_000 else f"${_val:,.0f}"
    fig_type_cost.add_annotation(
        x=_row["device_type"], y=_val,
        text=_label,
        showarrow=False, yshift=10,
        font=dict(color=BRAND["white"], size=11, family="Arial"),
    )
st.plotly_chart(fig_type_cost, use_container_width=True)
st.markdown(insight_caption(
    "Each bar shows the total cost to replace all devices of that type, "
    "colored by urgency. Red = Critical (refresh now)."
), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Batch refresh savings detail
# ---------------------------------------------------------------------------
st.markdown(
    f"<h2 style='color:{BRAND['white']}'>Batch Refresh Savings — {radius}-Mile Clusters</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    f"Batching nearby devices into a single refresh project saves an estimated "
    f"**${TRUCK_ROLL_SAVINGS_PER_DEVICE:,} per co-located device** in truck roll costs."
)

if not geo_df.empty and not cluster_summary.empty:
    display_cs = cluster_summary.copy()
    display_cs["avg_risk_score"]    = display_cs["avg_risk_score"].apply(lambda x: f"{x:.1f}")
    display_cs["total_cost"]        = display_cs["total_cost"].apply(lambda x: f"${x:,.0f}")
    display_cs["estimated_savings"] = display_cs["estimated_savings"].apply(lambda x: f"${x:,.0f}")
    display_cs = display_cs.rename(columns={
        "cluster_id":       "Cluster #",
        "device_count":     "Devices",
        "avg_risk_score":   "Avg Risk Score",
        "critical_count":   "Critical",
        "high_count":       "High",
        "states":           "States",
        "site_names":       "Sample Sites",
        "total_cost":       "Total Replacement Cost",
        "estimated_savings":"Truck-Roll Savings",
    })
    st.dataframe(
        display_cs[[
            "Cluster #", "Devices", "Avg Risk Score", "Critical",
            "States", "Sample Sites", "Total Replacement Cost", "Truck-Roll Savings"
        ]],
        use_container_width=True,
    )

    # Savings waterfall-style bar
    top_clusters = cluster_summary.head(10).copy()
    top_clusters["label"] = top_clusters["cluster_id"].apply(lambda x: f"Cluster {x}")

    fig_savings = px.bar(
        top_clusters,
        x="label",
        y="estimated_savings",
        color="avg_risk_score",
        color_continuous_scale=[BRAND["light_blue"], RISK_COLORS["Critical"]],
        text=top_clusters["estimated_savings"].apply(lambda x: f"${x:,.0f}"),
        title=f"Estimated Truck-Roll Savings — Top 10 Clusters ({radius}-mile radius)",
        labels={"label": "Cluster", "estimated_savings": "Estimated Savings ($)"},
    )
    fig_savings.update_traces(textposition="outside", textfont_color=BRAND["white"])
    fig_savings.update_layout(
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#1a3a5c"),
        yaxis=dict(tickformat="$,.0f", gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40, r=40),
    )
    st.plotly_chart(fig_savings, use_container_width=True)

    csv = cluster_summary.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Savings Opportunities CSV",
        data=csv,
        file_name=f"gridguard_savings_{radius}mi.csv",
        mime="text/csv",
    )
else:
    st.info("No clustered devices found. Adjust cluster radius or filters.")

# ---------------------------------------------------------------------------
# State cost summary table
# ---------------------------------------------------------------------------
st.divider()
st.markdown(f"<h2 style='color:{BRAND['white']}'>State Cost Summary</h2>",
            unsafe_allow_html=True)

state_display = state_cost.copy()
state_display["total_replacement"] = state_display["total_replacement"].apply(lambda x: f"${x:,.0f}")
state_display["risk_exposure"]     = state_display["risk_exposure"].apply(lambda x: f"${x:,.0f}")
state_display["avg_risk_score"]    = state_display["avg_risk_score"].round(1)
state_display = state_display.rename(columns={
    "state":              "State",
    "total_devices":      "Devices",
    "critical_devices":   "Critical",
    "total_replacement":  "Total Replacement Cost",
    "risk_exposure":      "Risk Cost Exposure",
    "avg_risk_score":     "Avg Risk Score",
})
st.dataframe(state_display, use_container_width=True)
csv2 = state_cost.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download State Cost Summary CSV",
    data=csv2,
    file_name="gridguard_state_costs.csv",
    mime="text/csv",
)
