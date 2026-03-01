"""
6_Exceptions.py — Exception register for devices excluded from refresh planning.
GridGuard Network Intelligence — UA Innovate 2026
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from utils.constants import BRAND, RISK_COLORS
from utils.exceptions import load_exceptions, save_exception, remove_exception

st.set_page_config(
    page_title="Exceptions | GridGuard",
    page_icon="⚡",
    layout="wide",
)

if "df" not in st.session_state:
    st.warning("Upload your dataset on the Home page first.")
    st.stop()

df = st.session_state["df"]

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<h3 style='color:{BRAND['accent_orange']}'>Exceptions</h3>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "Devices added here are excluded from risk analysis and reporting "
        "(unless 'Include Excepted Devices' is toggled on other pages).",
        unsafe_allow_html=False,
    )

# ---------------------------------------------------------------------------
# Heading
# ---------------------------------------------------------------------------
st.markdown(
    f"<h1 style='color:{BRAND['white']}'>Exception Register</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "Track devices that are technically past EoL but have a documented business reason "
    "to remain in production. Each exception includes an automatic 6-month review date."
)
st.divider()

# ---------------------------------------------------------------------------
# Existing exceptions
# ---------------------------------------------------------------------------
exceptions = load_exceptions()

col_exc, col_add = st.columns([2, 1])

with col_exc:
    st.markdown(f"<h2 style='color:{BRAND['white']}'>Current Exceptions</h2>",
                unsafe_allow_html=True)

    if exceptions.empty:
        st.info("No exceptions registered. Use the form on the right to add one.")
    else:
        st.caption(f"**{len(exceptions)}** active exceptions")

        # Highlight exceptions approaching review date
        exc_display = exceptions.copy()
        exc_display["review_date"] = pd.to_datetime(exc_display["review_date"])
        exc_display["days_to_review"] = (
            exc_display["review_date"] - pd.Timestamp("2026-02-28")
        ).dt.days
        exc_display["review_date"] = exc_display["review_date"].dt.strftime("%Y-%m-%d")

        st.dataframe(
            exc_display.rename(columns={
                "device_id":        "Device ID",
                "hostname":         "Hostname",
                "exception_reason": "Reason",
                "exception_date":   "Registered",
                "exception_owner":  "Owner",
                "review_date":      "Review Date",
                "days_to_review":   "Days to Review",
            }),
            use_container_width=True,
        )

        # Overdue review warnings
        overdue = exc_display[exc_display["days_to_review"] < 0]
        if not overdue.empty:
            st.warning(
                f"**{len(overdue)} exception(s) overdue for review.** "
                f"Hostnames: {', '.join(overdue['hostname'].tolist())}"
            )

        upcoming = exc_display[(exc_display["days_to_review"] >= 0) & (exc_display["days_to_review"] <= 30)]
        if not upcoming.empty:
            st.info(
                f"**{len(upcoming)} exception(s) due for review within 30 days.**"
            )

        csv = exceptions.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Exception Register CSV",
            data=csv,
            file_name="exceptions_register.csv",
            mime="text/csv",
        )

        st.divider()
        st.markdown(f"<h3 style='color:{BRAND['white']}'>Remove an Exception</h3>",
                    unsafe_allow_html=True)
        _exc_labels = dict(zip(exceptions["device_id"], exceptions["hostname"]))
        remove_id = st.selectbox(
            "Select device to remove from exceptions",
            options=exceptions["device_id"].tolist(),
            format_func=lambda x: f"{x} — {_exc_labels.get(x, x)}",
        )
        if st.button("Remove Exception", type="secondary"):
            remove_exception(remove_id)
            st.success("Exception removed.")
            st.rerun()

# ---------------------------------------------------------------------------
# Add new exception
# ---------------------------------------------------------------------------
with col_add:
    st.markdown(f"<h2 style='color:{BRAND['white']}'>Add Exception</h2>",
                unsafe_allow_html=True)

    # Risk tier filter — default to high-risk only so selectbox stays fast
    tier_filter = st.multiselect(
        "Filter candidates by risk tier",
        options=["Critical", "High", "Medium", "Low"],
        default=["Critical", "High"],
        key="exc_tier_filter",
        help="Narrow the device list to keep the selector responsive.",
    )
    if not tier_filter:
        tier_filter = ["Critical", "High", "Medium", "Low"]  # fall back to all

    candidates = (
        df[df["risk_tier"].isin(tier_filter)]
        .sort_values("risk_score", ascending=False)
        [["device_id", "hostname", "model", "lifecycle_stage", "risk_score", "risk_tier"]]
    )

    st.caption(f"Showing {len(candidates):,} devices ({', '.join(tier_filter)} risk tiers)")

    # Pre-build O(1) lookup dict — avoids O(n²) pandas masks inside format_func
    _id_to_label = {
        row.device_id: f"{row.hostname} ({row.risk_score:.0f} risk)"
        for row in candidates.itertuples(index=False)
    }

    # Device selection outside the form so the detail preview updates reactively
    selected_id = st.selectbox(
        "Select Device",
        options=candidates["device_id"].tolist(),
        format_func=lambda x: _id_to_label.get(x, x),
        key="exc_device_select",
    )

    if selected_id in candidates["device_id"].values:
        sel_row = candidates[candidates["device_id"] == selected_id].iloc[0]
        st.info(
            f"**{sel_row['hostname']}** | Model: {sel_row['model']} | "
            f"Stage: {sel_row['lifecycle_stage']} | Risk: {sel_row['risk_score']:.0f}/100"
        )

    with st.form("add_exception_form"):
        reason = st.text_area(
            "Exception Reason",
            placeholder="e.g., Hardware under active replacement contract through Q3 2026",
            help="Document why this device should be excluded from refresh planning.",
        )

        owner = st.text_input(
            "Owner / Approver",
            placeholder="e.g., Jane Smith, Network Engineering",
        )

        submitted = st.form_submit_button("Register Exception", type="primary")

        if submitted:
            if not reason.strip():
                st.error("Please provide an exception reason.")
            elif not owner.strip():
                st.error("Please provide an owner/approver name.")
            elif selected_id in exceptions["device_id"].values:
                st.warning("This device already has an exception registered.")
            else:
                hostname = (
                    candidates[candidates["device_id"] == selected_id]["hostname"].values[0]
                    if selected_id in candidates["device_id"].values else selected_id
                )
                save_exception(selected_id, hostname, reason.strip(), owner.strip())
                st.success(
                    f"Exception registered for **{hostname}**. "
                    f"Review scheduled in 6 months."
                )
                st.rerun()

# ---------------------------------------------------------------------------
# Exception impact summary
# ---------------------------------------------------------------------------
st.divider()
st.markdown(f"<h2 style='color:{BRAND['white']}'>Exception Impact Summary</h2>",
            unsafe_allow_html=True)

if not exceptions.empty:
    excepted_devices = df[df["device_id"].isin(exceptions["device_id"])]
    if not excepted_devices.empty:
        exc_cost     = excepted_devices["total_cost"].sum()
        exc_exposure = excepted_devices["risk_cost_exposure"].sum()
        exc_crit     = (excepted_devices["risk_tier"] == "Critical").sum()

        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            st.metric("Excepted Devices", f"{len(excepted_devices):,}")
        with ec2:
            st.metric("Excluded Replacement Cost", f"${exc_cost:,.0f}")
        with ec3:
            st.metric("Excluded Risk Exposure", f"${exc_exposure:,.0f}")

        if exc_crit > 0:
            st.warning(
                f"**{exc_crit} Critical-risk device(s) are currently excepted.** "
                f"Ensure exception reasons are current and reviewed."
            )
    else:
        st.info("Excepted device IDs not found in current dataset.")
else:
    st.info("No exceptions registered — no impact to report.")
