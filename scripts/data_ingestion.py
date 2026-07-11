"""
data_ingestion.py
------------------
Bluestock Fintech | Mutual Fund Analytics Capstone | Day 1

Loads all 10 raw AMFI-sourced CSV datasets, prints diagnostic
information (shape, dtypes, head, null counts), and runs a
foreign-key style validation of amfi_code across the fund_master,
nav_history, and investor_transactions files.

Usage:
    python scripts/data_ingestion.py

Author: Bluestock MF Capstone
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Project root is two levels up from this file (scripts/ -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

# Expected datasets: filename -> list of columns that MUST be present.
# This lets us fail loudly and specifically if AMFI changes a schema,
# instead of silently proceeding with a malformed DataFrame.
DATASET_CONFIG: dict[str, list[str]] = {
    "01_fund_master.csv": [
        "amfi_code", "fund_house", "scheme_name", "category",
        "sub_category", "plan", "launch_date", "benchmark",
        "expense_ratio_pct", "exit_load_pct", "fund_manager",
        "risk_category", "sebi_category_code",
    ],
    "02_nav_history.csv": ["amfi_code", "date", "nav"],
    "03_aum_by_fund_house.csv": [
        "date", "fund_house", "aum_lakh_crore", "aum_crore", "num_schemes",
    ],
    "04_monthly_sip_inflows.csv": [
        "month", "sip_inflow_crore", "active_sip_accounts_crore",
        "new_sip_accounts_lakh", "sip_aum_lakh_crore", "yoy_growth_pct",
    ],
    "05_category_inflows.csv": ["month", "category", "net_inflow_crore"],
    "06_industry_folio_count.csv": [
        "month", "total_folios_crore", "equity_folios_crore",
        "debt_folios_crore", "hybrid_folios_crore", "others_folios_crore",
    ],
    "07_scheme_performance.csv": [
        "amfi_code", "scheme_name", "fund_house", "category", "plan",
        "return_1yr_pct", "return_3yr_pct", "return_5yr_pct",
        "benchmark_3yr_pct", "alpha", "beta", "sharpe_ratio",
        "sortino_ratio", "std_dev_ann_pct", "max_drawdown_pct",
        "aum_crore", "expense_ratio_pct", "morningstar_rating", "risk_grade",
    ],
    "08_investor_transactions.csv": [
        "investor_id", "transaction_date", "amfi_code", "transaction_type",
        "amount_inr", "state", "city", "city_tier", "age_group", "gender",
        "annual_income_lakh", "payment_mode", "kyc_status",
    ],
    "09_portfolio_holdings.csv": [
        "amfi_code", "stock_symbol", "stock_name", "sector",
        "weight_pct", "market_value_cr", "current_price_inr", "portfolio_date",
    ],
    "10_benchmark_indices.csv": ["date", "index_name", "close_value"],
}

# Date columns to parse per file, so pandas doesn't leave them as strings
DATE_COLUMNS: dict[str, list[str]] = {
    "01_fund_master.csv": ["launch_date"],
    "02_nav_history.csv": ["date"],
    "03_aum_by_fund_house.csv": ["date"],
    "08_investor_transactions.csv": ["transaction_date"],
    "09_portfolio_holdings.csv": ["portfolio_date"],
    "10_benchmark_indices.csv": ["date"],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("data_ingestion")


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def load_csv(filename: str, expected_columns: list[str]) -> pd.DataFrame | None:
    """
    Load a single CSV from data/raw/, validate expected columns exist,
    and parse any known date columns.

    Parameters
    ----------
    filename : str
        Name of the CSV file inside data/raw/.
    expected_columns : list[str]
        Columns that must be present for the file to be considered valid.

    Returns
    -------
    pd.DataFrame | None
        The loaded DataFrame, or None if loading failed.
    """
    file_path = RAW_DATA_DIR / filename

    if not file_path.exists():
        logger.error(f"Missing file: {file_path}")
        return None

    try:
        parse_dates = DATE_COLUMNS.get(filename)
        df = pd.read_csv(file_path, parse_dates=parse_dates)
    except Exception as exc:
        logger.error(f"Failed to read {filename}: {exc}")
        return None

    missing_cols = set(expected_columns) - set(df.columns)
    if missing_cols:
        logger.warning(f"{filename}: missing expected columns {missing_cols}")

    return df


def summarize_dataframe(name: str, df: pd.DataFrame) -> None:
    """
    Print shape, dtypes, head, and null-count diagnostics for a DataFrame.

    Parameters
    ----------
    name : str
        Human-readable dataset name (used in printed headers).
    df : pd.DataFrame
        The DataFrame to summarize.
    """
    print(f"\n{'=' * 80}")
    print(f"DATASET: {name}")
    print(f"{'=' * 80}")
    print(f"Shape: {df.shape[0]:,} rows x {df.shape[1]} columns")

    print("\nDtypes:")
    print(df.dtypes.to_string())

    print("\nHead (3 rows):")
    print(df.head(3).to_string())

    null_counts = df.isnull().sum()
    nulls_present = null_counts[null_counts > 0]
    if not nulls_present.empty:
        print("\nAnomaly — null values found:")
        print(nulls_present.to_string())
    else:
        print("\nNo null values found.")

    dup_count = df.duplicated().sum()
    if dup_count > 0:
        print(f"Anomaly — {dup_count} fully duplicated rows found.")


def validate_amfi_codes(
    fund_master: pd.DataFrame,
    nav_history: pd.DataFrame,
    transactions: pd.DataFrame,
) -> None:
    """
    Cross-validate amfi_code as a foreign key across the three files
    that reference it, and print a short data-quality summary.

    Every amfi_code in nav_history and investor_transactions should
    exist in fund_master (the dimension table). Any that don't are
    orphaned records — an ETL red flag.
    """
    print(f"\n{'=' * 80}")
    print("DATA QUALITY SUMMARY: amfi_code referential integrity")
    print(f"{'=' * 80}")

    master_codes = set(fund_master["amfi_code"])
    nav_codes = set(nav_history["amfi_code"])
    tx_codes = set(transactions["amfi_code"])

    print(f"Unique amfi_codes in fund_master:          {len(master_codes)}")
    print(f"Unique amfi_codes in nav_history:           {len(nav_codes)}")
    print(f"Unique amfi_codes in investor_transactions: {len(tx_codes)}")

    orphaned_nav = nav_codes - master_codes
    orphaned_tx = tx_codes - master_codes

    if orphaned_nav:
        print(f"WARNING: {len(orphaned_nav)} amfi_code(s) in nav_history "
              f"not found in fund_master: {sorted(orphaned_nav)}")
    else:
        print("PASS: All nav_history amfi_codes exist in fund_master.")

    if orphaned_tx:
        print(f"WARNING: {len(orphaned_tx)} amfi_code(s) in investor_transactions "
              f"not found in fund_master: {sorted(orphaned_tx)}")
    else:
        print("PASS: All investor_transactions amfi_codes exist in fund_master.")


def explore_fund_master(fund_master: pd.DataFrame) -> None:
    """
    Print unique fund houses, categories, sub-categories, and risk
    grades from the fund master dataset — a quick sanity/exploration
    step before deeper analysis.
    """
    print(f"\n{'=' * 80}")
    print("FUND MASTER EXPLORATION")
    print(f"{'=' * 80}")

    for col in ["fund_house", "category", "sub_category", "risk_category"]:
        if col in fund_master.columns:
            uniques = fund_master[col].dropna().unique()
            print(f"\n{col} ({len(uniques)} unique values):")
            print(sorted(uniques.tolist()))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Load all 10 datasets, print diagnostics for each, run amfi_code
    validation, and explore fund_master. Returns an exit code
    (0 = success, 1 = one or more files failed to load).
    """
    if not RAW_DATA_DIR.exists():
        logger.error(f"Raw data directory not found: {RAW_DATA_DIR}")
        return 1

    logger.info(f"Loading datasets from: {RAW_DATA_DIR}")

    loaded: dict[str, pd.DataFrame] = {}
    failed: list[str] = []

    for filename, expected_cols in DATASET_CONFIG.items():
        df = load_csv(filename, expected_cols)
        if df is None:
            failed.append(filename)
            continue
        loaded[filename] = df
        summarize_dataframe(filename, df)

    if failed:
        logger.error(f"Failed to load {len(failed)} file(s): {failed}")

    # Fund master exploration
    if "01_fund_master.csv" in loaded:
        explore_fund_master(loaded["01_fund_master.csv"])

    # amfi_code referential integrity check
    required_for_validation = [
        "01_fund_master.csv", "02_nav_history.csv", "08_investor_transactions.csv",
    ]
    if all(f in loaded for f in required_for_validation):
        validate_amfi_codes(
            fund_master=loaded["01_fund_master.csv"],
            nav_history=loaded["02_nav_history.csv"],
            transactions=loaded["08_investor_transactions.csv"],
        )
    else:
        logger.warning(
            "Skipping amfi_code validation — one or more required files failed to load."
        )

    logger.info(f"Ingestion complete. {len(loaded)}/{len(DATASET_CONFIG)} files loaded successfully.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())