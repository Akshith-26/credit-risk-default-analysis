
CREATE OR REPLACE TABLE loans AS
SELECT
    id,
    TRY_CAST(loan_amnt AS DOUBLE)                                        AS loan_amnt,
    TRY_CAST(regexp_extract(term, '(\d+)', 1) AS INTEGER)                AS term_months,
    TRY_CAST(replace(int_rate, '%', '') AS DOUBLE)                       AS int_rate,
    TRY_CAST(installment AS DOUBLE)                                      AS installment,
    grade,
    sub_grade,
    CASE WHEN emp_length LIKE '<%' THEN 0
         ELSE TRY_CAST(regexp_extract(emp_length, '(\d+)', 1) AS INTEGER) END AS emp_years,
    home_ownership,
    TRY_CAST(annual_inc AS DOUBLE)                                       AS annual_inc,
    verification_status,
    CAST(try_strptime(issue_d, '%b-%Y') AS DATE)                         AS issue_date,
    loan_status,
    purpose,
    addr_state,
    TRY_CAST(dti AS DOUBLE)                                              AS dti,
    TRY_CAST(delinq_2yrs AS DOUBLE)                                      AS delinq_2yrs,
    (TRY_CAST(fico_range_low AS DOUBLE) + TRY_CAST(fico_range_high AS DOUBLE)) / 2 AS fico,
    TRY_CAST(open_acc AS DOUBLE)                                         AS open_acc,
    TRY_CAST(pub_rec AS DOUBLE)                                          AS pub_rec,
    TRY_CAST(replace(revol_util, '%', '') AS DOUBLE)                     AS revol_util,
    TRY_CAST(total_acc AS DOUBLE)                                        AS total_acc,
    CASE WHEN loan_status IN ('Charged Off', 'Default',
              'Does not meet the credit policy. Status:Charged Off') THEN 1 ELSE 0 END AS is_default
FROM loans_raw
WHERE loan_status IN ('Fully Paid', 'Charged Off', 'Default',
                      'Does not meet the credit policy. Status:Fully Paid',
                      'Does not meet the credit policy. Status:Charged Off')
  AND TRY_CAST(annual_inc AS DOUBLE) > 0
  AND TRY_CAST(loan_amnt AS DOUBLE) > 0;
