"""
constants.py — Southern Company brand colors, mappings, and shared configuration.
GridGuard Network Intelligence — UA Innovate 2026
"""

# ---------------------------------------------------------------------------
# Southern Company Brand Colors
# ---------------------------------------------------------------------------
BRAND = {
    "primary_blue":  "#0075BE",
    "dark_blue":     "#003865",
    "accent_orange": "#E87722",
    "light_blue":    "#6CACE4",
    "white":         "#FFFFFF",
    "light_gray":    "#F5F5F5",
    "dark_gray":     "#333333",
}

# Risk tier → color mapping (consistent across all charts/tables)
RISK_COLORS = {
    "Critical": "#D32F2F",
    "High":     "#E87722",
    "Medium":   "#FFC107",
    "Low":      "#4CAF50",
    "Unknown":  "#9E9E9E",
}

# Lifecycle stage → display order (for sorting/charts)
LIFECYCLE_STAGE_ORDER = [
    "Critical - Past EoL",
    "High Risk - Past EoS",
    "Approaching EoL (<1yr)",
    "Approaching EoS (<6mo)",
    "Active - Supported",
    "Unknown - No Lifecycle Data",
]

RISK_TIER_ORDER = ["Critical", "High", "Medium", "Low"]

# ---------------------------------------------------------------------------
# Device Type Normalization
# ---------------------------------------------------------------------------
# Maps raw device type strings (from each source) → clean canonical name
DEVICE_TYPE_MAP = {
    # NA tab values
    "l3switch":             "L3 Switch",
    "switch":               "Switch",
    "router":               "Router",
    "application switch":   "Switch",
    "wireless controller":  "Wireless Controller",  # will be excluded from NA
    "voice gateway":        "Voice Gateway",
    "firewall":             "Firewall",
    "unknown":              "Unknown",
    # CatCtr family values
    "unified ap":           "Access Point",
    "wireless controller":  "Wireless Controller",
    "routers":              "Router",
    "switches and hubs":    "Switch",
    "managed":              "Switch",
    # Prime sources
    "access point":         "Access Point",
    "wlc":                  "Wireless Controller",
}

# Device types that belong to CatCtr/Prime (not NA)
WIRELESS_TYPES_LOWER = {"wireless controller", "access point", "unified ap", "wlc"}

# ---------------------------------------------------------------------------
# Affiliate Code → Company Name
# ---------------------------------------------------------------------------
AFFILIATE_MAP = {
    "GA": "Georgia Power",
    "AL": "Alabama Power",
    "MS": "Mississippi Power",
    "GN": "Gulf Power / Southern Natural Gas",
    "FL": "Florida Operations",
    "SN": "Southern Nuclear",
    "SO": "Southern Company Services",
    "AT": "ATC (Tower Company)",
    "TH": "The Southern Company",
    "SC": "Southern Company",
}

# ---------------------------------------------------------------------------
# Fallback Cost Estimates (used only when ModelData has no match)
# ---------------------------------------------------------------------------
FALLBACK_DEVICE_COST = {
    "Switch":               3_500,
    "L3 Switch":            5_000,
    "Router":               5_000,
    "Voice Gateway":        2_500,
    "Access Point":           800,
    "Wireless Controller": 15_000,
    "Firewall":             8_000,
    "Unknown":              4_000,
}

FALLBACK_LABOR_COST = {
    "Switch":               1_200,
    "L3 Switch":            1_500,
    "Router":               1_800,
    "Voice Gateway":          900,
    "Access Point":           400,
    "Wireless Controller":  3_000,
    "Firewall":             2_500,
    "Unknown":              1_500,
}

# Estimated truck-roll cost savings per co-located device batched together
TRUCK_ROLL_SAVINGS_PER_DEVICE = 1_500

# ---------------------------------------------------------------------------
# Data source labels
# ---------------------------------------------------------------------------
SOURCE_LABELS = {
    "NA":       "Network Analytics",
    "CatCtr":   "Catalyst Center",
    "PrimeAP":  "Cisco Prime (AP)",
    "PrimeWLC": "Cisco Prime (WLC)",
}

# Default data file path (fallback when no upload)
DEFAULT_DATA_PATH = "UAInnovateDataset-SoCo.xlsx"

# ---------------------------------------------------------------------------
# Dark Mode Premium — Chart & Caption Helpers
# ---------------------------------------------------------------------------
# Use as plot_bgcolor in all Plotly charts
DARK_PLOT_BG = "#0D1B2E"


def insight_caption(text: str) -> str:
    """Return styled HTML for a chart insight caption (replaces 📌 st.caption calls)."""
    return (
        "<p style='font-size:0.82rem;color:#6CACE4;margin-top:-10px;"
        "padding-bottom:4px;line-height:1.5'>"
        "<span style='color:#E87722;font-weight:600;letter-spacing:0.04em'>"
        "Insight</span>"
        f"<span style='color:#6CACE4'> — </span>{text}</p>"
    )
