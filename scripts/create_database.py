"""
create_database.py

Builds bluestock_mf.db: a 10-table SQLite star schema (2 dims + 8 facts)
for the Bluestock MF Analytics Capstone, and loads all source data into it.

Pipeline:
    1. Apply schema.sql (DROP + CREATE all 10 tables, PRAGMA foreign_keys=ON).
    2. Build dim_date (generated daily calendar, Indian fiscal-year attrs).
    3. Load dim_fund from 01_fund_master.csv.
    4. Load each fact table:
         fact_nav              <- data/processed/nav_history_clean.csv
         fact_transactions     <- data/processed/investor_transactions_clean.csv
         fact_performance      <- 07_scheme_performance.csv
         fact_aum              <- 03_aum_by_fund_house.csv
         fact_portfolio        <- 09_portfolio_holdings.csv
         fact_sip_industry     <- 04_monthly_sip_inflows.csv LEFT JOIN
                                   06_industry_folio_count.csv on month
         fact_category_inflows <- 05_category_inflows.csv
         fact_benchmark        <- 10_benchmark_indices.csv
    5. Verify row counts loaded match source row counts.
    6. Verify no FK orphans (belt-and-braces check on top of
       PRAGMA foreign_keys=ON, which would already reject orphans at
       insert time).

IMPORTANT — run order:
    python scripts/clean_nav.py           (must run first)
    python scripts/clean_transactions.py  (must run first)
    python scripts/create_database.py     (this script, run last)

Usage (from project root, venv active):
    python scripts/create_database.py
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SQL_DIR = PROJECT_ROOT / "sql"
SCHEMA_PATH = SQL_DIR / "schema.sql"
DB_PATH = PROJECT_ROOT / "bluestock_mf.db"

# Calendar span for dim_date — comfortably covers every date-bearing
# source file (earliest 2022-01-03, latest 2026-05-29).
DIM_DATE_START = "2022-01-01"
DIM_DATE_END = "2026-12-31"

FISCAL_QUARTER_MAP = {
    4: 1, 5: 1, 6: 1,
    7: 2, 8: 2, 9: 2,
    10: 3, 11: 3, 12: 3,
    1: 4, 2: 4, 3: 4,
}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def apply_schema(conn: sqlite3.Connection) -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema.sql not found at {SCHEMA_PATH}")
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()
    logger.info("Applied schema.sql — all 10 tables (re)created.")


# ---------------------------------------------------------------------------
# dim_date
# ---------------------------------------------------------------------------
def build_dim_date(start: str, end: str) -> pd.DataFrame:
    dates = pd.date_range(start=start, end=end, freq="D")
    df = pd.DataFrame({"date_dt": dates})

    df["date"] = df["date_dt"].dt.strftime("%Y-%m-%d")
    df["date_id"] = df["date_dt"].dt.strftime("%Y%m%d").astype(int)
    df["year"] = df["date_dt"].dt.year
    df["quarter"] = df["date_dt"].dt.quarter
    df["month"] = df["date_dt"].dt.month
    df["month_name"] = df["date_dt"].dt.strftime("%B")
    df["day"] = df["date_dt"].dt.day
    df["day_of_week"] = df["date_dt"].dt.dayofweek  # 0=Mon..6=Sun
    df["day_name"] = df["date_dt"].dt.strftime("%A")
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # Indian fiscal year: April(Y) - March(Y+1) => 'FY{Y}-{Y+1 last2}'
    fy_start_year = df["year"].where(df["month"] >= 4, df["year"] - 1)
    df["fiscal_year"] = (
        "FY" + fy_start_year.astype(str) + "-" + ((fy_start_year + 1) % 100).astype(str).str.zfill(2)
    )
    df["fiscal_quarter"] = df["month"].map(FISCAL_QUARTER_MAP)

    month_end = df["date_dt"] + pd.offsets.MonthEnd(0)
    df["is_month_end"] = (df["date_dt"] == month_end).astype(int)
    df["is_quarter_end"] = (df["is_month_end"] == 1) & (df["month"].isin([3, 6, 9, 12]))
    df["is_quarter_end"] = df["is_quarter_end"].astype(int)
    df["is_fiscal_year_end"] = ((df["is_month_end"] == 1) & (df["month"] == 3)).astype(int)

    df = df.drop(columns=["date_dt"])
    logger.info("Built dim_date: %d calendar days (%s to %s).", len(df), start, end)
    return df


# ---------------------------------------------------------------------------
# Loaders — each returns a DataFrame shaped exactly like its target table
# ---------------------------------------------------------------------------
def load_dim_fund() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "01_fund_master.csv")
    return df


def load_fact_nav() -> pd.DataFrame:
    path = PROCESSED_DIR / "nav_history_clean.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run scripts/clean_nav.py first."
        )
    df = pd.read_csv(path)
    df["is_filled"] = df["is_filled"].astype(int)
    return df


def load_fact_transactions() -> pd.DataFrame:
    path = PROCESSED_DIR / "investor_transactions_clean.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run scripts/clean_transactions.py first."
        )
    df = pd.read_csv(path)
    flag_cols = [c for c in df.columns if c.startswith("flag_") or c == "has_data_quality_flag"]
    for col in flag_cols:
        df[col] = df[col].astype(int)
    return df


def load_fact_performance() -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / "07_scheme_performance.csv")


def load_fact_aum() -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / "03_aum_by_fund_house.csv")


def load_fact_portfolio() -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / "09_portfolio_holdings.csv")


def load_fact_sip_industry() -> pd.DataFrame:
    """LEFT JOIN monthly SIP inflows with quarterly folio counts on month."""
    sip = pd.read_csv(RAW_DIR / "04_monthly_sip_inflows.csv")
    folio = pd.read_csv(RAW_DIR / "06_industry_folio_count.csv")

    merged = sip.merge(folio, on="month", how="left")
    merged["month_date"] = pd.to_datetime(merged["month"] + "-01").dt.strftime("%Y-%m-%d")

    cols = [
        "month", "month_date", "sip_inflow_crore", "active_sip_accounts_crore",
        "new_sip_accounts_lakh", "sip_aum_lakh_crore", "yoy_growth_pct",
        "total_folios_crore", "equity_folios_crore", "debt_folios_crore",
        "hybrid_folios_crore", "others_folios_crore",
    ]
    return merged[cols]


def load_fact_category_inflows() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "05_category_inflows.csv")
    df["month_date"] = pd.to_datetime(df["month"] + "-01").dt.strftime("%Y-%m-%d")
    return df[["month", "month_date", "category", "net_inflow_crore"]]


def load_fact_benchmark() -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / "10_benchmark_indices.csv")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify_row_counts(conn: sqlite3.Connection, expected: dict[str, int]) -> None:
    logger.info("Verifying row counts...")
    all_ok = True
    for table, expected_n in expected.items():
        actual_n = conn.execute(f"SELECT COUNT(*) FROM {table};").fetchone()[0]
        status = "OK" if actual_n == expected_n else "MISMATCH"
        if status == "MISMATCH":
            all_ok = False
        logger.info("  %-24s expected=%-8d actual=%-8d [%s]", table, expected_n, actual_n, status)
    if not all_ok:
        raise ValueError("Row count verification failed — see MISMATCH rows above.")
    logger.info("All row counts verified.")


def check_fk_orphans(conn: sqlite3.Connection) -> None:
    """
    Explicit orphan check as a belt-and-braces measure on top of
    PRAGMA foreign_keys=ON (which already blocks orphaned inserts at
    write time — this just confirms the DB is clean and reports counts).
    """
    checks = [
        ("fact_nav", "amfi_code", "dim_fund", "amfi_code"),
        ("fact_nav", "date", "dim_date", "date"),
        ("fact_transactions", "amfi_code", "dim_fund", "amfi_code"),
        ("fact_transactions", "transaction_date", "dim_date", "date"),
        ("fact_performance", "amfi_code", "dim_fund", "amfi_code"),
        ("fact_aum", "date", "dim_date", "date"),
        ("fact_portfolio", "amfi_code", "dim_fund", "amfi_code"),
        ("fact_portfolio", "portfolio_date", "dim_date", "date"),
        ("fact_sip_industry", "month_date", "dim_date", "date"),
        ("fact_category_inflows", "month_date", "dim_date", "date"),
        ("fact_benchmark", "date", "dim_date", "date"),
    ]
    logger.info("Checking for FK orphans...")
    any_orphans = False
    for fact_table, fk_col, dim_table, dim_col in checks:
        query = f"""
            SELECT COUNT(*) FROM {fact_table} f
            LEFT JOIN {dim_table} d ON f.{fk_col} = d.{dim_col}
            WHERE d.{dim_col} IS NULL;
        """
        orphan_count = conn.execute(query).fetchone()[0]
        if orphan_count:
            any_orphans = True
            logger.warning(
                "  ORPHANS: %s.%s -> %s.%s : %d orphan rows",
                fact_table, fk_col, dim_table, dim_col, orphan_count,
            )
    if not any_orphans:
        logger.info("No FK orphans found across any fact table.")
    else:
        raise ValueError("FK orphan check failed — see warnings above.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    logger.info("Starting database build...")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    apply_schema(conn)

    # SQLAlchemy engine for pandas.to_sql, with FK pragma enforced on
    # every connection it opens (SQLAlchemy sqlite recipe).
    engine = create_engine(f"sqlite:///{DB_PATH}")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

    # --- Load order matters: dims before facts ---
    loaders = {
        "dim_date": lambda: build_dim_date(DIM_DATE_START, DIM_DATE_END),
        "dim_fund": load_dim_fund,
        "fact_nav": load_fact_nav,
        "fact_transactions": load_fact_transactions,
        "fact_performance": load_fact_performance,
        "fact_aum": load_fact_aum,
        "fact_portfolio": load_fact_portfolio,
        "fact_sip_industry": load_fact_sip_industry,
        "fact_category_inflows": load_fact_category_inflows,
        "fact_benchmark": load_fact_benchmark,
    }

    expected_counts: dict[str, int] = {}
    for table_name, loader_fn in loaders.items():
        df = loader_fn()
        df.to_sql(table_name, engine, if_exists="append", index=False)
        expected_counts[table_name] = len(df)
        logger.info("Loaded %-24s %d rows.", table_name, len(df))

    conn.close()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    verify_row_counts(conn, expected_counts)
    check_fk_orphans(conn)
    conn.close()

    logger.info("Database build complete: %s", DB_PATH)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        logger.error("create_database.py failed: %s", exc)
        sys.exit(1)