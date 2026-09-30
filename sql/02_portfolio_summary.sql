-- 02_portfolio_summary.sql
SELECT
    COUNT(*)                                   AS loans,
    SUM(loan_amnt)                             AS total_volume,
    ROUND(AVG(loan_amnt), 0)                   AS avg_loan,
    ROUND(100.0 * AVG(is_default), 2)          AS default_rate_pct,
    MIN(issue_date)                            AS first_issue,
    MAX(issue_date)                            AS last_issue
FROM loans;
