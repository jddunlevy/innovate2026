"""
exceptions.py — Exception register for devices excluded from active refresh planning.
GridGuard Network Intelligence — UA Innovate 2026

Devices that are technically past EoL but have a documented business reason
to remain in production are tracked here. The register persists as a CSV
and is applied before any risk analysis.
"""

import pandas as pd
from pathlib import Path

_EXCEPTION_PATH = Path(__file__).parent.parent / "data" / "exceptions_register.csv"

_EXCEPTION_COLS = [
    "device_id",
    "hostname",
    "exception_reason",
    "exception_date",
    "exception_owner",
    "review_date",
]


def load_exceptions() -> pd.DataFrame:
    """Load existing exception register, or return empty DataFrame if none exists."""
    if _EXCEPTION_PATH.exists():
        return pd.read_csv(_EXCEPTION_PATH)
    return pd.DataFrame(columns=_EXCEPTION_COLS)


def save_exception(device_id: str, hostname: str, reason: str, owner: str) -> None:
    """Append a new exception entry and persist to CSV."""
    _EXCEPTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    exceptions = load_exceptions()
    today = pd.Timestamp.today()
    new_row = {
        "device_id":        device_id,
        "hostname":         hostname,
        "exception_reason": reason,
        "exception_date":   today.strftime("%Y-%m-%d"),
        "exception_owner":  owner,
        "review_date":      (today + pd.DateOffset(months=6)).strftime("%Y-%m-%d"),
    }
    exceptions = pd.concat(
        [exceptions, pd.DataFrame([new_row])], ignore_index=True
    )
    exceptions.to_csv(_EXCEPTION_PATH, index=False)


def remove_exception(device_id: str) -> None:
    """Remove an exception entry by device_id."""
    exceptions = load_exceptions()
    exceptions = exceptions[exceptions["device_id"] != device_id]
    exceptions.to_csv(_EXCEPTION_PATH, index=False)


def apply_exceptions(df: pd.DataFrame, show_exceptions: bool = False) -> pd.DataFrame:
    """
    Filter the device DataFrame based on the exception register.

    Parameters
    ----------
    df : pd.DataFrame
    show_exceptions : bool
        If True, include excepted devices in the view (tagged with a flag column).
        If False, exclude them entirely.
    """
    exceptions = load_exceptions()
    if exceptions.empty:
        df["is_exception"] = False
        return df

    excepted_ids = set(exceptions["device_id"].astype(str))
    df["is_exception"] = df["device_id"].astype(str).isin(excepted_ids)

    if not show_exceptions:
        df = df[~df["is_exception"]].copy()

    return df
