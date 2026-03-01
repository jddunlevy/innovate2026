"""
geo_clustering.py — DBSCAN radius-based device clustering for batch refresh analysis.
GridGuard Network Intelligence — UA Innovate 2026

Key insight: grouping co-located devices into a single refresh project
eliminates redundant truck rolls, reducing operational cost.

Truck roll savings estimate: $1,500 per additional device in a cluster
(avoids a separate dispatch per device).
"""

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from utils.constants import TRUCK_ROLL_SAVINGS_PER_DEVICE

_KMS_PER_MILE  = 1.60934
_EARTH_RADIUS_KM = 6371.0


def cluster_devices_by_radius(df: pd.DataFrame, radius_miles: float = 5) -> pd.DataFrame:
    """
    Assign a cluster_id to every device using DBSCAN with haversine distance.

    Devices without lat/lon are assigned cluster_id = -2 (no location data).
    Noise points (isolated devices) are assigned cluster_id = -1.
    Clustered devices get cluster_id ≥ 0.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'latitude' and 'longitude' columns.
    radius_miles : float
        Maximum distance between two devices to be in the same cluster.

    Returns
    -------
    pd.DataFrame with 'cluster_id' column added/updated.
    """
    df = df.copy()
    df["cluster_id"] = -2  # default: no location

    geo_mask = df["latitude"].notna() & df["longitude"].notna()
    geo_df   = df[geo_mask].copy()

    if len(geo_df) < 2:
        return df

    coords  = np.radians(geo_df[["latitude", "longitude"]].values)
    epsilon = (radius_miles * _KMS_PER_MILE) / _EARTH_RADIUS_KM

    labels = DBSCAN(
        eps=epsilon,
        min_samples=2,
        algorithm="ball_tree",
        metric="haversine",
    ).fit_predict(coords)

    df.loc[geo_mask, "cluster_id"] = labels
    return df


def build_cluster_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Summarise clustered devices into one row per cluster.

    Returns a DataFrame with:
        cluster_id, device_count, avg_risk_score, critical_count,
        states, lat_center, lon_center, site_names,
        total_replacement_cost, estimated_savings
    """
    clustered = df[df["cluster_id"] >= 0].copy()

    if clustered.empty:
        return pd.DataFrame()

    summary = (
        clustered.groupby("cluster_id")
        .agg(
            device_count      = ("device_id",    "count"),
            avg_risk_score    = ("risk_score",   "mean"),
            critical_count    = ("risk_tier",    lambda x: (x == "Critical").sum()),
            high_count        = ("risk_tier",    lambda x: (x == "High").sum()),
            states            = ("state",        lambda x: ", ".join(sorted(x.dropna().unique()))),
            site_names        = ("site_name",    lambda x: "; ".join(sorted(x.dropna().unique())[:3])),
            lat_center        = ("latitude",     "mean"),
            lon_center        = ("longitude",    "mean"),
            total_cost        = ("total_cost",   "sum"),
        )
        .reset_index()
    )

    # Truck roll savings: if you batch N devices, you save (N-1) trips
    summary["estimated_savings"] = (
        (summary["device_count"] - 1) * TRUCK_ROLL_SAVINGS_PER_DEVICE
    )

    summary["avg_risk_score"] = summary["avg_risk_score"].round(1)
    return summary.sort_values("avg_risk_score", ascending=False).reset_index(drop=True)
