-- 03_default_by_grade.sql
-- Is the lender's own grading system ranking risk correctly?
SELECT
    grade,
    COUNT(*)                                   AS loans,
    ROUND(100.0 * AVG(is_default), 2)          AS default_rate_pct,
    ROUND(AVG(int_rate), 2)                    AS avg_int_rate_pct,
    ROUND(AVG(fico), 0)                        AS avg_fico
FROM loans
GROUP BY grade
ORDER BY grade;
