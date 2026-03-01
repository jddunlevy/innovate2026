"""
ml_models.py — Predictive ML layer for GridGuard Network Intelligence.
UA Innovate 2026 — Southern Company

Five ML capabilities:
  1. train_lifecycle_predictor  — GradientBoostingClassifier on labeled devices
  2. predict_unknown_lifecycle  — Inference on 9,004 devices with no lifecycle data
  3. compute_permutation_importance — Holdout-based feature importance (trustworthy)
  4. detect_anomalies            — IsolationForest on full fleet
  5. optimize_refresh_budget     — Greedy ROI-ranked budget allocator

Design notes:
  - Features are restricted to fields that exist on ALL devices (labeled + unlabeled).
    Lifecycle-derived columns (risk_score, days_to_eos, is_past_eos) are NOT used as
    features; they would leak the label and don't exist on unlabeled devices.
  - All sklearn objects are returned for caching by the calling page.
  - Functions are pure (no Streamlit calls) — safe to call from any context.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.inspection import permutation_importance
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)


# ---------------------------------------------------------------------------
# Feature set — safe to use on ALL devices (no lifecycle leakage)
# ---------------------------------------------------------------------------
_FEATURE_COLS = [
    "device_type",   # categorical — encoded
    "affiliate_code",# categorical — encoded
    "state",         # categorical — encoded
    "source",        # categorical — encoded
    "uptime_days",   # numeric — fillna(median)
    "total_cost",    # numeric
    "device_cost",   # numeric
    "labor_cost",    # numeric
]

# Columns that are categorical and need label encoding
_CAT_COLS = ["device_type", "affiliate_code", "state", "source"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _encode_features(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, LabelEncoder]]:
    """
    Label-encode categorical columns, fill numeric NaNs with column medians.
    Returns (feature_df, encoders_dict) — encoders are needed to transform unknowns.
    """
    X = df[_FEATURE_COLS].copy()

    encoders: dict[str, LabelEncoder] = {}
    for col in _CAT_COLS:
        le = LabelEncoder()
        # Fill missing with sentinel "UNKNOWN" before encoding
        X[col] = X[col].fillna("UNKNOWN").astype(str)
        le.fit(X[col])
        X[col] = le.transform(X[col])
        encoders[col] = le

    # Fill numeric NaNs with training-set medians
    for col in ["uptime_days", "total_cost", "device_cost", "labor_cost"]:
        median_val = X[col].median()
        X[col] = X[col].fillna(median_val)

    return X.astype(float), encoders


def _transform_with_encoders(
    df: pd.DataFrame,
    encoders: dict[str, LabelEncoder],
    uptime_median: float,
    cost_medians: dict[str, float],
) -> pd.DataFrame:
    """
    Apply saved encoders to new (unlabeled) data.
    Unseen categories are mapped to a special "UNKNOWN" class.
    """
    X = df[_FEATURE_COLS].copy()

    for col in _CAT_COLS:
        le = encoders[col]
        vals = X[col].fillna("UNKNOWN").astype(str)
        # Map unseen labels to "UNKNOWN" if the encoder has seen it, else 0
        known_classes = set(le.classes_)
        vals = vals.apply(lambda v: v if v in known_classes else "UNKNOWN")
        if "UNKNOWN" not in known_classes:
            # Fallback: use most frequent encoded value (0)
            X[col] = 0
        else:
            X[col] = le.transform(vals)

    for col in ["uptime_days", "total_cost", "device_cost", "labor_cost"]:
        fill = cost_medians.get(col, uptime_median)
        X[col] = X[col].fillna(fill)

    return X.astype(float)


# ---------------------------------------------------------------------------
# 1. Train Lifecycle Predictor
# ---------------------------------------------------------------------------

def train_lifecycle_predictor(df: pd.DataFrame) -> dict[str, Any]:
    """
    Train a GradientBoostingClassifier to predict whether a device is past End-of-Life.

    Training data: devices where eos_date OR eol_date is NOT null (has lifecycle data).
    Target (y): binary — is_past_eol (1 = Critical/past EoL, 0 = EoS-only or active).

    Parameters
    ----------
    df : pd.DataFrame
        Full cleaned device DataFrame from load_data().

    Returns
    -------
    dict with keys:
        model       — fitted GradientBoostingClassifier
        encoders    — dict of LabelEncoders (one per categorical feature)
        feature_names — list of feature column names
        accuracy    — holdout accuracy (float, 0–1)
        X_test      — holdout feature DataFrame
        y_test      — holdout labels Series
        medians     — dict of numeric column medians (for transform_with_encoders)
        n_train     — int, number of training rows
        n_test      — int, number of test rows
    """
    # --- Labeled set: devices with any lifecycle date ---
    labeled = df[df["eos_date"].notna() | df["eol_date"].notna()].copy()

    if len(labeled) < 50:
        raise ValueError(
            f"Insufficient labeled data for training ({len(labeled)} rows). "
            "Need at least 50 devices with lifecycle dates."
        )

    # Target: is_past_eol (bool → int)
    y = labeled["is_past_eol"].astype(int)

    # Encode features
    X, encoders = _encode_features(labeled)

    # Store medians from training data (needed to transform unknowns consistently)
    medians = {
        col: labeled[col].median()
        for col in ["uptime_days", "total_cost", "device_cost", "labor_cost"]
    }
    medians = {k: (v if pd.notna(v) else 0.0) for k, v in medians.items()}

    # 80/20 stratified split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42
    )

    # GradientBoostingClassifier — strong enough for ~6k rows, interpretable
    model = GradientBoostingClassifier(
        n_estimators=150,
        learning_rate=0.1,
        max_depth=4,
        subsample=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)

    accuracy = model.score(X_test, y_test)

    return {
        "model":         model,
        "encoders":      encoders,
        "feature_names": _FEATURE_COLS,
        "accuracy":      accuracy,
        "X_test":        X_test,
        "y_test":        y_test,
        "medians":       medians,
        "n_train":       len(X_train),
        "n_test":        len(X_test),
    }


# ---------------------------------------------------------------------------
# 2. Predict Unknown Lifecycle
# ---------------------------------------------------------------------------

def predict_unknown_lifecycle(
    df: pd.DataFrame,
    model_artifacts: dict[str, Any],
) -> pd.DataFrame:
    """
    Run the trained lifecycle predictor on devices with NO lifecycle data.

    Returns a DataFrame of the unlabeled rows augmented with:
        predicted_eol_probability  — P(is_past_eol == 1), float 0–1
        predicted_lifecycle_tier   — 'Likely Past EoL' | 'Likely Past EoS Only' | 'Likely Active'

    Parameters
    ----------
    df : pd.DataFrame
        Full device DataFrame.
    model_artifacts : dict
        Output of train_lifecycle_predictor().
    """
    # Unlabeled = no lifecycle data
    unknown = df[df["eos_date"].isna() & df["eol_date"].isna()].copy()

    if unknown.empty:
        return unknown

    model    = model_artifacts["model"]
    encoders = model_artifacts["encoders"]
    medians  = model_artifacts["medians"]

    X_unknown = _transform_with_encoders(
        unknown, encoders,
        uptime_median=medians.get("uptime_days", 0),
        cost_medians=medians,
    )

    probs = model.predict_proba(X_unknown)[:, 1]  # P(is_past_eol)

    unknown = unknown.copy()
    unknown["predicted_eol_probability"] = np.round(probs, 4)

    def _tier(p: float) -> str:
        if p >= 0.65:
            return "Likely Past EoL"
        elif p >= 0.40:
            return "Likely Past EoS Only"
        else:
            return "Likely Active"

    unknown["predicted_lifecycle_tier"] = unknown["predicted_eol_probability"].apply(_tier)

    return unknown.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. Permutation Importance
# ---------------------------------------------------------------------------

def compute_permutation_importance(
    model_artifacts: dict[str, Any],
    n_repeats: int = 10,
) -> pd.DataFrame:
    """
    Compute permutation-based feature importance on the holdout set.

    Permutation importance is more reliable than Gini/split importance because
    it measures the actual drop in accuracy when a feature's values are shuffled.

    Parameters
    ----------
    model_artifacts : dict
        Output of train_lifecycle_predictor().
    n_repeats : int
        Number of permutation rounds (10 gives stable estimates, ~1s runtime).

    Returns
    -------
    pd.DataFrame with columns: feature, importance_mean, importance_std
        Sorted by importance_mean descending.
    """
    model        = model_artifacts["model"]
    X_test       = model_artifacts["X_test"]
    y_test       = model_artifacts["y_test"]
    feature_names = model_artifacts["feature_names"]

    result = permutation_importance(
        model, X_test, y_test,
        n_repeats=n_repeats,
        random_state=42,
        scoring="accuracy",
    )

    imp_df = pd.DataFrame({
        "feature":          feature_names,
        "importance_mean":  np.round(result.importances_mean, 5),
        "importance_std":   np.round(result.importances_std,  5),
    }).sort_values("importance_mean", ascending=False).reset_index(drop=True)

    return imp_df


# ---------------------------------------------------------------------------
# 4. Anomaly Detection
# ---------------------------------------------------------------------------

def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag anomalous devices using IsolationForest on the full fleet.

    Features: uptime_days, total_cost, risk_score
    (All three are available on every device; uptime_days fillna(0) for APs/WLCs
    from Prime which lack uptime data.)

    IsolationForest contamination=0.05 means ~5% of the fleet is labeled anomalous.
    This deliberately includes LOW-risk devices that have unexpected feature combinations
    (e.g., suspiciously low cost + long uptime + no lifecycle data) — these are the
    "hidden risk" story for the presentation.

    Parameters
    ----------
    df : pd.DataFrame
        Full device DataFrame with risk_score, uptime_days, total_cost.

    Returns
    -------
    pd.DataFrame — same rows as input, with added columns:
        anomaly_score  — 0–100, higher = more anomalous
        is_anomaly     — bool
    """
    _ANOMALY_FEATURES = ["uptime_days", "total_cost", "risk_score"]

    work = df.copy()

    X = work[_ANOMALY_FEATURES].copy()
    X["uptime_days"] = X["uptime_days"].fillna(0)
    X["total_cost"]  = X["total_cost"].fillna(0)
    X["risk_score"]  = X["risk_score"].fillna(0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    iso = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42,
        n_jobs=-1,
    )
    iso.fit(X_scaled)

    # decision_function: more negative = more anomalous
    raw_scores = iso.decision_function(X_scaled)

    # Normalize to 0–100 (invert so high = more anomalous)
    # decision_function range is roughly [-0.5, 0.5]
    normalized = 1 - (raw_scores - raw_scores.min()) / (raw_scores.max() - raw_scores.min() + 1e-9)
    anomaly_score = np.round(normalized * 100, 1)

    predictions = iso.predict(X_scaled)  # -1 = anomaly, 1 = normal

    work["anomaly_score"] = anomaly_score
    work["is_anomaly"]    = predictions == -1

    return work


