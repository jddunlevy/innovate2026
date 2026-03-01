"""
data_loader.py — Full ingestion and cleaning pipeline for UAInnovateDataset-SoCo.xlsx.
GridGuard Network Intelligence — UA Innovate 2026

Pipeline steps (in order):
  1. Load all Excel tabs
  2. Filter each source to active/reachable devices only
  3. Exclude Wireless Controllers from NA (CatCtr/Prime are authoritative)
  4. Normalize column names to a standard schema
  5. Combine all sources into one DataFrame
  6. Parse hostnames → affiliate code + site code
  7. Exclude decommissioned sites
  8. Join SOLID / SOLID-Loc → addresses + lat/lon
  9. Join ModelData → EoS, EoL, and real cost data
 10. Classify / normalize device types
 11. Compute derived columns (device age, uptime days)
 12. Engineer lifecycle risk features (see risk_scoring.py)
 13. Return (df, quality_report)
"""

from __future__ import annotations

import io
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from utils.constants import (
    DEVICE_TYPE_MAP,
    FALLBACK_DEVICE_COST,
    FALLBACK_LABOR_COST,
    WIRELESS_TYPES_LOWER,
)
from utils.risk_scoring import engineer_risk_features

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

TODAY = pd.Timestamp("2026-02-28")  # Competition date — fixed for reproducibility


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading and processing dataset…")
def load_data(file_bytes: bytes) -> tuple[pd.DataFrame, dict]:
    """
    Load, clean, and enrich the UAInnovate dataset.

    Parameters
    ----------
    file_bytes : bytes
        Raw bytes of the uploaded .xlsx file.

    Returns
    -------
    df : pd.DataFrame
        Clean, combined, enriched device DataFrame ready for the app.
    quality_report : dict
        Counts and notes documenting every transformation for audit trail.
    """
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    qr: dict = {}  # quality report accumulator

    # ------------------------------------------------------------------
    # 1. Load raw tabs
    # ------------------------------------------------------------------
    na_raw     = xl.parse("NA")
    prime_ap   = xl.parse("PrimeAP")
    prime_wlc  = xl.parse("PrimeWLC")
    catctr_raw = xl.parse("CatCtr")
    solid      = xl.parse("SOLID")
    solid_loc  = xl.parse("SOLID-Loc")
    decom      = xl.parse("Decom")
    model_data = xl.parse("ModelData")

    qr["na_raw_rows"]      = len(na_raw)
    qr["catctr_raw_rows"]  = len(catctr_raw)
    qr["prime_ap_rows"]    = len(prime_ap)
    qr["prime_wlc_rows"]   = len(prime_wlc)

    # ------------------------------------------------------------------
    # 2. Process NA tab — switches, routers, voice gateways
    # ------------------------------------------------------------------
    na = _process_na(na_raw, qr)

    # ------------------------------------------------------------------
    # 3. Process CatCtr tab — APs and WLCs only
    # ------------------------------------------------------------------
    catctr = _process_catctr(catctr_raw, qr)

    # ------------------------------------------------------------------
    # 4. Process Prime tabs — APs and WLCs
    # ------------------------------------------------------------------
    pa  = _process_prime_ap(prime_ap, qr)
    pwlc = _process_prime_wlc(prime_wlc, qr)

    # ------------------------------------------------------------------
    # 5. Combine all sources + deduplicate by hostname
    #    Source priority: CatCtr > PrimeAP > PrimeWLC > NA
    #    (CatCtr is authoritative for APs/WLCs; PrimeAP overrides PrimeWLC;
    #     NA may have stale records for same device)
    # ------------------------------------------------------------------
    combined = pd.concat([na, catctr, pa, pwlc], ignore_index=True)
    qr["combined_pre_dedup"] = len(combined)

    _SRC_PRIORITY = {"CatCtr": 0, "PrimeAP": 1, "PrimeWLC": 2, "NA": 3}
    combined["_src_pri"] = combined["source"].map(_SRC_PRIORITY).fillna(9)
    combined = (
        combined
        .sort_values(["hostname", "_src_pri"])
        .drop_duplicates(subset=["hostname"], keep="first")
        .drop(columns=["_src_pri"])
        .reset_index(drop=True)
    )
    qr["deduped_by_hostname"] = qr["combined_pre_dedup"] - len(combined)
    qr["combined_pre_decom"] = len(combined)

    # ------------------------------------------------------------------
    # 6. Parse hostnames → affiliate_code + site_code
    # ------------------------------------------------------------------
    combined = _parse_hostnames(combined)

    # ------------------------------------------------------------------
    # 7. Exclude decommissioned sites
    # ------------------------------------------------------------------
    decom_codes = set(decom["Site Cd"].str.strip().str.upper())
    mask_decom  = combined["site_code"].str.upper().isin(decom_codes)
    qr["decom_excluded"] = int(mask_decom.sum())
    combined = combined[~mask_decom].copy()

    # ------------------------------------------------------------------
    # 8. Join SOLID + SOLID-Loc → addresses and lat/lon
    # ------------------------------------------------------------------
    combined = _join_site_data(combined, solid, solid_loc, qr)

    # ------------------------------------------------------------------
    # 9. Join ModelData → EoS, EoL, real costs
    # ------------------------------------------------------------------
    combined = _join_model_data(combined, model_data, qr)

    # ------------------------------------------------------------------
    # 10. Fill cost gaps with fallback estimates
    # ------------------------------------------------------------------
    combined = _fill_cost_gaps(combined)

    # ------------------------------------------------------------------
    # 11. Engineer risk features (lifecycle flags + risk score)
    # ------------------------------------------------------------------
    combined = engineer_risk_features(combined, TODAY)

    # ------------------------------------------------------------------
    # 12. Compute risk cost exposure
    # ------------------------------------------------------------------
    combined["risk_cost_exposure"] = (
        combined["total_cost"] * (combined["risk_score"] / 100)
    ).round(2)

    # ------------------------------------------------------------------
    # 13. Final dedup check — warn if duplicate device IDs
    # ------------------------------------------------------------------
    dup_count = combined.duplicated(subset=["device_id"]).sum()
    qr["duplicate_device_ids"] = int(dup_count)

    qr["final_device_count"] = len(combined)

    return combined, qr


