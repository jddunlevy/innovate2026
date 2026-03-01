"""
risk_scoring.py — Lifecycle risk feature engineering and composite risk scoring.
GridGuard Network Intelligence — UA Innovate 2026

Risk score model (0–100):
  - Past EoL (End of Life)           → 50 pts  [highest urgency]
  - Past EoS (End of Sale, not EoL)  → 20 pts
  - Approaching EoL (≤365 days)      → 15 pts
  - Approaching EoS (≤180 days)      →  8 pts
  - Device age from uptime (0–7 pts) →  7 pts  [normalized, max at 10yr]

Score is normalized to 0–100 based on observed max in dataset.
Risk tier: Critical (≥75) | High (≥50) | Medium (≥25) | Low (<25)
"""

import numpy as np
import pandas as pd


def engineer_risk_features(df: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    """
    Compute all lifecycle flags, lifecycle stage, and risk score.

    Parameters
    ----------
    df : pd.DataFrame
        Combined device DataFrame — must contain eos_date, eol_date, uptime_days.
    today : pd.Timestamp
        Reference date for day calculations (fixed for reproducibility).

    Returns
    -------
    pd.DataFrame with added columns:
        days_to_eos, days_to_eol,
        is_past_eos, is_past_eol,
        is_approaching_eos, is_approaching_eol,
        lifecycle_stage, risk_score, risk_tier
    """
    df = df.copy()

    # ------------------------------------------------------------------
    # Days until / since each milestone (negative = already past)
    # ------------------------------------------------------------------
    df["days_to_eos"] = (pd.to_datetime(df["eos_date"]) - today).dt.days
    df["days_to_eol"] = (pd.to_datetime(df["eol_date"]) - today).dt.days

    # ------------------------------------------------------------------
    # Boolean lifecycle flags
    # ------------------------------------------------------------------
    df["is_past_eos"] = df["days_to_eos"] < 0
    df["is_past_eol"] = df["days_to_eol"] < 0

    # Approaching — only for devices NOT yet past that milestone
    df["is_approaching_eol"] = (df["days_to_eol"] >= 0) & (df["days_to_eol"] <= 365)
    df["is_approaching_eos"] = (df["days_to_eos"] >= 0) & (df["days_to_eos"] <= 180)

    # ------------------------------------------------------------------
    # Lifecycle stage (categorical, for display)
    # ------------------------------------------------------------------
    df["lifecycle_stage"] = df.apply(_lifecycle_stage, axis=1)

    # ------------------------------------------------------------------
    # Uptime-based age score (0–7 pts, max at 3,650 days / ~10 years)
    # ------------------------------------------------------------------
    age_score = np.clip(df["uptime_days"].fillna(0) / 3650, 0, 1) * 7

    # ------------------------------------------------------------------
    # Composite raw score
    # ------------------------------------------------------------------
    df["_raw_risk"] = (
        df["is_past_eol"].astype(int)         * 50
        + df["is_past_eos"].astype(int)        * 20
        + df["is_approaching_eol"].astype(int) * 15
        + df["is_approaching_eos"].astype(int) *  8
        + age_score
    )

    # ------------------------------------------------------------------
    # Normalize to 0–100 (relative to dataset max)
    # ------------------------------------------------------------------
    raw_max = df["_raw_risk"].max()
    if raw_max > 0:
        df["risk_score"] = (df["_raw_risk"] / raw_max * 100).round(1)
    else:
        df["risk_score"] = 0.0

    df = df.drop(columns=["_raw_risk"])

    # ------------------------------------------------------------------
    # Risk tier
    # ------------------------------------------------------------------
    df["risk_tier"] = pd.cut(
        df["risk_score"],
        bins=[-0.01, 25, 50, 75, 100.01],
        labels=["Low", "Medium", "High", "Critical"],
    ).astype(str)

    return df


def _lifecycle_stage(row) -> str:
    """Assign a human-readable lifecycle stage to a single device row."""
    has_eol = pd.notna(row.get("eol_date"))
    has_eos = pd.notna(row.get("eos_date"))

    if not has_eol and not has_eos:
        return "Unknown - No Lifecycle Data"
    if row.get("is_past_eol"):
        return "Critical - Past EoL"
    if row.get("is_past_eos"):
        return "High Risk - Past EoS"
    if row.get("is_approaching_eol"):
        return "Approaching EoL (<1yr)"
    if row.get("is_approaching_eos"):
        return "Approaching EoS (<6mo)"
    return "Active - Supported"
