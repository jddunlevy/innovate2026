"""
7_Predictive_Intelligence.py — ML-powered predictive layer for GridGuard.
UA Innovate 2026 — Southern Company

Four ML features:
  A. Lifecycle Status Predictor  — GBT predicts EoL risk on 9,004 unlabeled devices
  B. Budget Optimizer            — Greedy ROI allocator maximizes risk eliminated per $
  C. Feature Importance          — Permutation importance + device explainer
  D. Anomaly Detection           — IsolationForest flags 750 hidden-risk devices
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.constants import BRAND, RISK_COLORS, RISK_TIER_ORDER, DARK_PLOT_BG, insight_caption
from utils.exceptions import apply_exceptions
from utils.ml_models import (
    compute_permutation_importance,
    detect_anomalies,
    optimize_refresh_budget,
    predict_unknown_lifecycle,
    train_lifecycle_predictor,
)

st.set_page_config(
    page_title="Predictive Intelligence | GridGuard",
    page_icon="⚡",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Cached wrappers — keep models in memory across reruns
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Training lifecycle predictor…")
def _cached_train(df_hash: int, _df: pd.DataFrame) -> dict:
    """Train and cache the lifecycle predictor. df_hash forces refresh on new data."""
    return train_lifecycle_predictor(_df)


@st.cache_data(show_spinner="Running predictions on unlabeled devices…")
def _cached_predictions(_df: pd.DataFrame, _artifacts_hash: int) -> pd.DataFrame:
    """Cache prediction results — recomputes only when df or model changes."""
    artifacts = st.session_state.get("_ml_artifacts")
    if artifacts is None:
        return pd.DataFrame()
    return predict_unknown_lifecycle(_df, artifacts)


@st.cache_data(show_spinner="Detecting anomalies across full fleet…")
def _cached_anomalies(_df: pd.DataFrame) -> pd.DataFrame:
    """Cache IsolationForest results."""
    return detect_anomalies(_df)


# ---------------------------------------------------------------------------
# Guard: dataset must be loaded first
# ---------------------------------------------------------------------------
if "df" not in st.session_state:
    st.warning("Upload your dataset on the Home page first.")
    st.stop()

raw_df = st.session_state["df"]

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<h3 style='color:{BRAND['accent_orange']}'>Predictive Intelligence</h3>",
        unsafe_allow_html=True,
    )
    sel_states = st.multiselect(
        "Filter by State",
        sorted(raw_df["state"].dropna().unique()),
        key="pi_states",
    )
    sel_types = st.multiselect(
        "Filter by Device Type",
        sorted(raw_df["device_type"].dropna().unique()),
        key="pi_types",
    )
    show_exc = st.checkbox("Include Excepted Devices", value=False, key="pi_exc")

df = apply_exceptions(raw_df.copy(), show_exceptions=show_exc)
if sel_states:
    df = df[df["state"].isin(sel_states)]
if sel_types:
    df = df[df["device_type"].isin(sel_types)]

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.markdown(
    f"<h1 style='color:{BRAND['white']}'>Predictive Intelligence</h1>",
    unsafe_allow_html=True,
)
st.caption(
    f"Showing **{len(df):,}** devices | "
    f"Labeled (has lifecycle data): **{int((df['eos_date'].notna() | df['eol_date'].notna()).sum()):,}** | "
    f"Unlabeled: **{int((df['eos_date'].isna() & df['eol_date'].isna()).sum()):,}**"
)
st.divider()


# ===========================================================================
# Feature A — Lifecycle Status Predictor
# ===========================================================================
st.markdown(
    f"<h2 style='color:{BRAND['white']}'>A. Lifecycle Status Predictor</h2>",
    unsafe_allow_html=True,
)
st.info(
    "**Data quality note:** All devices in the labeled training set already have EoS or EoL dates, "
    "meaning the model estimates *severity* (past EoL vs. EoS-only) rather than *presence* of risk. "
    "For the 9,004 unlabeled devices, predictions represent the model's best estimate of lifecycle status "
    "based on device type, location, uptime, and cost patterns."
)

# Train model (cached per unique df state)
df_hash = hash(tuple(sorted(df["device_id"].tolist())) if len(df) < 20000 else str(len(df)))

try:
    with st.spinner("Training GradientBoosting classifier on labeled devices…"):
        artifacts = _cached_train(df_hash, df)
    st.session_state["_ml_artifacts"] = artifacts
    train_ok = True
except ValueError as e:
    st.error(f"Model training failed: {e}")
    train_ok = False

if train_ok:
    # Predictions on unlabeled devices
    unknown_preds = predict_unknown_lifecycle(df, artifacts)
    n_unknown = len(unknown_preds)

    # KPI row
    likely_eol_count = int((unknown_preds["predicted_lifecycle_tier"] == "Likely Past EoL").sum()) if n_unknown > 0 else 0
    likely_eos_count = int((unknown_preds["predicted_lifecycle_tier"] == "Likely Past EoS Only").sum()) if n_unknown > 0 else 0
    accuracy_pct = artifacts["accuracy"] * 100

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Unlabeled Devices Analyzed", f"{n_unknown:,}")
    with col2:
        st.metric(
            "Predicted Likely Past EoL",
            f"{likely_eol_count:,}",
            delta=f"{likely_eol_count/n_unknown*100:.1f}% of unknowns" if n_unknown > 0 else "—",
            delta_color="inverse",
        )
    with col3:
        st.metric(
            "Predicted Likely Past EoS",
            f"{likely_eos_count:,}",
            delta=f"{likely_eos_count/n_unknown*100:.1f}% of unknowns" if n_unknown > 0 else "—",
            delta_color="off",
        )
    with col4:
        st.metric(
            "Model Holdout Accuracy",
            f"{accuracy_pct:.1f}%",
            delta=f"n={artifacts['n_test']} test devices",
            delta_color="off",
        )

    if n_unknown > 0:
        st.markdown("---")

        # Stacked bar: predicted tier by device_type
        tier_type = (
            unknown_preds.groupby(["device_type", "predicted_lifecycle_tier"])
            .size()
            .reset_index(name="count")
        )
        tier_color_map = {
            "Likely Past EoL":     RISK_COLORS["Critical"],
            "Likely Past EoS Only": RISK_COLORS["High"],
            "Likely Active":        RISK_COLORS["Low"],
        }
        fig_tier = px.bar(
            tier_type,
            x="device_type",
            y="count",
            color="predicted_lifecycle_tier",
            color_discrete_map=tier_color_map,
            title="Predicted Lifecycle Tier by Device Type",
            labels={
                "device_type":              "Device Type",
                "count":                    "Device Count",
                "predicted_lifecycle_tier": "Predicted Tier",
            },
            barmode="stack",
        )
        fig_tier.update_layout(
            title_font_color=BRAND["white"],
            font=dict(color=BRAND["white"], family="Arial"),
            plot_bgcolor=DARK_PLOT_BG,
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(tickangle=-30, gridcolor="#1a3a5c"),
            yaxis=dict(gridcolor="#1a3a5c"),
            margin=dict(t=60, b=40),
        )
        st.plotly_chart(fig_tier, use_container_width=True)

        st.markdown("---")

        # Histogram of predicted EoL probability
        fig_hist = px.histogram(
            unknown_preds,
            x="predicted_eol_probability",
            nbins=30,
            title="Distribution of Predicted EoL Probability",
            labels={
                "predicted_eol_probability": "P(Past EoL)",
                "count": "Device Count",
            },
            color_discrete_sequence=[BRAND["primary_blue"]],
        )
        fig_hist.add_vline(
            x=0.65, line_dash="dash", line_color=RISK_COLORS["Critical"],
            annotation_text="EoL threshold (0.65)",
            annotation_position="top right",
            annotation_font_color=RISK_COLORS["Critical"],
        )
        fig_hist.add_vline(
            x=0.40, line_dash="dot", line_color=BRAND["accent_orange"],
            annotation_text="EoS threshold (0.40)",
            annotation_position="top left",
            annotation_font_color=BRAND["accent_orange"],
        )
        fig_hist.update_layout(
            title_font_color=BRAND["white"],
            font=dict(color=BRAND["white"], family="Arial"),
            plot_bgcolor=DARK_PLOT_BG,
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#1a3a5c"),
            yaxis=dict(gridcolor="#1a3a5c"),
            margin=dict(t=60, b=40),
        )
        st.plotly_chart(fig_hist, use_container_width=True)

        # Top 20 "hidden risk" devices
        st.markdown(
            f"<h3 style='color:{BRAND['white']}'>Top 20 Hidden Risk Devices</h3>",
            unsafe_allow_html=True,
        )
        st.caption("Devices with no lifecycle data but highest predicted probability of being past End-of-Life.")

        top20 = (
            unknown_preds[unknown_preds["predicted_lifecycle_tier"] == "Likely Past EoL"]
            .sort_values("predicted_eol_probability", ascending=False)
            .head(20)
        )[["hostname", "device_type", "state", "affiliate_code", "model",
           "predicted_eol_probability", "predicted_lifecycle_tier", "total_cost", "risk_score"]]

        if not top20.empty:
            display_top20 = top20.copy()
            display_top20["predicted_eol_probability"] = (
                display_top20["predicted_eol_probability"] * 100
            ).round(1).astype(str) + "%"
            display_top20["total_cost"] = display_top20["total_cost"].apply(
                lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
            )
            display_top20 = display_top20.rename(columns={
                "hostname":                   "Hostname",
                "device_type":                "Type",
                "state":                      "State",
                "affiliate_code":             "Affiliate",
                "model":                      "Model",
                "predicted_eol_probability":  "P(EoL)",
                "predicted_lifecycle_tier":   "Predicted Tier",
                "total_cost":                 "Replacement Cost",
                "risk_score":                 "Risk Score",
            })
            st.dataframe(display_top20, use_container_width=True)
            csv_top20 = top20.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Hidden Risk Devices CSV",
                data=csv_top20,
                file_name="gridguard_hidden_risk_devices.csv",
                mime="text/csv",
            )
        else:
            st.info("No devices predicted as Likely Past EoL under current filters.")

    st.markdown(insight_caption(
        f"Of the **{n_unknown:,}** devices with no Cisco lifecycle record, the model estimates "
        f"**{likely_eol_count:,}** are probably already past end-of-life — hidden risk not captured anywhere else in the dataset. "
        f"The model was trained on {artifacts['n_train']:,} devices where lifecycle dates are confirmed "
        f"and achieved **{accuracy_pct:.1f}%** accuracy on devices it had never seen before."
    ), unsafe_allow_html=True)

st.divider()


# ===========================================================================
# Feature B — Budget Optimizer
# ===========================================================================
st.markdown(
    f"<h2 style='color:{BRAND['white']}'>B. Refresh Budget Optimizer</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "The optimizer ranks Critical and High risk devices by **risk exposure eliminated per dollar spent** "
    "and greedily selects devices until the budget is exhausted. Move the slider to see which devices "
    "would be refreshed at different investment levels."
)

budget = st.slider(
    "Refresh Budget ($)",
    min_value=1_000_000,
    max_value=50_000_000,
    value=10_000_000,
    step=500_000,
    format="$%d",
    key="budget_slider",
)

selected_devices, opt_summary = optimize_refresh_budget(df, budget)

# KPI row
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Devices Selected", f"{opt_summary['devices_selected']:,}")
with col2:
    st.metric("Budget Used", f"${opt_summary['budget_used']:,.0f}",
              delta=f"${opt_summary['budget_remaining']:,.0f} remaining",
              delta_color="off")
with col3:
    st.metric("Risk Exposure Eliminated", f"${opt_summary['exposure_eliminated']:,.0f}")
with col4:
    roi_str = f"${opt_summary['roi_ratio']:.2f} of risk per $1 spent"
    st.metric("Optimization ROI", roi_str)

if not selected_devices.empty:
    # Horizontal bar by state
    state_budget = (
        selected_devices.groupby("state")
        .agg(devices=("device_id", "count"), cost=("total_cost", "sum"))
        .reset_index()
        .sort_values("cost", ascending=True)
        .tail(15)  # top 15 states
    )
    fig_state_bar = px.bar(
        state_budget,
        x="cost",
        y="state",
        orientation="h",
        color="devices",
        color_continuous_scale=["#6CACE4", "#003865"],
        title="Budget Allocation by State",
        labels={"cost": "Refresh Cost ($)", "state": "State", "devices": "Devices"},
        text_auto=False,
    )
    fig_state_bar.update_traces(
        texttemplate="%{x:$,.0f}",
        textposition="outside",
        textfont_color=BRAND["white"],
    )
    fig_state_bar.update_layout(
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#1a3a5c"),
        yaxis=dict(gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40, r=80),
    )
    st.plotly_chart(fig_state_bar, use_container_width=True)

    st.markdown("---")

    # Budget utilization curve — cumulative cost vs device rank
    fig_curve = go.Figure()

    n_devices = len(selected_devices)
    device_ranks = list(range(1, n_devices + 1))

    fig_curve.add_trace(go.Scatter(
        x=device_ranks,
        y=selected_devices["cumulative_cost"],
        mode="lines",
        fill="tozeroy",
        name="Cumulative Cost",
        line=dict(color=BRAND["primary_blue"], width=2),
        fillcolor="rgba(0, 117, 190, 0.15)",
    ))

    fig_curve.add_trace(go.Scatter(
        x=device_ranks,
        y=selected_devices["cumulative_exposure"],
        mode="lines",
        name="Cumulative Exposure Eliminated",
        line=dict(color=RISK_COLORS["High"], width=2, dash="dash"),
    ))

    # Budget line
    fig_curve.add_hline(
        y=budget,
        line_dash="dot",
        line_color=BRAND["accent_orange"],
        annotation_text=f"Budget: ${budget:,.0f}",
        annotation_position="top right",
        annotation_font_color=BRAND["accent_orange"],
    )

    fig_curve.update_layout(
        title="Budget Utilization Curve",
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Devices Selected (Rank Order)", gridcolor="#1a3a5c"),
        yaxis=dict(tickprefix="$", tickformat=",.0f", title="Cumulative ($)", gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40),
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig_curve, use_container_width=True)

    # Selected devices table
    st.markdown(
        f"<h3 style='color:{BRAND['white']}'>Selected Devices</h3>",
        unsafe_allow_html=True,
    )
    display_selected = selected_devices[[
        "hostname", "device_type", "state", "model", "risk_tier",
        "risk_score", "total_cost", "risk_cost_exposure", "priority_ratio",
        "cumulative_cost",
    ]].copy()
    display_selected["total_cost"]         = display_selected["total_cost"].apply(lambda x: f"${x:,.0f}")
    display_selected["risk_cost_exposure"] = display_selected["risk_cost_exposure"].apply(lambda x: f"${x:,.0f}")
    display_selected["cumulative_cost"]    = display_selected["cumulative_cost"].apply(lambda x: f"${x:,.0f}")
    display_selected["priority_ratio"]     = display_selected["priority_ratio"].round(3)
    display_selected["risk_score"]         = display_selected["risk_score"].round(1)
    display_selected = display_selected.rename(columns={
        "hostname":            "Hostname",
        "device_type":         "Type",
        "state":               "State",
        "model":               "Model",
        "risk_tier":           "Risk Tier",
        "risk_score":          "Risk Score",
        "total_cost":          "Replacement Cost",
        "risk_cost_exposure":  "Risk Exposure",
        "priority_ratio":      "Priority Ratio",
        "cumulative_cost":     "Cumulative Spend",
    })
    st.dataframe(display_selected, use_container_width=True)

    csv_selected = selected_devices.drop(
        columns=["cumulative_cost", "cumulative_exposure", "priority_ratio"], errors="ignore"
    ).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Optimizer Selection CSV",
        data=csv_selected,
        file_name="gridguard_budget_optimizer.csv",
        mime="text/csv",
    )

else:
    st.warning("No Critical or High risk devices with valid cost data found under current filters.")

st.divider()


# ===========================================================================
# Feature C — Feature Importance / Explainability
# ===========================================================================
st.markdown(
    f"<h2 style='color:{BRAND['white']}'>C. Model Explainability</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "**Permutation importance** measures how much model accuracy drops when each feature "
    "is randomly shuffled — a more rigorous and unbiased measure than Gini/split importance. "
    "Error bars show variance across 10 permutation rounds."
)

if train_ok:
    imp_df = compute_permutation_importance(artifacts, n_repeats=10)

    # Horizontal bar with error bars
    fig_imp = go.Figure()
    fig_imp.add_trace(go.Bar(
        y=imp_df["feature"][::-1],
        x=imp_df["importance_mean"][::-1],
        orientation="h",
        error_x=dict(
            type="data",
            array=imp_df["importance_std"][::-1].tolist(),
            visible=True,
            color=BRAND["light_blue"],
        ),
        marker_color=BRAND["primary_blue"],
        name="Permutation Importance",
    ))
    fig_imp.update_layout(
        title="Feature Importance (Permutation, Holdout Set)",
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Mean Accuracy Drop When Shuffled", gridcolor="#1a3a5c"),
        yaxis=dict(gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40, l=120),
    )
    st.plotly_chart(fig_imp, use_container_width=True)
    st.markdown(insight_caption(
        "This shows which pieces of information the model relies on most when predicting whether a device is past its end-of-life. "
        "Longer bars mean stronger influence on the prediction. "
        "Features with bars near zero had almost no impact — removing them would not change the results."
    ), unsafe_allow_html=True)

    st.markdown("---")

    # Risk score distribution: labeled vs predicted-unknown
    labeled_df   = df[df["eos_date"].notna() | df["eol_date"].notna()].copy()
    labeled_df["data_group"] = "Labeled (Known Lifecycle)"

    if n_unknown > 0:
        preds_for_chart = predict_unknown_lifecycle(df, artifacts)
        preds_for_chart["data_group"] = "Predicted Unknown"
        compare_df = pd.concat(
            [labeled_df[["risk_score", "data_group"]],
             preds_for_chart[["risk_score", "data_group"]]],
            ignore_index=True,
        )
    else:
        compare_df = labeled_df[["risk_score", "data_group"]]

    fig_compare = px.histogram(
        compare_df,
        x="risk_score",
        color="data_group",
        nbins=30,
        barmode="overlay",
        opacity=0.65,
        title="Risk Score Distribution: Labeled vs Unlabeled",
        labels={"risk_score": "Risk Score (0–100)", "data_group": "Device Group"},
        color_discrete_map={
            "Labeled (Known Lifecycle)": BRAND["primary_blue"],
            "Predicted Unknown":         BRAND["accent_orange"],
        },
    )
    fig_compare.update_layout(
        title_font_color=BRAND["white"],
        font=dict(color=BRAND["white"], family="Arial"),
        plot_bgcolor=DARK_PLOT_BG,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#1a3a5c"),
        yaxis=dict(gridcolor="#1a3a5c"),
        margin=dict(t=60, b=40),
    )
    st.plotly_chart(fig_compare, use_container_width=True)
    st.markdown(insight_caption(
        "Devices with no lifecycle record (orange) pile up at low risk scores — not because they are safe, "
        "but because the standard scoring system has nothing to score them on. "
        "The machine learning model identifies which of those orange devices actually behave like high-risk devices, "
        "surfacing risk that would otherwise remain completely invisible."
    ), unsafe_allow_html=True)

    # Device Explainer
    with st.expander("Device Explainer — Compare Individual Device to Fleet Average"):
        all_hostnames = sorted(df["hostname"].dropna().unique().tolist())
        selected_hostname = st.selectbox(
            "Select a device to explain:",
            options=all_hostnames,
            key="explainer_device",
        )

        device_row = df[df["hostname"] == selected_hostname]
        if not device_row.empty:
            row = device_row.iloc[0]
            from utils.ml_models import _FEATURE_COLS  # noqa: PLC0415

            explainer_data = []
            for feat in _FEATURE_COLS:
                device_val = row.get(feat, None)
                fleet_val  = df[feat].mean() if pd.api.types.is_numeric_dtype(df[feat]) else df[feat].mode().iloc[0] if not df[feat].mode().empty else "—"

                explainer_data.append({
                    "Feature":       feat,
                    "Device Value":  str(device_val) if device_val is not None else "—",
                    "Fleet Average": f"{fleet_val:.2f}" if isinstance(fleet_val, float) else str(fleet_val),
                })

            explainer_df = pd.DataFrame(explainer_data)
            st.dataframe(explainer_df, use_container_width=True)

            # Show predictions for this device if it's unlabeled
            if pd.isna(row.get("eos_date")) and pd.isna(row.get("eol_date")):
                single_pred = predict_unknown_lifecycle(device_row, artifacts)
                if not single_pred.empty:
                    p = single_pred.iloc[0]["predicted_eol_probability"]
                    tier = single_pred.iloc[0]["predicted_lifecycle_tier"]
                    st.markdown(
                        f"**Prediction:** {tier} — P(Past EoL) = **{p*100:.1f}%**"
                    )
            else:
                st.markdown(
                    f"**Actual lifecycle status:** {row.get('lifecycle_stage', '—')} "
                    f"(Risk Score: {row.get('risk_score', '—')})"
                )
else:
    st.warning("Model not trained — cannot compute feature importance.")

st.divider()


# ===========================================================================
# Feature D — Anomaly Detection
# ===========================================================================
st.markdown(
    f"<h2 style='color:{BRAND['white']}'>D. Anomaly Detection</h2>",
    unsafe_allow_html=True,
)
st.info(
    "**Methodology:** IsolationForest (contamination=5%, n_estimators=100) on three features: "
    "uptime_days, total_cost, and risk_score. APs and WLCs from Prime sources have imputed "
    "uptime=0 due to missing data. The 5% contamination threshold flags approximately 750 devices. "
    "Low- and Medium-risk anomalies represent 'hidden risk' — devices with unusual feature "
    "combinations that conventional scoring misses."
)

with st.spinner("Running IsolationForest on full fleet…"):
    anomaly_df = _cached_anomalies(df)

n_anomalies = int(anomaly_df["is_anomaly"].sum())
low_med_anomalies = int(
    anomaly_df[anomaly_df["is_anomaly"] & anomaly_df["risk_tier"].isin(["Low", "Medium"])].shape[0]
)
avg_anomaly_score = float(anomaly_df[anomaly_df["is_anomaly"]]["anomaly_score"].mean()) if n_anomalies > 0 else 0.0

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        "Anomalies Detected",
        f"{n_anomalies:,}",
        delta=f"{n_anomalies/len(anomaly_df)*100:.1f}% of fleet",
        delta_color="off",
    )
with col2:
    st.metric(
        "Low/Medium Risk Anomalies",
        f"{low_med_anomalies:,}",
        delta="Hidden risk — not caught by rule-based scoring",
        delta_color="inverse",
    )
with col3:
    st.metric("Avg Anomaly Score (Flagged)", f"{avg_anomaly_score:.1f} / 100")

# Scatter: uptime_days vs risk_score, color by is_anomaly
scatter_df = anomaly_df.copy()
scatter_df["Status"] = scatter_df["is_anomaly"].map(
    {True: "Anomalous", False: "Normal"}
)
fig_scatter = px.scatter(
    scatter_df,
    x="uptime_days",
    y="risk_score",
    color="Status",
    color_discrete_map={"Anomalous": RISK_COLORS["Critical"], "Normal": BRAND["light_blue"]},
    opacity=0.6,
    title="Uptime vs Risk Score — Anomaly Overlay",
    labels={
        "uptime_days": "Uptime (Days)",
        "risk_score":  "Risk Score",
    },
    hover_data=["hostname", "device_type", "anomaly_score"],
)
fig_scatter.update_layout(
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    plot_bgcolor=DARK_PLOT_BG,
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#1a3a5c"),
    yaxis=dict(gridcolor="#1a3a5c"),
    margin=dict(t=60, b=40),
)
st.plotly_chart(fig_scatter, use_container_width=True)
st.markdown(insight_caption(
    "The most important dots to notice are the red ones sitting low on the chart — low risk score but flagged as anomalous. "
    "These are devices the standard scoring system rated as low risk, but whose combination of age, cost, and uptime "
    "is statistically unusual compared to the rest of the fleet. They warrant a manual review before the next refresh cycle."
), unsafe_allow_html=True)

st.markdown("---")

# Donut: anomalous devices by risk tier
anomalous_only = anomaly_df[anomaly_df["is_anomaly"]]
donut_data = (
    anomalous_only.groupby("risk_tier")
    .size()
    .reset_index(name="count")
)
# Ensure all tiers are represented
all_tiers = pd.DataFrame({"risk_tier": RISK_TIER_ORDER})
donut_data = all_tiers.merge(donut_data, on="risk_tier", how="left").fillna(0)
donut_data["count"] = donut_data["count"].astype(int)
donut_data = donut_data[donut_data["count"] > 0]

fig_donut = px.pie(
    donut_data,
    names="risk_tier",
    values="count",
    color="risk_tier",
    color_discrete_map=RISK_COLORS,
    title="Anomalous Devices by Risk Tier",
    hole=0.5,
)
fig_donut.update_traces(
    textposition="outside",
    textinfo="label+value+percent",
    textfont_color=BRAND["white"],
)
fig_donut.update_layout(
    title_font_color=BRAND["white"],
    font=dict(color=BRAND["white"], family="Arial"),
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=60, b=40),
    showlegend=False,
)
st.plotly_chart(fig_donut, use_container_width=True)
st.markdown(insight_caption(
    "The yellow and green slices show devices that scored as Medium or Low risk by the standard system — "
    "but the model flagged them as behaving unusually. These are the 'hidden risk' devices a simple rules-based checklist would miss entirely. "
    "They are the reason anomaly detection adds value on top of standard lifecycle scoring."
), unsafe_allow_html=True)

# Top 30 anomalous devices table
st.markdown(
    f"<h3 style='color:{BRAND['white']}'>Top 30 Anomalous Devices</h3>",
    unsafe_allow_html=True,
)
st.caption("Ranked by anomaly score (higher = more statistically unusual relative to fleet).")

top30_anomalies = (
    anomaly_df[anomaly_df["is_anomaly"]]
    .sort_values("anomaly_score", ascending=False)
    .head(30)
)[["hostname", "device_type", "state", "model", "risk_tier",
   "risk_score", "uptime_days", "total_cost", "anomaly_score"]]

if not top30_anomalies.empty:
    display_anomalies = top30_anomalies.copy()
    display_anomalies["total_cost"] = display_anomalies["total_cost"].apply(
        lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
    )
    display_anomalies["uptime_days"] = display_anomalies["uptime_days"].fillna(0).astype(int)
    display_anomalies["risk_score"]  = display_anomalies["risk_score"].round(1)
    display_anomalies = display_anomalies.rename(columns={
        "hostname":     "Hostname",
        "device_type":  "Type",
        "state":        "State",
        "model":        "Model",
        "risk_tier":    "Risk Tier",
        "risk_score":   "Risk Score",
        "uptime_days":  "Uptime (Days)",
        "total_cost":   "Replacement Cost",
        "anomaly_score":"Anomaly Score",
    })
    st.dataframe(display_anomalies, use_container_width=True)

    csv_anomalies = top30_anomalies.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Anomaly Report CSV",
        data=csv_anomalies,
        file_name="gridguard_anomalies.csv",
        mime="text/csv",
    )
else:
    st.info("No anomalies detected under current filters.")