# ---------------------------------------------------------------------------
# Per-source processors
# ---------------------------------------------------------------------------

def _process_na(df: pd.DataFrame, qr: dict) -> pd.DataFrame:
    """
    Clean the NA (Network Analytics) tab.
    Keep: Active devices only.
    Exclude: Wireless Controllers (CatCtr is authoritative for those).
    Normalize columns to standard schema.
    """
    # Active devices only
    active_mask = df["Device Status"].str.strip().str.lower() == "active"
    qr["na_inactive_excluded"] = int((~active_mask).sum())
    df = df[active_mask].copy()

    # Exclude wireless controllers — CatCtr owns those
    wc_mask = df["Device Type"].str.strip().str.lower() == "wireless controller"
    qr["na_wireless_ctrl_excluded"] = int(wc_mask.sum())
    df = df[~wc_mask].copy()

    qr["na_active_kept"] = len(df)

    # Normalize columns → standard schema
    df = df.rename(columns={
        "Host Name":     "hostname",
        "Device IP":     "ip_address",
        "Device Type":   "raw_device_type",
        "Device Status": "status_raw",
        "Device Model":  "model",
        "Serial Number": "serial_number",
        "Software Version": "software_version",
        "Uptime":        "uptime_raw",
    })

    df["source"]        = "NA"
    df["support_level"] = None  # not available in NA
    df["device_id"]     = "NA-" + df["hostname"].astype(str)

    # Parse uptime → days
    df["uptime_days"] = df["uptime_raw"].apply(_parse_uptime_days)

    return df[_STANDARD_COLS].copy()


