-- ============================================================================
-- queries.sql
-- Bluestock MF Analytics Capstone — Day 2 Analytical Queries
--
-- Run against: bluestock_mf.db
-- All queries tested against the actual loaded schema (dim_fund, dim_date,
-- fact_nav, fact_transactions, fact_performance, fact_aum, fact_portfolio,
-- fact_sip_industry, fact_category_inflows, fact_benchmark).
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Q1. Top 5 funds by current AUM (from fact_performance snapshot)
-- ----------------------------------------------------------------------------
SELECT
    p.amfi_code,
    f.scheme_name,
    f.fund_house,
    p.aum_crore,
    p.category
FROM fact_performance p
JOIN dim_fund f ON f.amfi_code = p.amfi_code
ORDER BY p.aum_crore DESC
LIMIT 5;


-- ----------------------------------------------------------------------------
-- Q2. Average NAV per month, per fund (trend of monthly average NAV)
-- ----------------------------------------------------------------------------
SELECT
    n.amfi_code,
    f.scheme_name,
    strftime('%Y-%m', n.date) AS nav_month,
    ROUND(AVG(n.nav), 4) AS avg_nav
FROM fact_nav n
JOIN dim_fund f ON f.amfi_code = n.amfi_code
GROUP BY n.amfi_code, nav_month
ORDER BY n.amfi_code, nav_month;


-- ----------------------------------------------------------------------------
-- Q3. SIP inflow YoY growth trend, industry-wide, by month
-- ----------------------------------------------------------------------------
SELECT
    month,
    sip_inflow_crore,
    sip_aum_lakh_crore,
    yoy_growth_pct
FROM fact_sip_industry
WHERE yoy_growth_pct IS NOT NULL
ORDER BY month;


-- ----------------------------------------------------------------------------
-- Q4. Transaction volume and value by state
-- ----------------------------------------------------------------------------
SELECT
    state,
    COUNT(*) AS transaction_count,
    SUM(amount_inr) AS total_amount_inr,
    ROUND(AVG(amount_inr), 2) AS avg_amount_inr
FROM fact_transactions
GROUP BY state
ORDER BY total_amount_inr DESC;


-- ----------------------------------------------------------------------------
-- Q5. Funds with expense ratio below 1%
-- ----------------------------------------------------------------------------
SELECT
    amfi_code,
    scheme_name,
    fund_house,
    category,
    expense_ratio_pct
FROM dim_fund
WHERE expense_ratio_pct < 1.0
ORDER BY expense_ratio_pct ASC;


-- ----------------------------------------------------------------------------
-- Q6. Average 3-year return and Sharpe ratio by fund category
-- ----------------------------------------------------------------------------
SELECT
    category,
    COUNT(*) AS fund_count,
    ROUND(AVG(return_3yr_pct), 2) AS avg_return_3yr_pct,
    ROUND(AVG(sharpe_ratio), 3) AS avg_sharpe_ratio,
    ROUND(AVG(std_dev_ann_pct), 2) AS avg_volatility_pct
FROM fact_performance
GROUP BY category
ORDER BY avg_sharpe_ratio DESC;


-- ----------------------------------------------------------------------------
-- Q7. Top 10 funds by risk-adjusted return (Sharpe ratio)
-- ----------------------------------------------------------------------------
SELECT
    p.amfi_code,
    f.scheme_name,
    f.fund_house,
    p.category,
    p.sharpe_ratio,
    p.sortino_ratio,
    p.return_3yr_pct
FROM fact_performance p
JOIN dim_fund f ON f.amfi_code = p.amfi_code
ORDER BY p.sharpe_ratio DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Q8. KYC status breakdown by transaction type
-- ----------------------------------------------------------------------------
SELECT
    transaction_type,
    kyc_status,
    COUNT(*) AS transaction_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY transaction_type), 2) AS pct_of_type
FROM fact_transactions
GROUP BY transaction_type, kyc_status
ORDER BY transaction_type, kyc_status;


-- ----------------------------------------------------------------------------
-- Q9. Sector concentration across portfolio holdings (by total market value)
-- ----------------------------------------------------------------------------
SELECT
    sector,
    COUNT(DISTINCT amfi_code) AS funds_holding_sector,
    ROUND(SUM(market_value_cr), 2) AS total_market_value_cr,
    ROUND(AVG(weight_pct), 2) AS avg_weight_pct
FROM fact_portfolio
GROUP BY sector
ORDER BY total_market_value_cr DESC;


-- ----------------------------------------------------------------------------
-- Q10. Fund-house AUM growth: latest quarter vs. earliest quarter on record
-- ----------------------------------------------------------------------------
WITH first_last AS (
    SELECT
        fund_house,
        MIN(date) AS first_date,
        MAX(date) AS last_date
    FROM fact_aum
    GROUP BY fund_house
)
SELECT
    fl.fund_house,
    first_aum.aum_crore AS aum_crore_first,
    fl.first_date,
    last_aum.aum_crore AS aum_crore_latest,
    fl.last_date,
    ROUND(
        100.0 * (last_aum.aum_crore - first_aum.aum_crore) / first_aum.aum_crore, 2
    ) AS growth_pct
FROM first_last fl
JOIN fact_aum first_aum
    ON first_aum.fund_house = fl.fund_house AND first_aum.date = fl.first_date
JOIN fact_aum last_aum
    ON last_aum.fund_house = fl.fund_house AND last_aum.date = fl.last_date
ORDER BY growth_pct DESC;