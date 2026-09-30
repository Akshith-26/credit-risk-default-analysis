-- 06_default_by_year.sql
SELECT
    EXTRACT(YEAR FROM issue_date)              AS issue_year,
    COUNT(*)                                   AS loans,
    SUM(loan_amnt)                             AS volume,
    ROUND(100.0 * AVG(is_default), 2)          AS default_rate_pct,
    ROUND(AVG(int_rate), 2)                    AS avg_int_rate_pct
FROM loans
WHERE issue_date IS NOT NULL
GROUP BY 1
ORDER BY 1;