def _process_catctr(df: pd.DataFrame, qr: dict) -> pd.DataFrame:
    """
    Clean the CatCtr (Catalyst Center) tab.
    Keep: APs and WLCs only (Unified AP + Wireless Controller families).
    Keep: Reachable devices only.
    """
    # Filter to AP and WLC families
    ap_wlc_families = {"unified ap", "wireless controller"}
    family_mask = df["family"].str.strip().str.lower().isin(ap_wlc_families)
    qr["catctr_non_ap_wlc_excluded"] = int((~family_mask).sum())
    df = df[family_mask].copy()

    # Reachable devices only
    reachable_vals = {"reachable", "ping reachable"}
    reach_mask = df["reachabilityStatus"].str.strip().str.lower().isin(reachable_vals)
    qr["catctr_unreachable_excluded"] = int((~reach_mask).sum())
    df = df[reach_mask].copy()

    qr["catctr_ap_wlc_kept"] = len(df)

    # Map raw device type from family column
    df["raw_device_type"] = df["family"].str.strip()

    # Normalize columns
    df = df.rename(columns={
        "hostname":           "hostname",
        "id":                 "_catctr_id",
        "platformId":         "model",
        "serialNumber":       "serial_number",
        "reachabilityStatus": "status_raw",
        "softwareVersion":    "software_version",
        "upTime":             "uptime_raw",
        "deviceSupportLevel": "support_level",
    })

    # CatCtr model can be a list string — take first item
    df["model"] = df["model"].apply(_clean_catctr_model)

    df["source"]      = "CatCtr"
    df["ip_address"]  = None
    df["device_id"]   = "CC-" + df["hostname"].astype(str)
    df["uptime_days"] = df["uptime_raw"].apply(_parse_uptime_days)

    return df[_STANDARD_COLS].copy()


def _process_prime_ap(df: pd.DataFrame, qr: dict) -> pd.DataFrame:
    """
    Clean the PrimeAP tab. Include all records (alarm status ≠ device status).
    """
    qr["prime_ap_kept"] = len(df)

    df = df.rename(columns={
        "name":          "hostname",
        "model":         "model",
        "serialNumber":  "serial_number",
        "ipAddress":     "ip_address",
        "softwareVersion": "software_version",
        "status":        "status_raw",
    })

    df["source"]        = "PrimeAP"
    df["raw_device_type"] = "Unified AP"
    df["support_level"] = None
    df["uptime_days"]   = None
    df["device_id"]     = "PA-" + df["hostname"].astype(str)

    return df[_STANDARD_COLS].copy()


def _process_prime_wlc(df: pd.DataFrame, qr: dict) -> pd.DataFrame:
    """
    Clean the PrimeWLC tab. Keep REACHABLE devices only.
    """
    reach_mask = df["reachability"].str.strip().str.upper() == "REACHABLE"
    qr["prime_wlc_unreachable_excluded"] = int((~reach_mask).sum())
    df = df[reach_mask].copy()
    qr["prime_wlc_kept"] = len(df)

    df = df.rename(columns={
        "deviceName":                    "hostname",
        "manufacturer_part_partNumber":  "model",
        "manufacturer_part_serialNumber": "serial_number",
        "ipAddress":                     "ip_address",
        "softwareVersion":               "software_version",
        "reachability":                  "status_raw",
    })

    df["source"]          = "PrimeWLC"
    df["raw_device_type"] = "Wireless Controller"
    df["support_level"]   = None
    df["uptime_days"]     = None
    df["device_id"]       = "WL-" + df["hostname"].astype(str)

    return df[_STANDARD_COLS].copy()


# ---------------------------------------------------------------------------
# Hostname parsing
# ---------------------------------------------------------------------------