# ---------------------------------------------------------------------------
# 5. Budget Optimizer
# ---------------------------------------------------------------------------

def optimize_refresh_budget(
    df: pd.DataFrame,
    budget: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """
    Greedy ROI-ranked refresh budget allocator.

    Selects devices from the Critical/High risk tiers to maximize risk exposure
    eliminated per dollar spent.

    Priority ratio = risk_cost_exposure / total_cost
    Devices with the highest ratio (most risk eliminated per dollar) are selected first
    until the budget is exhausted.

    Parameters
    ----------
    df : pd.DataFrame
        Full device DataFrame with risk_tier, risk_cost_exposure, total_cost.
    budget : float
        Total available refresh budget in USD.

    Returns
    -------
    selected : pd.DataFrame
        Selected devices with cumulative_cost and cumulative_exposure_eliminated columns.
    summary : dict
        Keys: devices_selected, budget_used, exposure_eliminated, roi_ratio, budget_remaining
    """
    # Candidates: Critical or High risk with positive cost
    candidates = df[
        df["risk_tier"].isin(["Critical", "High"]) &
        (df["total_cost"] > 0)
    ].copy()

    if candidates.empty:
        empty = df.iloc[0:0].copy()
        return empty, {
            "devices_selected": 0,
            "budget_used": 0.0,
            "exposure_eliminated": 0.0,
            "roi_ratio": 0.0,
            "budget_remaining": budget,
        }

    # Priority ratio: exposure eliminated per $ spent
    candidates["priority_ratio"] = (
        candidates["risk_cost_exposure"] / candidates["total_cost"]
    ).replace([np.inf, -np.inf], 0).fillna(0)

    # Sort by priority ratio descending (best ROI first)
    candidates = candidates.sort_values("priority_ratio", ascending=False).reset_index(drop=True)

    # Greedy selection
    cumulative_cost = 0.0
    selected_rows = []
    for _, row in candidates.iterrows():
        device_cost = float(row["total_cost"])
        if cumulative_cost + device_cost <= budget:
            cumulative_cost += device_cost
            selected_rows.append(row)

    if not selected_rows:
        # Budget too small for even the cheapest device — take cheapest anyway
        cheapest = candidates.nsmallest(1, "total_cost")
        selected_rows = [cheapest.iloc[0]]
        cumulative_cost = float(cheapest.iloc[0]["total_cost"])

    selected = pd.DataFrame(selected_rows).reset_index(drop=True)

    # Add cumulative tracking columns
    selected["cumulative_cost"]     = selected["total_cost"].cumsum()
    selected["cumulative_exposure"]  = selected["risk_cost_exposure"].cumsum()

    exposure_eliminated = float(selected["risk_cost_exposure"].sum())
    roi_ratio = exposure_eliminated / cumulative_cost if cumulative_cost > 0 else 0.0

    summary = {
        "devices_selected":    len(selected),
        "budget_used":         round(cumulative_cost, 2),
        "exposure_eliminated": round(exposure_eliminated, 2),
        "roi_ratio":           round(roi_ratio, 3),
        "budget_remaining":    round(budget - cumulative_cost, 2),
    }

    return selected, summary
