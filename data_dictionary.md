# Bluestock MF Analytics Capstone — Data Dictionary

**Database:** `bluestock_mf.db` (SQLite)
**Schema type:** Star schema — 2 dimension tables, 8 fact tables
**Last updated:** Day 2 of capstone sprint

---

## Table of Contents

1. [dim_fund](#dim_fund)
2. [dim_date](#dim_date)
3. [fact_nav](#fact_nav)
4. [fact_transactions](#fact_transactions)
5. [fact_performance](#fact_performance)
6. [fact_aum](#fact_aum)
7. [fact_portfolio](#fact_portfolio)
8. [fact_sip_industry](#fact_sip_industry)
9. [fact_category_inflows](#fact_category_inflows)
10. [fact_benchmark](#fact_benchmark)

---

## dim_fund

**Grain:** One row per mutual fund scheme.
**Source:** `01_fund_master.csv`
**Primary key:** `amfi_code`

| Column | Type | Business Definition |
|---|---|---|
| `amfi_code` | INTEGER (PK) | Unique AMFI-assigned scheme code identifying the mutual fund. |
| `fund_house` | TEXT | Asset Management Company (AMC) that manages the fund, e.g. "SBI Mutual Fund". |
| `scheme_name` | TEXT | Full official name of the scheme, including plan/option. |
| `category` | TEXT | SEBI-defined fund category, e.g. "Large Cap", "Debt", "Hybrid". |
| `sub_category` | TEXT | Finer-grained classification within the category. |
| `plan` | TEXT | Plan type — typically "Regular" or "Direct". |
| `launch_date` | TEXT (date) | Date the scheme was first launched. |
| `benchmark` | TEXT | Name of the benchmark index the fund is measured against (e.g. NIFTY50). |
| `expense_ratio_pct` | REAL | Annual expense ratio charged to investors, as a percentage of AUM. |
| `exit_load_pct` | REAL | Penalty percentage charged on early redemption. |
| `min_sip_amount` | INTEGER | Minimum SIP installment amount (INR). |
| `min_lumpsum_amount` | INTEGER | Minimum lumpsum investment amount (INR). |
| `fund_manager` | TEXT | Name of the fund manager(s) responsible for the scheme. |
| `risk_category` | TEXT | SEBI risk-o-meter category, e.g. "Moderate", "High". |
| `sebi_category_code` | TEXT | SEBI's internal category code for the scheme. |

---

## dim_date

**Grain:** One row per calendar day, 2022-01-01 to 2026-12-31.
**Source:** Generated (not from a raw CSV) by `create_database.py`.
**Primary key:** `date`

Uses **Indian fiscal year** convention: FY runs April 1 – March 31 (e.g., "FY2022-23" covers 1 Apr 2022 – 31 Mar 2023).

| Column | Type | Business Definition |
|---|---|---|
| `date` | TEXT (PK) | Calendar date in ISO format (`YYYY-MM-DD`). |
| `date_id` | INTEGER | Surrogate integer key in `YYYYMMDD` format, convenient for BI tools. |
| `year` | INTEGER | Calendar year. |
| `quarter` | INTEGER | Calendar quarter (1–4, Jan–Mar = Q1). |
| `month` | INTEGER | Calendar month number (1–12). |
| `month_name` | TEXT | Full month name (e.g. "January"). |
| `day` | INTEGER | Day of month. |
| `day_of_week` | INTEGER | 0 = Monday … 6 = Sunday. |
| `day_name` | TEXT | Full weekday name (e.g. "Monday"). |
| `is_weekend` | INTEGER (0/1) | 1 if Saturday or Sunday. |
| `fiscal_year` | TEXT | Indian fiscal year label, e.g. "FY2022-23". |
| `fiscal_quarter` | INTEGER | Fiscal quarter (1 = Apr–Jun … 4 = Jan–Mar). |
| `is_month_end` | INTEGER (0/1) | 1 if this date is the last calendar day of its month. |
| `is_quarter_end` | INTEGER (0/1) | 1 if this is a calendar-quarter-end date (Mar/Jun/Sep/Dec 31 or equivalent). |
| `is_fiscal_year_end` | INTEGER (0/1) | 1 if this date is 31 March (Indian fiscal year end). |

---

## fact_nav

**Grain:** One row per (fund, calendar day).
**Source:** `data/processed/nav_history_clean.csv` (output of `clean_nav.py`, derived from raw `02_nav_history.csv`).
**Primary key:** (`amfi_code`, `date`)
**Foreign keys:** `amfi_code` → `dim_fund.amfi_code`; `date` → `dim_date.date`

| Column | Type | Business Definition |
|---|---|---|
| `amfi_code` | INTEGER (FK) | Fund the NAV belongs to. |
| `date` | TEXT (FK) | Business day the NAV is reported for. |
| `nav` | REAL | Net Asset Value per unit (INR) for the fund on this date. |
| `is_filled` | INTEGER (0/1) | 1 if this NAV was forward-filled to cover a non-trading day / data gap rather than being an originally reported value. |

---

## fact_transactions

**Grain:** One row per individual investor transaction.
**Source:** `data/processed/investor_transactions_clean.csv` (output of `clean_transactions.py`, derived from raw `08_investor_transactions.csv`).
**Primary key:** `transaction_id` (surrogate, autoincrement)
**Foreign keys:** `amfi_code` → `dim_fund.amfi_code`; `transaction_date` → `dim_date.date`

| Column | Type | Business Definition |
|---|---|---|
| `transaction_id` | INTEGER (PK) | Surrogate key, unique per transaction row. |
| `investor_id` | TEXT | Anonymised unique identifier for the investor. |
| `transaction_date` | TEXT (FK) | Date the transaction occurred. |
| `amfi_code` | INTEGER (FK) | Fund the transaction was made in. |
| `transaction_type` | TEXT | One of `SIP`, `Lumpsum`, `Redemption`. |
| `amount_inr` | REAL | Transaction amount in INR. |
| `state` | TEXT | Indian state the investor is registered in. |
| `city` | TEXT | City the investor is registered in. |
| `city_tier` | TEXT | `T30` (Top-30 cities) or `B30` (Beyond Top-30) — SEBI/AMFI city-tier classification, used to track penetration beyond major metros. |
| `age_group` | TEXT | Investor age band, e.g. "26-35". |
| `gender` | TEXT | Investor gender. |
| `annual_income_lakh` | REAL | Investor's self-declared annual income, in INR lakh. |
| `payment_mode` | TEXT | Payment method used, e.g. "UPI", "Mandate", "Net Banking", "Cheque". |
| `kyc_status` | TEXT | `Verified` or `Pending` — investor's KYC (Know Your Customer) compliance status. |
| `flag_invalid_date` | INTEGER (0/1) | 1 if `transaction_date` could not be parsed in the raw source. |
| `flag_invalid_transaction_type` | INTEGER (0/1) | 1 if `transaction_type` did not match a known value. |
| `flag_invalid_amount` | INTEGER (0/1) | 1 if `amount_inr` was missing, non-numeric, or ≤ 0. |
| `flag_invalid_kyc_status` | INTEGER (0/1) | 1 if `kyc_status` did not match a known value. |
| `flag_orphan_amfi_code` | INTEGER (0/1) | 1 if `amfi_code` does not exist in `dim_fund` (broken referential integrity in source). |
| `flag_invalid_city_tier` | INTEGER (0/1) | 1 if `city_tier` was outside {T30, B30}. |
| `flag_invalid_age_group` | INTEGER (0/1) | 1 if `age_group` was outside the expected age bands. |
| `flag_invalid_gender` | INTEGER (0/1) | 1 if `gender` was outside {Male, Female, Other}. |
| `flag_invalid_payment_mode` | INTEGER (0/1) | 1 if `payment_mode` was outside the expected set. |
| `flag_invalid_income` | INTEGER (0/1) | 1 if `annual_income_lakh` was missing, non-numeric, or ≤ 0. |
| `has_data_quality_flag` | INTEGER (0/1) | Rollup: 1 if **any** of the above flags is 1. Data quality issues are flagged, not dropped — analysts can filter this column as needed. |

---

## fact_performance

**Grain:** One row per fund (point-in-time performance/risk snapshot).
**Source:** `07_scheme_performance.csv`
**Primary key:** `amfi_code`
**Foreign keys:** `amfi_code` → `dim_fund.amfi_code`

| Column | Type | Business Definition |
|---|---|---|
| `amfi_code` | INTEGER (PK/FK) | Fund identifier. |
| `scheme_name` | TEXT | Scheme name (denormalised copy, also in `dim_fund`). |
| `fund_house` | TEXT | AMC name (denormalised copy). |
| `category` | TEXT | Fund category (denormalised copy). |
| `plan` | TEXT | Plan type (denormalised copy). |
| `return_1yr_pct` | REAL | Trailing 1-year return, %. |
| `return_3yr_pct` | REAL | Trailing 3-year annualised return (CAGR), %. |
| `return_5yr_pct` | REAL | Trailing 5-year annualised return (CAGR), %. |
| `benchmark_3yr_pct` | REAL | Benchmark's 3-year annualised return, %, for comparison. |
| `alpha` | REAL | Jensen's Alpha vs. benchmark — excess return not explained by market movement (OLS regression). |
| `beta` | REAL | Beta vs. benchmark — the fund's sensitivity to benchmark movements (OLS regression). |
| `sharpe_ratio` | REAL | Risk-adjusted return: (fund return − risk-free rate) / total volatility. Rf = 6.5%, annualised via √252. |
| `sortino_ratio` | REAL | Like Sharpe, but penalises only downside volatility. |
| `std_dev_ann_pct` | REAL | Annualised standard deviation of returns (volatility), %. |
| `max_drawdown_pct` | REAL | Largest peak-to-trough decline over the observed period, %. |
| `aum_crore` | INTEGER | Assets Under Management for this fund, in INR crore. |
| `expense_ratio_pct` | REAL | Annual expense ratio, % (denormalised copy). |
| `morningstar_rating` | INTEGER | Morningstar star rating (1–5). |
| `risk_grade` | TEXT | Qualitative risk grade, e.g. "Moderate", "High". |

---

## fact_aum

**Grain:** One row per (fund house, snapshot date) — typically quarter-end.
**Source:** `03_aum_by_fund_house.csv`
**Primary key:** `aum_id` (surrogate, autoincrement)
**Foreign keys:** `date` → `dim_date.date`

| Column | Type | Business Definition |
|---|---|---|
| `aum_id` | INTEGER (PK) | Surrogate key. |
| `date` | TEXT (FK) | Snapshot date (typically a fiscal quarter-end). |
| `fund_house` | TEXT | AMC name. |
| `aum_lakh_crore` | REAL | Total AUM for the fund house, in INR lakh-crore. |
| `aum_crore` | INTEGER | Total AUM for the fund house, in INR crore (same value, different unit). |
| `num_schemes` | INTEGER | Number of schemes the fund house had live on this date. |

---

## fact_portfolio

**Grain:** One row per (fund, stock holding, portfolio date).
**Source:** `09_portfolio_holdings.csv`
**Primary key:** `holding_id` (surrogate, autoincrement)
**Foreign keys:** `amfi_code` → `dim_fund.amfi_code`; `portfolio_date` → `dim_date.date`

| Column | Type | Business Definition |
|---|---|---|
| `holding_id` | INTEGER (PK) | Surrogate key. |
| `amfi_code` | INTEGER (FK) | Fund that holds this stock. |
| `stock_symbol` | TEXT | NSE/BSE ticker symbol of the held stock. |
| `stock_name` | TEXT | Full company name. |
| `sector` | TEXT | GICS-style sector classification, e.g. "Banking", "IT", "Pharma". |
| `weight_pct` | REAL | This holding's weight as a percentage of the fund's total portfolio. |
| `market_value_cr` | REAL | Market value of this holding, in INR crore. |
| `current_price_inr` | REAL | Current market price per share, INR. |
| `portfolio_date` | TEXT (FK) | Date this portfolio snapshot (disclosure) was taken. |

---

## fact_sip_industry

**Grain:** One row per calendar month (industry-wide SIP + folio metrics).
**Source:** `04_monthly_sip_inflows.csv` **LEFT JOIN** `06_industry_folio_count.csv` on `month`.
**Primary key:** `sip_id` (surrogate, autoincrement)
**Foreign keys:** `month_date` → `dim_date.date`

> **Known data characteristics (expected, not defects):**
> - `04_monthly_sip_inflows.csv` reports monthly (48 rows); `06_industry_folio_count.csv` reports less frequently (21 rows, roughly quarterly with some irregular gaps). The LEFT JOIN means `total_folios_crore` and related folio columns are **intentionally NULL** for months without a folio-count reading.
> - `yoy_growth_pct` is **intentionally NULL for the first 12 months** (Jan–Dec 2022), since there is no prior-year data to compute year-over-year growth against.

| Column | Type | Business Definition |
|---|---|---|
| `sip_id` | INTEGER (PK) | Surrogate key. |
| `month` | TEXT | Month in `YYYY-MM` format. |
| `month_date` | TEXT (FK) | First calendar day of the month, used to join to `dim_date`. |
| `sip_inflow_crore` | INTEGER | Total industry-wide SIP inflow for the month, INR crore. |
| `active_sip_accounts_crore` | REAL | Number of active SIP accounts industry-wide, in crore. |
| `new_sip_accounts_lakh` | REAL | New SIP accounts registered this month, in lakh. |
| `sip_aum_lakh_crore` | REAL | Total AUM attributable to SIPs, in lakh-crore. |
| `yoy_growth_pct` | REAL | Year-over-year growth in SIP inflow, %. NULL for the first 12 months (no prior-year base). |
| `total_folios_crore` | REAL | Total industry folio count, in crore. NULL for non-reporting months. |
| `equity_folios_crore` | REAL | Equity-scheme folio count, in crore. NULL for non-reporting months. |
| `debt_folios_crore` | REAL | Debt-scheme folio count, in crore. NULL for non-reporting months. |
| `hybrid_folios_crore` | REAL | Hybrid-scheme folio count, in crore. NULL for non-reporting months. |
| `others_folios_crore` | REAL | Other-scheme-type folio count, in crore. NULL for non-reporting months. |

---

## fact_category_inflows

**Grain:** One row per (month, fund category).
**Source:** `05_category_inflows.csv`
**Primary key:** `inflow_id` (surrogate, autoincrement)
**Foreign keys:** `month_date` → `dim_date.date`

| Column | Type | Business Definition |
|---|---|---|
| `inflow_id` | INTEGER (PK) | Surrogate key. |
| `month` | TEXT | Month in `YYYY-MM` format. |
| `month_date` | TEXT (FK) | First calendar day of the month, used to join to `dim_date`. |
| `category` | TEXT | Fund category, e.g. "Large Cap", "ELSS", "Liquid". |
| `net_inflow_crore` | REAL | Net inflow (inflow minus outflow) into this category for the month, INR crore. Can be negative (net outflow). |

---

## fact_benchmark

**Grain:** One row per (index, calendar day).
**Source:** `10_benchmark_indices.csv`
**Primary key:** `benchmark_id` (surrogate, autoincrement)
**Foreign keys:** `date` → `dim_date.date`

| Column | Type | Business Definition |
|---|---|---|
| `benchmark_id` | INTEGER (PK) | Surrogate key. |
| `date` | TEXT (FK) | Trading date. |
| `index_name` | TEXT | Benchmark index name, e.g. `NIFTY50`, `NIFTY100`, `NIFTY_MIDCAP150`, `BSE_SMALLCAP`, `NIFTY500`, `CRISIL_LIQUID`, `CRISIL_GILT`. |
| `close_value` | REAL | Closing value of the index on this date. Used as the basis for Alpha/Beta OLS regression and CAGR comparison against fund returns. |

---

## Cross-cutting notes

- **Referential integrity:** All fact tables enforce foreign keys against `dim_fund` and/or `dim_date` via `PRAGMA foreign_keys = ON`. Row-count and orphan checks are run automatically by `create_database.py` after every load.
- **Flag-don't-drop:** Wherever a source column could contain bad data (see `fact_transactions`), quality issues are captured as boolean flag columns rather than silently dropping rows, so no data is lost and analysts can choose their own inclusion/exclusion criteria.
- **Units:** AUM figures appear in multiple units across source files (`aum_crore` vs `aum_lakh_crore`) — both are preserved as-is from source rather than being unified, to avoid introducing conversion errors; 1 lakh crore = 100,000 crore.
- **City tiers (T30/B30):** AMFI classification distinguishing India's top 30 cities by mutual fund AUM (T30) from all other locations (B30), used industry-wide to track financial-inclusion / geographic penetration of MF investing.