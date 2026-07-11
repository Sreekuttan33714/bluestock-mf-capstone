"""
clean_transactions.py

Cleans raw investor transaction data for the Bluestock MF Analytics
Capstone.

Philosophy: FLAG, DON'T DROP. Data quality issues are surfaced via
boolean flag columns (and a `has_data_quality_flag` rollup) rather
than silently removed, so downstream analysis can decide whether to
include/exclude flagged rows.

Pipeline:
    1. Load raw CSV.
    2. Parse and validate transaction_date.
    3. Standardise transaction_type to {SIP, Lumpsum, Redemption}
       (case/whitespace-insensitive mapping).
    4. Validate amount_inr > 0.
    5. Coerce kyc_status to {Verified, Pending} (flag anything else).
    6. Referential integrity check: amfi_code must exist in dim_fund
       (01_fund_master.csv).
    7. Flag categorical fields (city_tier, age_group, gender,
       payment_mode) that fall outside an expected value set, without
       dropping them.
    8. Roll all per-row flags into `has_data_quality_flag`.
    9. Remove only EXACT full-row duplicates.

Usage (from project root, venv active):
    python scripts/clean_transactions.py

Input:
    data/raw/08_investor_transactions.csv
    data/raw/01_fund_master.csv   (for FK validation)
Output:
    data/processed/investor_transactions_clean.csv
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
RAW_DIR = PROJECT_ROOT / "data" / "raw"
TRANSACTIONS_PATH = RAW_DIR / "08_investor_transactions.csv"
FUND_MASTER_PATH = RAW_DIR / "01_fund_master.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_PATH = PROCESSED_DIR / "investor_transactions_clean.csv"

REQUIRED_COLUMNS = {
    "investor_id", "transaction_date", "amfi_code", "transaction_type",
    "amount_inr", "state", "city", "city_tier", "age_group", "gender",
    "annual_income_lakh", "payment_mode", "kyc_status",
}

TRANSACTION_TYPE_MAP = {
    "sip": "SIP",
    "lumpsum": "Lumpsum",
    "redemption": "Redemption",
}
KYC_STATUS_MAP = {
    "verified": "Verified",
    "pending": "Pending",
}
VALID_CITY_TIERS = {"T30", "B30"}
VALID_AGE_GROUPS = {"18-25", "26-35", "36-45", "46-55", "56+"}
VALID_GENDERS = {"Male", "Female", "Other"}
VALID_PAYMENT_MODES = {"UPI", "Cheque", "Mandate", "Net Banking", "Debit Card"}


def load_raw(path: Path, required_cols: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    df = pd.read_csv(path)
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {path.name}: {missing}")
    return df


def _standardise(series: pd.Series, mapping: dict) -> tuple:
    """
    Map a categorical series to canonical values using a
    case/whitespace-insensitive lookup.

    Returns (standardised_series, is_invalid_flag) where is_invalid_flag
    is True for values that didn't match any key in `mapping`.
    """
    normalised_key = series.astype(str).str.strip().str.lower()
    standardised = normalised_key.map(mapping)
    is_invalid = standardised.isnull()
    standardised = standardised.where(~is_invalid, series.astype(str).str.strip())
    return standardised, is_invalid


def clean_transactions(df: pd.DataFrame, valid_amfi_codes: set) -> pd.DataFrame:
    df = df.copy()

    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df["flag_invalid_date"] = df["transaction_date"].isnull()
    if df["flag_invalid_date"].any():
        logger.warning("%d rows have unparseable transaction_date.", df["flag_invalid_date"].sum())

    df["transaction_type"], df["flag_invalid_transaction_type"] = _standardise(
        df["transaction_type"], TRANSACTION_TYPE_MAP
    )
    n_bad_type = df["flag_invalid_transaction_type"].sum()
    if n_bad_type:
        logger.warning("%d rows have an unrecognised transaction_type.", n_bad_type)

    df["amount_inr"] = pd.to_numeric(df["amount_inr"], errors="coerce")
    df["flag_invalid_amount"] = df["amount_inr"].isnull() | (df["amount_inr"] <= 0)
    n_bad_amount = df["flag_invalid_amount"].sum()
    if n_bad_amount:
        logger.warning("%d rows have amount_inr <= 0 or non-numeric.", n_bad_amount)

    df["kyc_status"], df["flag_invalid_kyc_status"] = _standardise(
        df["kyc_status"], KYC_STATUS_MAP
    )
    n_bad_kyc = df["flag_invalid_kyc_status"].sum()
    if n_bad_kyc:
        logger.warning("%d rows have an unrecognised kyc_status.", n_bad_kyc)

    df["flag_orphan_amfi_code"] = ~df["amfi_code"].isin(valid_amfi_codes)
    n_orphan = df["flag_orphan_amfi_code"].sum()
    if n_orphan:
        logger.warning(
            "%d rows reference an amfi_code not present in fund_master (orphan FK).",
            n_orphan,
        )

    df["flag_invalid_city_tier"] = ~df["city_tier"].isin(VALID_CITY_TIERS)
    df["flag_invalid_age_group"] = ~df["age_group"].isin(VALID_AGE_GROUPS)
    df["flag_invalid_gender"] = ~df["gender"].isin(VALID_GENDERS)
    df["flag_invalid_payment_mode"] = ~df["payment_mode"].isin(VALID_PAYMENT_MODES)

    for col, flag_col in [
        ("city_tier", "flag_invalid_city_tier"),
        ("age_group", "flag_invalid_age_group"),
        ("gender", "flag_invalid_gender"),
        ("payment_mode", "flag_invalid_payment_mode"),
    ]:
        n_bad = df[flag_col].sum()
        if n_bad:
            logger.warning("%d rows have an unexpected %s value.", n_bad, col)

    df["annual_income_lakh"] = pd.to_numeric(df["annual_income_lakh"], errors="coerce")
    df["flag_invalid_income"] = df["annual_income_lakh"].isnull() | (df["annual_income_lakh"] <= 0)
    n_bad_income = df["flag_invalid_income"].sum()
    if n_bad_income:
        logger.warning("%d rows have annual_income_lakh <= 0 or non-numeric.", n_bad_income)

    flag_cols = [c for c in df.columns if c.startswith("flag_")]
    df["has_data_quality_flag"] = df[flag_cols].any(axis=1)

    before = len(df)
    dedup_cols = [c for c in df.columns if c not in flag_cols and c != "has_data_quality_flag"]
    df = df.drop_duplicates(subset=dedup_cols, keep="first")
    removed = before - len(df)
    if removed:
        logger.info("Removed %d exact duplicate rows.", removed)
    else:
        logger.info("No exact duplicate rows found.")

    return df


def main() -> None:
    logger.info("Starting investor transactions cleaning...")

    txns = load_raw(TRANSACTIONS_PATH, REQUIRED_COLUMNS)
    fund_master = load_raw(FUND_MASTER_PATH, {"amfi_code"})
    valid_amfi_codes = set(fund_master["amfi_code"].astype(int).unique())

    logger.info("Loaded %d raw transaction rows across %d investors.", len(txns), txns["investor_id"].nunique())

    cleaned = clean_transactions(txns, valid_amfi_codes)

    n_flagged = int(cleaned["has_data_quality_flag"].sum())
    pct_flagged = 100 * n_flagged / len(cleaned) if len(cleaned) else 0
    logger.info(
        "%d / %d rows (%.2f%%) carry at least one data-quality flag (retained, not dropped).",
        n_flagged, len(cleaned), pct_flagged,
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = cleaned.sort_values(["transaction_date", "investor_id"]).reset_index(drop=True)
    cleaned.to_csv(OUTPUT_PATH, index=False)

    logger.info("Done. Wrote %d rows to %s", len(cleaned), OUTPUT_PATH)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        logger.error("clean_transactions.py failed: %s", exc)
        sys.exit(1)