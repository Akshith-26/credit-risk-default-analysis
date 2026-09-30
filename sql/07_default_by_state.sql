-- 07_default_by_state.sql
-- States ranked by default rate (window function), minimum volume to avoid noise.
SELECT
    addr_state,
    loans,
    default_rate_pct,
    RANK() OVER (ORDER BY default_rate_pct DESC)   AS risk_rank
FROM (
    SELECT addr_state,
           COUNT(*)                                AS loans,
           ROUND(100.0 * AVG(is_default), 2)       AS default_rate_pct
    FROM loans
    GROUP BY addr_state
    HAVING COUNT(*) >= 1000
) s
ORDER BY risk_rank;
