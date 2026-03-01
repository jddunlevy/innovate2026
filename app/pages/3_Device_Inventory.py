"""
3_Device_Inventory.py — Filterable, searchable device table with full lifecycle status.
GridGuard Network Intelligence — UA Innovate 2026
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

pd.set_option("styler.render.max_elements", 500_000)

from utils.constants import BRAND, RISK_COLORS, RISK_TIER_ORDER
from utils.exceptions import apply_exceptions

st.set_page_config(
    page_title="Device Inventory | GridGuard",
    page_icon="⚡",
    layout="wide",
)

if "df" not in st.session_state:
    st.warning("Upload your dataset on the Home page first.")
    st.stop()

raw_df = st.session_state["df"]

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<h3 style='color:{BRAND['accent_orange']}'>Device Inventory</h3>",
        unsafe_allow_html=True,
    )

    search = st.text_input("Search hostname / model", placeholder="e.g. SW, C9300, GA")

    states = sorted(raw_df["state"].dropna().unique())
    sel_states = st.multiselect("Filter by State", states)

    # County filter — scoped to selected states when states are active
    county_source = raw_df[raw_df["state"].isin(sel_states)] if sel_states else raw_df
    counties = sorted(county_source["county"].dropna().unique()) if "county" in county_source.columns else []
    sel_counties = st.multiselect("Filter by County", counties)

    types = sorted(raw_df["device_type"].dropna().unique())
    sel_types = st.multiselect("Filter by Device Type", types)

    sources = sorted(raw_df["source"].dropna().unique())
    sel_sources = st.multiselect("Filter by Data Source", sources)

    sel_risk = st.multiselect(
        "Filter by Risk Tier",
        ["Critical", "High", "Medium", "Low"],
    )

    sel_stages = st.multiselect(
        "Filter by Lifecycle Stage",
        sorted(raw_df["lifecycle_stage"].dropna().unique()),
    )

    show_exc = st.checkbox("Include Excepted Devices", value=False)

df = apply_exceptions(raw_df.copy(), show_exceptions=show_exc)

if search:
    mask = (
        df["hostname"].astype(str).str.contains(search, case=False, na=False)
        | df["model"].astype(str).str.contains(search, case=False, na=False)
    )
    df = df[mask]
if sel_states:
    df = df[df["state"].isin(sel_states)]
if sel_counties and "county" in df.columns:
    df = df[df["county"].isin(sel_counties)]
if sel_types:
    df = df[df["device_type"].isin(sel_types)]
if sel_sources:
    df = df[df["source"].isin(sel_sources)]
if sel_risk:
    df = df[df["risk_tier"].isin(sel_risk)]
if sel_stages:
    df = df[df["lifecycle_stage"].isin(sel_stages)]

# ---------------------------------------------------------------------------
# Page content
# ---------------------------------------------------------------------------
st.markdown(
    f"<h1 style='color:{BRAND['white']}'>Device Inventory</h1>",
    unsafe_allow_html=True,
)
st.caption(f"Showing **{len(df):,}** of {len(raw_df):,} devices")
st.divider()

# Summary counts row
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Devices Shown", f"{len(df):,}")
with col2:
    st.metric("Unique Models", f"{df['model'].nunique():,}")
with col3:
    st.metric("Unique Sites", f"{df['site_name'].nunique():,}")
with col4:
    st.metric("States Covered", f"{df['state'].nunique():,}")

st.divider()

# ---------------------------------------------------------------------------
# Display table
# ---------------------------------------------------------------------------
display_cols = {
    "hostname":       "Hostname",
    "device_type":    "Type",
    "model":          "Model",
    "serial_number":  "Serial",
    "state":          "State",
    "county":         "County",
    "site_name":      "Site",
    "source":         "Source",
    "software_version": "SW Version",
    "eos_date":       "End of Sale",
    "eol_date":       "End of Life",
    "days_to_eos":    "Days to EoS",
    "days_to_eol":    "Days to EoL",
    "lifecycle_stage":"Lifecycle Stage",
    "risk_score":     "Risk Score",
    "risk_tier":      "Risk Tier",
    "total_cost":     "Replacement Cost ($)",
    "support_level":  "Support Level",
}

# Only keep columns that exist in the dataframe
display_cols = {k: v for k, v in display_cols.items() if k in df.columns}

table_df = df[list(display_cols.keys())].rename(columns=display_cols).copy()

# Format dates
for col in ["End of Sale", "End of Life"]:
    if col in table_df.columns:
        table_df[col] = pd.to_datetime(table_df[col]).dt.strftime("%Y-%m-%d")

# Format cost
table_df["Replacement Cost ($)"] = table_df["Replacement Cost ($)"].apply(
    lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
)

# Format risk score
table_df["Risk Score"] = table_df["Risk Score"].apply(
    lambda x: f"{x:.1f}" if pd.notna(x) else "—"
)

# Format days (show negative as "X days ago")
for dcol in ["Days to EoS", "Days to EoL"]:
    def _fmt_days(v):
        if pd.isna(v):
            return "—"
        v = int(v)
        if v < 0:
            return f"{abs(v)} days ago"
        return f"in {v} days"
    table_df[dcol] = table_df[dcol].apply(_fmt_days)

st.dataframe(
    table_df.style.map(
        lambda v: f"background-color:{RISK_COLORS.get(v, 'transparent')}; color:white"
        if v in RISK_COLORS else "",
        subset=["Risk Tier"],
    ),
    use_container_width=True,
    height=600,
)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download Filtered Inventory as CSV",
    data=csv,
    file_name="gridguard_inventory_filtered.csv",
    mime="text/csv",
)

# ---------------------------------------------------------------------------
# Device type breakdown table
# ---------------------------------------------------------------------------
st.divider()
st.markdown(f"<h2 style='color:{BRAND['white']}'>Inventory Summary by Device Type</h2>",
            unsafe_allow_html=True)

type_summary = (
    df.groupby("device_type")
    .agg(
        total       = ("device_id",    "count"),
        critical    = ("risk_tier",    lambda x: (x == "Critical").sum()),
        high        = ("risk_tier",    lambda x: (x == "High").sum()),
        past_eol    = ("is_past_eol",  "sum"),
        past_eos    = ("is_past_eos",  "sum"),
        avg_risk    = ("risk_score",   "mean"),
        total_cost  = ("total_cost",   "sum"),
    )
    .reset_index()
    .sort_values("critical", ascending=False)
)
type_summary.columns = [
    "Device Type", "Total", "Critical", "High",
    "Past EoL", "Past EoS", "Avg Risk Score", "Total Replacement Cost ($)"
]
type_summary["Avg Risk Score"] = type_summary["Avg Risk Score"].round(1)
type_summary["Total Replacement Cost ($)"] = type_summary["Total Replacement Cost ($)"].apply(
    lambda x: f"${x:,.0f}"
)
st.dataframe(type_summary, use_container_width=True)