def _parse_hostnames(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract affiliate_code (chars 0-1) and site_code (chars 2-4) from hostname.
    Example: 'GALSBSWSDWANLAB01' → affiliate='GA', site_code='LSB'
    """
    def _parse(hostname: str) -> dict:
        h = str(hostname).upper().strip()
        if len(h) >= 5:
            return {"affiliate_code": h[:2], "site_code": h[2:5]}
        elif len(h) >= 2:
            return {"affiliate_code": h[:2], "site_code": None}
        return {"affiliate_code": None, "site_code": None}

    parsed = df["hostname"].apply(_parse).apply(pd.Series)
    df["affiliate_code"] = parsed["affiliate_code"]
    df["site_code"]      = parsed["site_code"]
    return df


# ---------------------------------------------------------------------------
# Site join (SOLID + SOLID-Loc)
# ---------------------------------------------------------------------------

def _join_site_data(
    df: pd.DataFrame,
    solid: pd.DataFrame,
    solid_loc: pd.DataFrame,
    qr: dict,
) -> pd.DataFrame:
    """
    Join SOLID and SOLID-Loc on Site Code to obtain:
      - Site Name, Street Address, City, State, Zip (from SOLID)
      - Latitude, Longitude, County, Call Group, Owner (from SOLID-Loc)
    Join key: device.site_code == SOLID.Site Code
    """
    # Normalize site codes for join
    solid["_site_key"]     = solid["Site Code"].str.strip().str.upper()
    solid_loc["_site_key"] = solid_loc["Site Code"].str.strip().str.upper()
    df["_site_key"]        = df["site_code"].str.strip().str.upper()

    # Build address lookup from SOLID
    solid_lookup = solid[["_site_key", "Site Name", "Street Address 1",
                           "City", "State", "Zip"]].drop_duplicates("_site_key")
    solid_lookup = solid_lookup.rename(columns={
        "Site Name":       "site_name",
        "Street Address 1": "street_address",
        "City":            "city",
        "State":           "state",
        "Zip":             "zip",
    })

    # Build geo lookup from SOLID-Loc
    geo_lookup = solid_loc[["_site_key", "Latitude", "Longitude",
                             "PhysicalAddressCounty", "Call Group", "Owner"]].drop_duplicates("_site_key")
    geo_lookup = geo_lookup.rename(columns={
        "Latitude":              "latitude",
        "Longitude":             "longitude",
        "PhysicalAddressCounty": "county",
        "Call Group":            "call_group",
        "Owner":                 "owner",
    })

    df = df.merge(solid_lookup, on="_site_key", how="left")
    df = df.merge(geo_lookup,   on="_site_key", how="left")

    qr["site_join_matched"]  = int(df["site_name"].notna().sum())
    qr["site_join_no_match"] = int(df["site_name"].isna().sum())
    qr["lat_lon_available"]  = int(df["latitude"].notna().sum())

    df = df.drop(columns=["_site_key"])
    return df


# ---------------------------------------------------------------------------
# ModelData join (EoS, EoL, costs)
# ---------------------------------------------------------------------------

def _join_model_data(
    df: pd.DataFrame,
    model_data: pd.DataFrame,
    qr: dict,
) -> pd.DataFrame:
    """
    Join ModelData on model number to obtain:
      - EoS date (End of Sale)
      - EoL date (End of Life)
      - Device Cost, Labor Cost, Material Cost, Tax & OH
      - Replacement model, Category

    Strategy:
      1. Exact match on normalized model string.
      2. Fallback: strip trailing variant suffix (e.g. '-K9', '/K9').
      3. Devices with no match get NaN for all lifecycle fields.
    """
    md = model_data[["Model", "EoS", "EoL", "Category",
                      "Repl Device", "Device Cost", "Labor Cost",
                      "Material Cost", "Tax&OH"]].copy()
    md.columns = ["model_key", "eos_date", "eol_date", "model_category",
                  "replacement_model", "device_cost", "labor_cost",
                  "material_cost", "tax_oh"]
    md["model_key_norm"] = md["model_key"].str.strip().str.upper()

    df["_model_norm"] = df["model"].astype(str).str.strip().str.upper()

    # --- Pass 1: exact match ---
    df = df.merge(
        md.rename(columns={"model_key_norm": "_model_norm"}),
        on="_model_norm",
        how="left",
    )

    matched_exact = df["eos_date"].notna() | df["eol_date"].notna()
    unmatched_mask = ~matched_exact

    # --- Pass 2: suffix-stripped fallback for unmatched rows ---
    def _strip_suffix(model: str) -> str:
        """Remove common trailing variant suffixes for fuzzy matching."""
        m = re.sub(r"[/\-](K9|K9M|K8|B|E|I|T|L|S|D)$", "", model, flags=re.I)
        return m.strip()

    if unmatched_mask.any():
        df["_model_strip"] = df["_model_norm"].apply(_strip_suffix)
        md["_model_strip"]  = md["model_key_norm"].apply(_strip_suffix)

        # Drop duplicate stripped keys (keep first)
        md_strip = md.drop_duplicates("_model_strip")

        # Merge only unmatched rows
        unmatched = df[unmatched_mask].drop(
            columns=["model_key", "eos_date", "eol_date", "model_category",
                     "replacement_model", "device_cost", "labor_cost",
                     "material_cost", "tax_oh"],
            errors="ignore",
        )
        unmatched = unmatched.merge(
            md_strip[["_model_strip", "model_key", "eos_date", "eol_date",
                       "model_category", "replacement_model", "device_cost",
                       "labor_cost", "material_cost", "tax_oh"]],
            on="_model_strip",
            how="left",
        )
        df = pd.concat([df[matched_exact], unmatched], ignore_index=True)

    df = df.drop(columns=["_model_norm", "_model_strip", "model_key"],
                 errors="ignore")

    qr["model_join_matched"]  = int((df["eos_date"].notna() | df["eol_date"].notna()).sum())
    qr["model_join_no_match"] = int((df["eos_date"].isna()  & df["eol_date"].isna()).sum())

    # Ensure datetime types
    df["eos_date"] = pd.to_datetime(df["eos_date"], errors="coerce")
    df["eol_date"] = pd.to_datetime(df["eol_date"], errors="coerce")

    return df


# ---------------------------------------------------------------------------
# Cost gap filling
# ---------------------------------------------------------------------------

def _fill_cost_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """
    For devices where ModelData had no cost data, use fallback estimates
    based on device type. Document how many estimates were applied.
    """
    # Normalize device type for cost lookup
    df["device_type"] = df["raw_device_type"].apply(_normalize_device_type)

    no_device_cost = df["device_cost"].isna()
    df.loc[no_device_cost, "device_cost"] = (
        df.loc[no_device_cost, "device_type"].map(FALLBACK_DEVICE_COST)
    )

    no_labor_cost = df["labor_cost"].isna()
    df.loc[no_labor_cost, "labor_cost"] = (
        df.loc[no_labor_cost, "device_type"].map(FALLBACK_LABOR_COST)
    )

    df["material_cost"] = df["material_cost"].fillna(0)
    df["tax_oh"]        = df["tax_oh"].fillna(0)

    df["total_cost"] = (
        df["device_cost"].fillna(0)
        + df["labor_cost"].fillna(0)
        + df["material_cost"].fillna(0)
        + df["tax_oh"].fillna(0)
    )

    return df


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _normalize_device_type(raw: str) -> str:
    """Map raw device type string to canonical device type name."""
    if pd.isna(raw) or str(raw).strip() == "":
        return "Unknown"
    key = str(raw).strip().lower()
    return DEVICE_TYPE_MAP.get(key, str(raw).strip())


def _clean_catctr_model(val) -> str:
    """CatCtr platformId can be a list-like string; take first element."""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    # Remove list brackets if present: "['C9300-48P']" → "C9300-48P"
    s = re.sub(r"^\[['\"](.*?)['\"]\]$", r"\1", s)
    return s.split(",")[0].strip().strip("'\"")


def _parse_uptime_days(uptime_str) -> float | None:
    """
    Parse uptime strings like '1089d:17h:47m:0s' or '2 days, 3:04:05' to days.
    Returns None if unparseable.
    """
    if pd.isna(uptime_str) or str(uptime_str).strip() in ("", " "):
        return None
    s = str(uptime_str)
    # Pattern: Xd:Yh:Zm:Ws
    m = re.match(r"(\d+)d", s)
    if m:
        return float(m.group(1))
    # Pattern: X days
    m = re.match(r"(\d+)\s*day", s)
    if m:
        return float(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Standard column set — every source must produce exactly these
# ---------------------------------------------------------------------------

_STANDARD_COLS = [
    "device_id",
    "hostname",
    "source",
    "raw_device_type",
    "model",
    "serial_number",
    "ip_address",
    "software_version",
    "status_raw",
    "support_level",
    "uptime_days",
]


# ---------------------------------------------------------------------------
# Convenience: load from local file path (for development / testing)
# ---------------------------------------------------------------------------

def load_from_path(path: str | Path) -> tuple[pd.DataFrame, dict]:
    """Load dataset from a local file path (wraps load_data)."""
    with open(path, "rb") as f:
        return load_data(f.read())
