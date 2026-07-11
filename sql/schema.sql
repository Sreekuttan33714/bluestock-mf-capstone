-- ============================================================================
-- schema.sql
-- Bluestock MF Analytics Capstone — SQLite Star Schema
--
-- 2 Dimension tables : dim_fund, dim_date
-- 8 Fact tables      : fact_nav, fact_transactions, fact_performance,
--                       fact_aum, fact_portfolio, fact_sip_industry,
--                       fact_category_inflows, fact_benchmark
--
-- Conventions:
--   - All dates stored as TEXT in ISO-8601 format (YYYY-MM-DD) so they
--     sort correctly and join cleanly against dim_date.date.
--   - Monthly-grain facts (fact_sip_industry, fact_category_inflows)
--     keep the original 'YYYY-MM' string for readability AND a
--     'month_date' (first-of-month) column that FKs to dim_date, since
--     dim_date's grain is daily.
--   - Boolean flags stored as INTEGER (0/1) — SQLite has no native BOOLEAN.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- DIMENSION: dim_fund
-- Source: 01_fund_master.csv
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS dim_fund;
CREATE TABLE dim_fund (
    amfi_code           INTEGER PRIMARY KEY,
    fund_house          TEXT NOT NULL,
    scheme_name         TEXT NOT NULL,
    category            TEXT,
    sub_category        TEXT,
    plan                TEXT,
    launch_date         TEXT,
    benchmark           TEXT,
    expense_ratio_pct   REAL,
    exit_load_pct       REAL,
    min_sip_amount      INTEGER,
    min_lumpsum_amount  INTEGER,
    fund_manager        TEXT,
    risk_category       TEXT,
    sebi_category_code  TEXT
);

-- ----------------------------------------------------------------------------
-- DIMENSION: dim_date
-- Generated calendar (daily grain), with Indian fiscal-year attributes
-- (FY = April-to-March).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date (
    date                TEXT PRIMARY KEY,   -- ISO YYYY-MM-DD
    date_id             INTEGER UNIQUE,     -- YYYYMMDD surrogate, BI-friendly
    year                INTEGER NOT NULL,
    quarter             INTEGER NOT NULL,   -- calendar quarter 1-4
    month               INTEGER NOT NULL,
    month_name          TEXT NOT NULL,
    day                 INTEGER NOT NULL,
    day_of_week         INTEGER NOT NULL,   -- 0=Mon .. 6=Sun
    day_name            TEXT NOT NULL,
    is_weekend          INTEGER NOT NULL,   -- 0/1
    fiscal_year         TEXT NOT NULL,      -- e.g. 'FY2022-23'
    fiscal_quarter      INTEGER NOT NULL,   -- 1=Apr-Jun .. 4=Jan-Mar
    is_month_end        INTEGER NOT NULL,
    is_quarter_end      INTEGER NOT NULL,
    is_fiscal_year_end  INTEGER NOT NULL
);

-- ----------------------------------------------------------------------------
-- FACT: fact_nav
-- Source: data/processed/nav_history_clean.csv (output of clean_nav.py)
-- Grain: one row per (amfi_code, date)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_nav;
CREATE TABLE fact_nav (
    amfi_code   INTEGER NOT NULL,
    date        TEXT NOT NULL,
    nav         REAL NOT NULL,
    is_filled   INTEGER NOT NULL,   -- 1 = forward-filled (non-trading day)
    PRIMARY KEY (amfi_code, date),
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code),
    FOREIGN KEY (date) REFERENCES dim_date(date)
);

-- ----------------------------------------------------------------------------
-- FACT: fact_transactions
-- Source: data/processed/investor_transactions_clean.csv
--         (output of clean_transactions.py)
-- Grain: one row per investor transaction
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_transactions;
CREATE TABLE fact_transactions (
    transaction_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    investor_id                     TEXT NOT NULL,
    transaction_date                TEXT NOT NULL,
    amfi_code                       INTEGER NOT NULL,
    transaction_type                TEXT,
    amount_inr                      REAL,
    state                           TEXT,
    city                            TEXT,
    city_tier                       TEXT,
    age_group                       TEXT,
    gender                          TEXT,
    annual_income_lakh              REAL,
    payment_mode                    TEXT,
    kyc_status                      TEXT,
    flag_invalid_date               INTEGER,
    flag_invalid_transaction_type   INTEGER,
    flag_invalid_amount             INTEGER,
    flag_invalid_kyc_status         INTEGER,
    flag_orphan_amfi_code           INTEGER,
    flag_invalid_city_tier          INTEGER,
    flag_invalid_age_group          INTEGER,
    flag_invalid_gender             INTEGER,
    flag_invalid_payment_mode       INTEGER,
    flag_invalid_income             INTEGER,
    has_data_quality_flag           INTEGER,
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code),
    FOREIGN KEY (transaction_date) REFERENCES dim_date(date)
);

