"""
live_nav_fetch.py
------------------
Bluestock Fintech | Mutual Fund Analytics Capstone | Day 1

Fetches live historical NAV data from the mfapi.in public REST API
(no auth required) for HDFC Top 100 Direct plus 5 key benchmark
schemes, and saves each as a raw CSV under data/raw/live/.

API reference: GET https://api.mfapi.in/mf/{amfi_code}
Response JSON shape:
    {
        "meta": {"fund_house": ..., "scheme_type": ..., "scheme_name": ...},
        "data": [{"date": "DD-MM-YYYY", "nav": "123.4567"}, ...]
    }

Usage:
    python scripts/live_nav_fetch.py

Author: Bluestock MF Capstone
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "live"

API_BASE_URL = "https://api.mfapi.in/mf"
REQUEST_TIMEOUT_SECONDS = 15
SLEEP_BETWEEN_CALLS_SECONDS = 1.5  # polite rate limiting — public, free API

# amfi_code -> friendly label, used only for filenames/logging
SCHEMES: dict[int, str] = {
    125497: "hdfc_top_100_direct",
    119551: "sbi_bluechip",
    120503: "icici_bluechip",
    118632: "nippon_large_cap",
    119092: "axis_bluechip",
    120841: "kotak_bluechip",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("live_nav_fetch")


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def fetch_scheme_nav(amfi_code: int) -> dict | None:
    """
    Call the mfapi.in API for a single scheme and return the parsed JSON.

    Parameters
    ----------
    amfi_code : int
        The AMFI scheme code, e.g. 125497 for HDFC Top 100 Direct.

    Returns
    -------
    dict | None
        Parsed JSON response, or None if the request failed.
    """
    url = f"{API_BASE_URL}/{amfi_code}"

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error(f"amfi_code {amfi_code}: request timed out after {REQUEST_TIMEOUT_SECONDS}s")
        return None
    except requests.exceptions.HTTPError as exc:
        logger.error(f"amfi_code {amfi_code}: HTTP error — {exc}")
        return None
    except requests.exceptions.RequestException as exc:
        logger.error(f"amfi_code {amfi_code}: request failed — {exc}")
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.error(f"amfi_code {amfi_code}: response was not valid JSON")
        return None

    if "data" not in payload or not payload["data"]:
        logger.warning(f"amfi_code {amfi_code}: API returned no NAV data")
        return None

    return payload


def payload_to_dataframe(amfi_code: int, payload: dict) -> pd.DataFrame:
    """
    Convert a mfapi.in JSON payload into a clean DataFrame.

    mfapi.in returns dates as 'DD-MM-YYYY' strings and NAV as strings —
    both must be explicitly parsed/converted rather than left for
    pandas to guess, since silent misparsing of DD-MM vs MM-DD is a
    classic ETL bug.

    Parameters
    ----------
    amfi_code : int
        The AMFI scheme code, attached as a column for downstream joins.
    payload : dict
        Parsed JSON response from fetch_scheme_nav().

    Returns
    -------
    pd.DataFrame
        Columns: amfi_code, scheme_name, date (datetime64), nav (float).
    """
    scheme_name = payload.get("meta", {}).get("scheme_name", "UNKNOWN")

    df = pd.DataFrame(payload["data"])
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df["amfi_code"] = amfi_code
    df["scheme_name"] = scheme_name

    # Drop rows where parsing failed (should be rare/none for this API)
    before = len(df)
    df = df.dropna(subset=["date", "nav"])
    dropped = before - len(df)
    if dropped:
        logger.warning(f"amfi_code {amfi_code}: dropped {dropped} rows with unparseable date/nav")

    df = df.sort_values("date").reset_index(drop=True)
    return df[["amfi_code", "scheme_name", "date", "nav"]]


def save_scheme_csv(amfi_code: int, label: str, df: pd.DataFrame) -> Path:
    """
    Save a scheme's NAV DataFrame to data/raw/live/{label}_{amfi_code}.csv.

    Parameters
    ----------
    amfi_code : int
        The AMFI scheme code.
    label : str
        Friendly filename label (e.g. 'hdfc_top_100_direct').
    df : pd.DataFrame
        NAV data to write.

    Returns
    -------
    Path
        The path the file was written to.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{label}_{amfi_code}.csv"
    df.to_csv(output_path, index=False)
    return output_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Fetch live NAV for every scheme in SCHEMES, save each as a raw CSV,
    and print a summary. Returns an exit code (0 = all succeeded,
    1 = one or more schemes failed).
    """
    logger.info(f"Fetching live NAV for {len(SCHEMES)} scheme(s) from {API_BASE_URL}")

    succeeded: list[str] = []
    failed: list[str] = []

    for i, (amfi_code, label) in enumerate(SCHEMES.items()):
        logger.info(f"[{i + 1}/{len(SCHEMES)}] Fetching amfi_code={amfi_code} ({label})...")

        payload = fetch_scheme_nav(amfi_code)
        if payload is None:
            failed.append(label)
        else:
            df = payload_to_dataframe(amfi_code, payload)
            output_path = save_scheme_csv(amfi_code, label, df)
            logger.info(
                f"amfi_code={amfi_code}: saved {len(df):,} rows "
                f"({df['date'].min().date()} to {df['date'].max().date()}) -> {output_path}"
            )
            succeeded.append(label)

        # Be polite to the free public API — skip the sleep after the last call
        if i < len(SCHEMES) - 1:
            time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)

    print(f"\n{'=' * 80}")
    print("LIVE NAV FETCH SUMMARY")
    print(f"{'=' * 80}")
    print(f"Succeeded ({len(succeeded)}): {succeeded}")
    print(f"Failed ({len(failed)}): {failed}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())