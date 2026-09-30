-- 05_default_by_income_fico.sql
-- Default rate across income band x FICO band (a risk matrix).
SELECT
    CASE WHEN annual_inc < 40000  THEN '1: <40k'
         WHEN annual_inc < 70000  THEN '2: 40-70k'
         WHEN annual_inc < 100000 THEN '3: 70-100k'
         ELSE '4: 100k+' END                   AS income_band,
    CASE WHEN fico < 670 THEN '1: <670'
         WHEN fico < 700 THEN '2: 670-699'
         WHEN fico < 740 THEN '3: 700-739'
         ELSE '4: 740+' END                    AS fico_band,
    COUNT(*)                                   AS loans,
    ROUND(100.0 * AVG(is_default), 2)          AS default_rate_pct
FROM loans
GROUP BY 1, 2
ORDER BY 1, 2;
