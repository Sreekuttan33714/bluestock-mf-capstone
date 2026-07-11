"""
clean_nav.py

Cleans raw NAV (Net Asset Value) history data for the Bluestock MF
Analytics Capstone.

Pipeline:
    1. Load raw CSV (amfi_code, date, nav).
    2. Parse dates, sort by (amfi_code, date).
    3. Drop exact duplicate (amfi_code, date) rows, keeping the first
       occurrence.
    4. For each amfi_code, reindex onto a full business-day range
       (pd.bdate_range) spanning that fund's min-to-max date, so that
       market holidays / data gaps become explicit NaN rows.
    5. Forward-fill NAV within each fund (NAV is assumed constant on a
       non-trading day = previous close), and add a boolean `is_filled`
       column marking which rows were forward-filled vs. originally
       reported.
    6. Warn (not fail) if any fund has *leading* NaNs that ffill could
       not resolve (i.e., the fund's business-day range starts before
       its first actual NAV record).
    7. Validate NAV > 0 post-fill and write the cleaned output.

Usage (from project root, venv active):
    python scripts/clean_nav.py

Input:
    data/raw/02_nav_history.csv
Output:
    data/processed/nav_history_clean.csv
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "02_nav_history.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_PATH = PROCESSED_DIR / "nav_history_clean.csv"

REQUIRED_COLUMNS = {"amfi_code", "date", "nav"}


def load_raw_nav(path: Path) -> pd.DataFrame:
    """Load the raw NAV CSV and do basic structural validation."""
    if not path.exists():
        raise FileNotFoundError(f"Raw NAV file not found at: {path}")

    df = pd.read_csv(path)

    missing_cols = REQUIRED_COLUMNS - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns in raw NAV data: {missing_cols}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = df["date"].isnull().sum()
    if bad_dates:
        logger.warning("%d rows had unparseable dates and were dropped.", bad_dates)
        df = df.dropna(subset=["date"])

    df["amfi_code"] = df["amfi_code"].astype(int)
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")

    logger.info("Loaded raw NAV data: %d rows, %d funds.", len(df), df["amfi_code"].nunique())
    return df


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Remove exact duplicate (amfi_code, date) rows, keeping the first."""
    before = len(df)
    df = df.sort_values(["amfi_code", "date"])
    df = df.drop_duplicates(subset=["amfi_code", "date"], keep="first")
    removed = before - len(df)
    if removed:
        logger.info("Removed %d duplicate (amfi_code, date) rows.", removed)
    else:
        logger.info("No duplicate (amfi_code, date) rows found.")
    return df


def reindex_and_fill(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each fund, reindex onto its full business-day date range and
    forward-fill NAV gaps (e.g. market holidays not already excluded
    from a business-day calendar).

    Adds `is_filled`: True where the row's NAV was forward-filled
    rather than originally present in the raw data.
    """
    filled_frames = []
    leading_null_funds = []

    for amfi_code, group in df.groupby("amfi_code", sort=False):
        group = group.set_index("date").sort_index()

        full_range = pd.bdate_range(group.index.min(), group.index.max())
        reindexed = group.reindex(full_range)
        reindexed.index.name = "date"

        reindexed["is_filled"] = reindexed["nav"].isnull()
        reindexed["nav"] = reindexed["nav"].ffill()
        reindexed["amfi_code"] = amfi_code

        residual_nulls = reindexed["nav"].isnull().sum()
        if residual_nulls:
            leading_null_funds.append((amfi_code, residual_nulls))

        filled_frames.append(reindexed.reset_index())

    result = pd.concat(filled_frames, ignore_index=True)

    n_filled = int(result["is_filled"].sum())
    if n_filled:
        logger.info(
            "Forward-filled %d NAV rows across all funds (non-trading day gaps).",
            n_filled,
        )
    else:
        logger.info("No gaps found — every fund had a NAV for every business day.")

    if leading_null_funds:
        logger.warning(
            "The following funds have residual (leading) NaN NAV values that "
            "ffill could not resolve, because the gap occurs before the "
            "fund's first recorded NAV: %s",
            leading_null_funds,
        )

    return result[["amfi_code", "date", "nav", "is_filled"]]


def validate(df: pd.DataFrame) -> None:
    """Post-fill sanity checks. Raises on hard failures, warns on soft ones."""
    non_positive = (df["nav"] <= 0).sum()
    if non_positive:
        raise ValueError(f"Found {non_positive} rows with NAV <= 0 after cleaning.")

    remaining_nulls = df["nav"].isnull().sum()
    if remaining_nulls:
        logger.warning(
            "%d rows still have null NAV after cleaning (see leading-NaN warning above).",
            remaining_nulls,
        )

    dupes = df.duplicated(subset=["amfi_code", "date"]).sum()
    if dupes:
        raise ValueError(f"Found {dupes} duplicate (amfi_code, date) rows after cleaning.")

    logger.info("Validation passed: NAV > 0, no duplicate keys.")


def main() -> None:
    logger.info("Starting NAV history cleaning...")

    df = load_raw_nav(RAW_PATH)
    df = dedupe(df)
    df = reindex_and_fill(df)
    validate(df)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(["amfi_code", "date"]).reset_index(drop=True)
    df.to_csv(OUTPUT_PATH, index=False)

    logger.info(
        "Done. Wrote %d rows (%d funds) to %s",
        len(df),
        df["amfi_code"].nunique(),
        OUTPUT_PATH,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        logger.error("clean_nav.py failed: %s", exc)
        sys.exit(1)