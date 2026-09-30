-- 04_default_by_purpose.sql
SELECT
    purpose,
    COUNT(*)                                   AS loans,
    SUM(loan_amnt)                             AS volume,
    ROUND(100.0 * AVG(is_default), 2)          AS default_rate_pct
FROM loans
GROUP BY purpose
HAVING COUNT(*) >= 1000
ORDER BY default_rate_pct DESC;
