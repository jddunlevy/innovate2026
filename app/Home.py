"""
app.py — GridGuard Network Intelligence | Entry point & Home page.
Southern Company — UA Innovate 2026

Run with:
    streamlit run app/Home.py
"""

import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from utils.constants import BRAND, DEFAULT_DATA_PATH
from utils.data_loader import load_data, load_from_path

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="GridGuard Network Intelligence | Southern Company",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS — Southern Company brand / dark mode premium
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
      /* ── App background ── */
      .stApp {{
          background-color: #050E1A;
      }}

      /* ── Top header bar ── */
      [data-testid="stHeader"] {{
          background-color: {BRAND['dark_blue']};
          border-bottom: 1px solid {BRAND['primary_blue']};
      }}

      /* ── Sidebar ── */
      [data-testid="stSidebar"] {{
          background-color: #070F1E !important;
          border-right: 1px solid #1a3a5c;
      }}
      [data-testid="stSidebar"] .stMarkdown p {{
          color: {BRAND['white']};
          font-family: Arial, sans-serif;
      }}

      /* ── Metric cards ── */
      [data-testid="stMetric"] {{
          background-color: #0D1B2E;
          border: 1px solid #1a3a5c;
          border-radius: 8px;
          padding: 1rem 1.25rem;
      }}
      [data-testid="stMetricLabel"] p,
      [data-testid="stMetricLabel"] div {{
          font-size: 0.78rem;
          font-weight: 600;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: {BRAND['light_blue']} !important;
      }}
      [data-testid="stMetricValue"] {{
          font-size: 1.9rem !important;
          font-weight: 700;
          color: {BRAND['white']} !important;
      }}

      /* ── Headings ── */
      h1, h2, h3 {{
          color: {BRAND['white']};
          font-family: Arial, sans-serif;
          letter-spacing: -0.01em;
      }}
      h1 {{ font-size: 1.8rem; font-weight: 700; }}
      h2 {{ font-size: 1.35rem; font-weight: 600; }}
      h3 {{ font-size: 1.1rem; font-weight: 600; }}

      /* ── Dividers ── */
      hr {{
          border: none;
          border-top: 1px solid #1a3a5c;
          margin: 1.5rem 0;
      }}

      /* ── Tabs ── */
      .stTabs [data-baseweb="tab"][aria-selected="true"] {{
          border-bottom: 3px solid {BRAND['primary_blue']};
          color: {BRAND['primary_blue']};
      }}
      .stTabs [data-baseweb="tab"] {{
          color: #8ab4d4;
          font-family: Arial, sans-serif;
      }}

      /* ── Download buttons ── */
      .stDownloadButton > button {{
          background-color: transparent !important;
          border: 1px solid {BRAND['primary_blue']} !important;
          color: {BRAND['light_blue']} !important;
          font-size: 0.8rem;
          font-weight: 500;
          letter-spacing: 0.03em;
          padding: 0.35rem 0.9rem;
          border-radius: 4px;
          transition: all 0.15s ease;
      }}
      .stDownloadButton > button:hover {{
          background-color: {BRAND['primary_blue']} !important;
          color: {BRAND['white']} !important;
      }}

      /* ── Primary action buttons ── */
      .stButton [data-testid="stBaseButton-primary"] {{
          background-color: {BRAND['primary_blue']} !important;
          border: none !important;
          border-radius: 4px;
      }}

      /* ── Dataframes / tables ── */
      [data-testid="stDataFrame"] {{
          border: 1px solid #1a3a5c;
          border-radius: 6px;
      }}

      /* ── Caption / insight text ── */
      .stCaption {{
          color: {BRAND['light_blue']} !important;
          font-size: 0.82rem;
      }}

      /* ── Expanders ── */
      [data-testid="stExpander"] {{
          border: 1px solid #1a3a5c !important;
          border-radius: 6px;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar — file uploader (shared across pages via session state)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<h2 style='color:{BRAND['accent_orange']}; margin-bottom:0'>⚡ GridGuard</h2>"
        f"<p style='color:{BRAND['light_blue']}; margin-top:0; font-size:0.8rem'>"
        f"Network Intelligence Platform</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    uploaded = st.file_uploader(
        "Upload Dataset (.xlsx)",
        type=["xlsx"],
        help="Upload UAInnovateDataset-SoCo.xlsx to load all data.",
    )

    if uploaded is not None:
        # New file uploaded — reload if hash changed
        file_bytes = uploaded.getvalue()
        file_hash  = hash(file_bytes)
        if st.session_state.get("_file_hash") != file_hash:
            with st.spinner("Processing dataset…"):
                df, qr = load_data(file_bytes)
                st.session_state["df"]             = df
                st.session_state["quality_report"] = qr
                st.session_state["_file_hash"]     = file_hash
            st.success(f"Loaded {len(df):,} devices")
    elif "df" not in st.session_state:
        # Try auto-load from known path (development / demo convenience)
        data_path = Path(DEFAULT_DATA_PATH)
        if data_path.exists():
            st.info(f"Auto-loading from: {DEFAULT_DATA_PATH}")
            with st.spinner("Processing dataset…"):
                with open(data_path, "rb") as f:
                    file_bytes = f.read()
                df, qr = load_data(file_bytes)
                st.session_state["df"]             = df
                st.session_state["quality_report"] = qr
            st.success(f"Loaded {len(df):,} devices")

# ---------------------------------------------------------------------------
# Home page content
# ---------------------------------------------------------------------------
st.markdown(
    f"<h1 style='color:{BRAND['white']}'>⚡ GridGuard Network Intelligence</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<p style='color:{BRAND['white']}; font-size:1.1rem'>"
    f"Southern Company — Enterprise Network Lifecycle Management Platform</p>",
    unsafe_allow_html=True,
)
st.divider()

if "df" not in st.session_state:
    st.warning("Upload your dataset using the sidebar to get started.")
    st.markdown("""
    ### What this platform does
    GridGuard ingests Southern Company's network equipment data across all sources
    (Network Analytics, Catalyst Center, Cisco Prime) and delivers:

    | Page | What you'll find |
    |------|-----------------|
    | Executive Summary | Fleet-wide KPIs, risk exposure, prioritization matrix |
    | Geographic Risk | Interactive device map, radius-based refresh clustering |
    | Device Inventory | Filterable, searchable device table with lifecycle status |
    | Lifecycle Analysis | EoS/EoL timelines, risk score distribution |
    | Cost Optimization | Replacement cost exposure, batch savings opportunities |
    | Exceptions | Register devices with documented exclusion reasons |

    **Navigate using the sidebar pages after uploading your dataset.**
    """)
else:
    df = st.session_state["df"]
    qr = st.session_state["quality_report"]

    # Quick stats on home page
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Active Devices", f"{len(df):,}")
    with col2:
        crit = (df["risk_tier"] == "Critical").sum()
        st.metric("Critical Risk Devices", f"{crit:,}",
                  delta=f"{crit/len(df)*100:.1f}% of fleet",
                  delta_color="inverse")
    with col3:
        exposure = df["risk_cost_exposure"].sum()
        st.metric("Risk Cost Exposure", f"${exposure:,.0f}")
    with col4:
        past_eol = df["is_past_eol"].sum()
        st.metric("Past End of Life", f"{past_eol:,}",
                  delta="Unsupported in production",
                  delta_color="inverse")

    st.divider()

    # Data quality report
    with st.expander("Data Quality Report", expanded=False):
        st.markdown("#### How This Data Was Built")
        st.markdown("""
| Step | What Happens |
|------|-------------|
| **1. Excel Load** | Three source tabs loaded: `Network Analytics (NA)`, `Catalyst Center (CatCtr)`, `Prime Infrastructure` |
| **2. Active Filter** | Inactive/unreachable devices removed. NA: `status == active`. CatCtr: `reachabilityStatus == reachable`. Prime: `reachability == REACHABLE` |
| **3. Deduplication** | CatCtr wins over Prime wins over NA for the same device hostname. Wireless (AP/WLC) types in NA are dropped — CatCtr and Prime are authoritative for those |
| **4. Decom Sites** | Sites flagged in the Decommissioned tab are excluded entirely |
| **5. Site Join** | Hostname prefix (chars 0–4) matched to SOLID-Loc for street address, city, state, county, latitude, and longitude |
| **6. Model Join** | Device model matched to ModelData for EoS date, EoL date, replacement model, and cost data. Unmatched models use category-level cost estimates |
| **7. Risk Scoring** | Each device scored 0–100 based on lifecycle status (EoL/EoS flags) and device uptime |
        """)
        st.markdown("---")
        st.markdown("#### Source Row Counts and Pipeline Decisions")
        report_items = {
            "NA tab raw rows":                    qr.get("na_raw_rows", "—"),
            "NA inactive excluded":               qr.get("na_inactive_excluded", "—"),
            "NA wireless controllers excluded":   qr.get("na_wireless_ctrl_excluded", "—"),
            "NA devices kept":                    qr.get("na_active_kept", "—"),
            "Catalyst Center raw rows":           qr.get("catctr_raw_rows", "—"),
            "CatCtr non-AP/WLC excluded":         qr.get("catctr_non_ap_wlc_excluded", "—"),
            "CatCtr unreachable excluded":        qr.get("catctr_unreachable_excluded", "—"),
            "CatCtr AP/WLC devices kept":         qr.get("catctr_ap_wlc_kept", "—"),
            "Prime AP rows":                      qr.get("prime_ap_rows", "—"),
            "Prime WLC rows":                     qr.get("prime_wlc_rows", "—"),
            "Decommissioned sites excluded":      qr.get("decom_excluded", "—"),
            "Combined (pre-decom)":               qr.get("combined_pre_decom", "—"),
            "Site address join matched":          qr.get("site_join_matched", "—"),
            "Site join no match":                 qr.get("site_join_no_match", "—"),
            "Lat/lon available":                  qr.get("lat_lon_available", "—"),
            "Model lifecycle join matched":       qr.get("model_join_matched", "—"),
            "Model join no match (fallback costs)": qr.get("model_join_no_match", "—"),
            "Duplicate device IDs (should be 0)": qr.get("duplicate_device_ids", "—"),
            "Final device count":                 qr.get("final_device_count", "—"),
        }
        for k, v in report_items.items():
            st.markdown(f"- **{k}:** {v}")

    st.markdown("### Navigate to a page using the sidebar to begin analysis.")
