"""
2_Geographic_Risk.py — Interactive device map + DBSCAN radius clustering.
GridGuard Network Intelligence — UA Innovate 2026
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.constants import BRAND, RISK_COLORS, RISK_TIER_ORDER, DARK_PLOT_BG, insight_caption
from utils.geo_clustering import cluster_devices_by_radius, build_cluster_summary
from utils.exceptions import apply_exceptions

st.set_page_config(
    page_title="Geographic Risk | GridGuard",
    page_icon="⚡",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
if "df" not in st.session_state:
    st.warning("Upload your dataset on the Home page first.")
    st.stop()

raw_df = st.session_state["df"]

with st.sidebar:
    st.markdown(
        f"<h3 style='color:{BRAND['accent_orange']}'>Geographic Risk</h3>",
        unsafe_allow_html=True,
    )

    radius = st.selectbox(
        "Cluster Radius (miles)",
        [1, 5, 10, 25],
        index=1,
        help="Devices within this radius can be batched into one refresh project.",
    )

    states = sorted(raw_df["state"].dropna().unique())
    sel_states = st.multiselect("Filter by State", states)

    # County filter — scoped to selected states when states are active
    county_source = raw_df[raw_df["state"].isin(sel_states)] if sel_states else raw_df
    counties = sorted(county_source["county"].dropna().unique()) if "county" in county_source.columns else []
    sel_counties = st.multiselect("Filter by County", counties)

    sel_risk = st.multiselect(
        "Show Risk Tiers",
        ["Critical", "High", "Medium", "Low"],
        default=["Critical", "High", "Medium", "Low"],
    )

    sel_types = st.multiselect(
        "Filter by Device Type",
        sorted(raw_df["device_type"].dropna().unique()),
    )

    show_exc = st.checkbox("Include Excepted Devices", value=False)

df = apply_exceptions(raw_df.copy(), show_exceptions=show_exc)

if sel_states:
    df = df[df["state"].isin(sel_states)]
if sel_counties and "county" in df.columns:
    df = df[df["county"].isin(sel_counties)]
if sel_risk:
    df = df[df["risk_tier"].isin(sel_risk)]
if sel_types:
    df = df[df["device_type"].isin(sel_types)]

# ---------------------------------------------------------------------------
# Heading & KPIs
# ---------------------------------------------------------------------------
st.markdown(
    f"<h1 style='color:{BRAND['white']}'>Geographic Risk Map</h1>",
    unsafe_allow_html=True,
)

geo_df = df[df["latitude"].notna() & df["longitude"].notna()]
no_geo = len(df) - len(geo_df)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Devices with Location Data", f"{len(geo_df):,}")
with col2:
    st.metric("No Location Data", f"{no_geo:,}", delta="Hostname/site not in SOLID", delta_color="off")
with col3:
    crit_geo = (geo_df["risk_tier"] == "Critical").sum()
    st.metric("Critical Devices on Map", f"{crit_geo:,}")

st.divider()

# ---------------------------------------------------------------------------
# Scatter map — individual devices
# ---------------------------------------------------------------------------
st.markdown(f"<h2 style='color:{BRAND['white']}'>Device Risk Map</h2>",
            unsafe_allow_html=True)

if geo_df.empty:
    st.info("No devices with location data match current filters.")
else:
    fig_map = px.scatter_mapbox(
        geo_df,
        lat="latitude",
        lon="longitude",
        color="risk_tier",
        color_discrete_map=RISK_COLORS,
        size="risk_score",
        size_max=8,
        hover_name="hostname",
        hover_data={
            "device_type":     True,
            "model":           True,
            "lifecycle_stage": True,
            "risk_score":      ":.1f",
            "site_name":       True,
            "state":           True,
            "latitude":        False,
            "longitude":       False,
            "risk_tier":       False,
        },
        zoom=5,
        mapbox_style="carto-positron",
        title=f"Device Risk Locations ({len(geo_df):,} devices)",
        category_orders={"risk_tier": RISK_TIER_ORDER},
    )
    fig_map.update_layout(
        margin=dict(t=40, b=0, l=0, r=0),
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(title="Risk Tier", orientation="v"),
        mapbox_style="carto-darkmatter",
    )
    st.plotly_chart(fig_map, use_container_width=True)
    st.markdown(insight_caption(
        f"Each dot is a physical device plotted at its real-world location. Bigger dots carry higher risk scores, "
        f"and red dots are critical. Click or hover any dot to see the device name, type, site, and risk details. "
        f"Showing {len(geo_df):,} devices with confirmed location data."
    ), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Choropleth — critical devices by state
# ---------------------------------------------------------------------------
st.markdown(f"<h2 style='color:{BRAND['white']}'>State-Level Risk Heat Map</h2>",
            unsafe_allow_html=True)

state_agg = (
    df.groupby("state")
    .agg(
        critical_devices = ("risk_tier",    lambda x: (x == "Critical").sum()),
        total_devices    = ("device_id",    "count"),
        avg_risk_score   = ("risk_score",   "mean"),
        total_exposure   = ("risk_cost_exposure", "sum"),
    )
    .reset_index()
)

# Map 2-char state codes to full state names for choropleth
state_agg["state_code"] = state_agg["state"]  # already 2-char

fig_choro = px.choropleth(
    state_agg,
    locations="state_code",
    locationmode="USA-states",
    color="critical_devices",
    scope="usa",
    color_continuous_scale=[BRAND["light_blue"], BRAND["primary_blue"], BRAND["dark_blue"]],
    hover_name="state_code",
    hover_data={
        "critical_devices": True,
        "total_devices":    True,
        "avg_risk_score":   ":.1f",
        "total_exposure":   ":,.0f",
        "state_code":       False,
    },
    title="Critical Risk Device Count by State",
    labels={
        "critical_devices": "Critical Devices",
        "total_devices":    "Total Devices",
        "avg_risk_score":   "Avg Risk Score",
        "total_exposure":   "Risk Exposure ($)",
    },
)
fig_choro.update_layout(
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    paper_bgcolor="rgba(0,0,0,0)",
    geo=dict(bgcolor="rgba(0,0,0,0)", lakecolor="#0D1B2E", landcolor="#0D1B2E"),
    margin=dict(t=50, b=0),
    coloraxis_colorbar=dict(title="Critical<br>Devices"),
)
st.plotly_chart(fig_choro, use_container_width=True)
st.markdown(insight_caption("Darker shading means more critical-risk devices in that state. Use this to quickly identify which regions of Southern Company's territory need the most urgent network attention. Hover any state for a full breakdown of device counts and cost exposure."), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Radius clustering — batch refresh opportunities
# ---------------------------------------------------------------------------
st.markdown(
    f"<h2 style='color:{BRAND['white']}'>Refresh Clustering — {radius}-Mile Radius</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    f"Devices within **{radius} miles** of each other can be batched into a single "
    f"refresh project, eliminating redundant truck rolls at **~$1,500 savings per device**."
)

if not geo_df.empty:
    clustered_df = cluster_devices_by_radius(geo_df, radius_miles=radius)
    cluster_summary = build_cluster_summary(clustered_df)

    n_clusters  = len(cluster_summary)
    n_clustered = int((clustered_df["cluster_id"] >= 0).sum())
    total_savings = int(cluster_summary["estimated_savings"].sum()) if not cluster_summary.empty else 0

    kc1, kc2, kc3 = st.columns(3)
    with kc1:
        st.metric("Refresh Clusters Identified", f"{n_clusters:,}")
    with kc2:
        st.metric("Devices Eligible for Batching", f"{n_clustered:,}")
    with kc3:
        st.metric("Estimated Truck-Roll Savings", f"${total_savings:,}")

    if not cluster_summary.empty:
        # Map cluster centers
        fig_clusters = px.scatter_mapbox(
            cluster_summary,
            lat="lat_center",
            lon="lon_center",
            size="device_count",
            color="avg_risk_score",
            color_continuous_scale=[BRAND["light_blue"], RISK_COLORS["Critical"]],
            hover_name="cluster_id",
            hover_data={
                "device_count":     True,
                "avg_risk_score":   ":.1f",
                "critical_count":   True,
                "states":           True,
                "estimated_savings":":.0f",
                "lat_center":       False,
                "lon_center":       False,
            },
            size_max=40,
            zoom=5,
            mapbox_style="carto-positron",
            title=f"Refresh Clusters ({radius}-mile radius) — {n_clusters} opportunities",
        )
        fig_clusters.update_layout(
            margin=dict(t=40, b=0, l=0, r=0),
            title_font_color=BRAND["white"],
            font=dict(color=BRAND["white"], family="Arial"),
            paper_bgcolor="rgba(0,0,0,0)",
            coloraxis_colorbar=dict(title="Avg Risk<br>Score"),
            mapbox_style="carto-darkmatter",
        )
        st.plotly_chart(fig_clusters, use_container_width=True)
        st.markdown(insight_caption(
            "Each bubble is a group of nearby devices that can be upgraded in a single site visit — "
            "fewer truck rolls, lower total cost. Bigger bubbles mean more devices can be batched together. "
            "Brighter-colored clusters carry higher average risk and should be scheduled first."
        ), unsafe_allow_html=True)

        # Cluster summary table
        st.markdown(f"<h3 style='color:{BRAND['white']}'>Top Clusters by Risk</h3>",
                    unsafe_allow_html=True)
        display_summary = cluster_summary.head(20).copy()
        display_summary["avg_risk_score"]    = display_summary["avg_risk_score"].apply(lambda x: f"{x:.1f}")
        display_summary["total_cost"]        = display_summary["total_cost"].apply(lambda x: f"${x:,.0f}")
        display_summary["estimated_savings"] = display_summary["estimated_savings"].apply(lambda x: f"${x:,.0f}")
        display_summary = display_summary.rename(columns={
            "cluster_id":       "Cluster",
            "device_count":     "Devices",
            "avg_risk_score":   "Avg Risk",
            "critical_count":   "Critical",
            "high_count":       "High",
            "states":           "States",
            "site_names":       "Sites (sample)",
            "total_cost":       "Total Replacement Cost",
            "estimated_savings":"Est. Truck-Roll Savings",
        })
        st.dataframe(display_summary[[
            "Cluster", "Devices", "Avg Risk", "Critical", "High",
            "States", "Sites (sample)", "Total Replacement Cost", "Est. Truck-Roll Savings"
        ]], use_container_width=True)

        csv = cluster_summary.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Cluster Summary CSV",
            data=csv,
            file_name=f"gridguard_clusters_{radius}mi.csv",
            mime="text/csv",
        )
else:
    st.info("No location data available for clustering with current filters.")

# ---------------------------------------------------------------------------
# County-level risk summary
# ---------------------------------------------------------------------------
if "county" in df.columns:
    st.divider()
    st.markdown(f"<h2 style='color:{BRAND['white']}'>County-Level Risk Summary</h2>",
                unsafe_allow_html=True)

    county_summary = (
        df[df["county"].notna()]
        .groupby(["state", "county"])
        .agg(
            total_devices   = ("device_id",          "count"),
            critical_devices= ("risk_tier",          lambda x: (x == "Critical").sum()),
            avg_risk_score  = ("risk_score",         "mean"),
            total_exposure  = ("risk_cost_exposure", "sum"),
        )
        .reset_index()
        .sort_values("critical_devices", ascending=False)
    )

    if not county_summary.empty:
        county_display = county_summary.copy()
        county_display["avg_risk_score"] = county_display["avg_risk_score"].round(1)
        county_display["total_exposure"] = county_display["total_exposure"].apply(lambda x: f"${x:,.0f}")
        county_display = county_display.rename(columns={
            "state":           "State",
            "county":          "County",
            "total_devices":   "Devices",
            "critical_devices":"Critical",
            "avg_risk_score":  "Avg Risk Score",
            "total_exposure":  "Risk Exposure",
        })
        st.dataframe(county_display, use_container_width=True)
        st.download_button(
            "Download County Risk Summary CSV",
            data=county_display.to_csv(index=False).encode("utf-8"),
            file_name="gridguard_county_risk.csv",
            mime="text/csv",
        )
    else:
        st.info("No county data available for current filters.")