-- ----------------------------------------------------------------------------
-- FACT: fact_performance
-- Source: 07_scheme_performance.csv
-- Grain: one row per fund (point-in-time snapshot of return/risk metrics)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_performance;
CREATE TABLE fact_performance (
    amfi_code           INTEGER PRIMARY KEY,
    scheme_name         TEXT,
    fund_house          TEXT,
    category            TEXT,
    plan                TEXT,
    return_1yr_pct      REAL,
    return_3yr_pct      REAL,
    return_5yr_pct      REAL,
    benchmark_3yr_pct   REAL,
    alpha               REAL,
    beta                REAL,
    sharpe_ratio        REAL,
    sortino_ratio       REAL,
    std_dev_ann_pct     REAL,
    max_drawdown_pct    REAL,
    aum_crore           INTEGER,
    expense_ratio_pct   REAL,
    morningstar_rating  INTEGER,
    risk_grade          TEXT,
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code)
);

-- ----------------------------------------------------------------------------
-- FACT: fact_aum
-- Source: 03_aum_by_fund_house.csv
-- Grain: one row per (date, fund_house) — date is a quarter-end snapshot
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_aum;
CREATE TABLE fact_aum (
    aum_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    fund_house      TEXT NOT NULL,
    aum_lakh_crore  REAL,
    aum_crore       INTEGER,
    num_schemes     INTEGER,
    FOREIGN KEY (date) REFERENCES dim_date(date)
);

-- ----------------------------------------------------------------------------
-- FACT: fact_portfolio
-- Source: 09_portfolio_holdings.csv
-- Grain: one row per (amfi_code, stock_symbol, portfolio_date)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_portfolio;
CREATE TABLE fact_portfolio (
    holding_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    amfi_code           INTEGER NOT NULL,
    stock_symbol        TEXT,
    stock_name          TEXT,
    sector              TEXT,
    weight_pct          REAL,
    market_value_cr     REAL,
    current_price_inr   REAL,
    portfolio_date      TEXT NOT NULL,
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code),
    FOREIGN KEY (portfolio_date) REFERENCES dim_date(date)
);

-- ----------------------------------------------------------------------------
-- FACT: fact_sip_industry
-- Source: 04_monthly_sip_inflows.csv LEFT JOIN 06_industry_folio_count.csv
--         on month.
-- Grain: one row per month. 04 is monthly (48 rows); 06 is quarterly-ish
--        (21 rows) — folio columns are intentionally NULL for months with
--        no folio-count reading. yoy_growth_pct is also intentionally NULL
--        for the first 12 months (no prior-year base to compare against).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_sip_industry;
CREATE TABLE fact_sip_industry (
    sip_id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    month                        TEXT NOT NULL,   -- 'YYYY-MM'
    month_date                   TEXT NOT NULL,   -- first-of-month, FK to dim_date
    sip_inflow_crore             INTEGER,
    active_sip_accounts_crore    REAL,
    new_sip_accounts_lakh        REAL,
    sip_aum_lakh_crore           REAL,
    yoy_growth_pct               REAL,
    total_folios_crore           REAL,
    equity_folios_crore          REAL,
    debt_folios_crore            REAL,
    hybrid_folios_crore          REAL,
    others_folios_crore          REAL,
    FOREIGN KEY (month_date) REFERENCES dim_date(date)
);

-- ----------------------------------------------------------------------------
-- FACT: fact_category_inflows
-- Source: 05_category_inflows.csv
-- Grain: one row per (month, category)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_category_inflows;
CREATE TABLE fact_category_inflows (
    inflow_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    month             TEXT NOT NULL,
    month_date        TEXT NOT NULL,
    category          TEXT NOT NULL,
    net_inflow_crore  REAL,
    FOREIGN KEY (month_date) REFERENCES dim_date(date)
);

-- ----------------------------------------------------------------------------
-- FACT: fact_benchmark
-- Source: 10_benchmark_indices.csv
-- Grain: one row per (date, index_name)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_benchmark;
CREATE TABLE fact_benchmark (
    benchmark_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    index_name    TEXT NOT NULL,
    close_value   REAL,
    FOREIGN KEY (date) REFERENCES dim_date(date)
);