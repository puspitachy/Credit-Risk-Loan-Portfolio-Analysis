-- =====================================================================
-- Credit Risk & Loan Portfolio Analysis
-- 03_analysis_queries.sql — business questions answered in SQL
--
-- Dialect: SQLite (database: data/credit_risk.db). Run 01_schema.sql,
-- load the CSVs, then 02_views.sql. PostgreSQL: replace strftime() with
-- to_char() / EXTRACT(); everything else is standard.
-- Each query starts with "-- Qnn:"; scripts/02_build_database.py runs them
-- and saves the results to sql/query_results/.
--
-- Default rate   = defaulted loans / all loans (count)
-- Delinquency    = delinquent loans / active loans
-- At-risk value  = outstanding principal on delinquent + defaulted loans
-- =====================================================================


-- Q01: Portfolio KPIs (executive summary)
SELECT
    COUNT(*)                                                        AS number_of_loans,
    ROUND(SUM(funded_amnt), 0)                                      AS total_loan_value,
    ROUND(AVG(funded_amnt), 0)                                      AS avg_loan,
    ROUND(100.0 * AVG(is_default), 2)                               AS default_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN is_default = 1 THEN funded_amnt END) / SUM(funded_amnt), 2) AS default_rate_by_value_pct,
    SUM(is_active)                                                  AS active_loans,
    ROUND(100.0 * SUM(is_delinquent) / SUM(is_active), 2)           AS delinquency_rate_pct,
    ROUND(100.0 * AVG(int_rate), 2)                                 AS avg_interest_rate_pct,
    ROUND(100.0 * SUM(int_rate * funded_amnt) / SUM(funded_amnt), 2) AS weighted_avg_rate_pct,
    ROUND(SUM(out_prncp), 0)                                        AS outstanding_balance,
    ROUND(SUM(at_risk_amount), 0)                                   AS at_risk_loan_value,
    ROUND(100.0 * SUM(at_risk_amount) / SUM(out_prncp), 2)          AS at_risk_share_of_outstanding_pct,
    ROUND(SUM(principal_lost), 0)                                   AS principal_lost_to_charge_offs
FROM vw_loans;


-- Q02: Loan status — where is every loan today?
SELECT
    m.sort_order, v.loan_status, v.status_group, v.days_past_due,
    COUNT(*)                                             AS loans,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)   AS share_of_loans_pct,
    ROUND(SUM(v.funded_amnt), 0)                         AS funded,
    ROUND(SUM(v.out_prncp), 0)                           AS outstanding
FROM vw_loans v
JOIN loan_status_map m ON m.loan_status = v.loan_status
GROUP BY m.sort_order, v.loan_status, v.status_group, v.days_past_due
ORDER BY m.sort_order;


-- Q03: Loan amounts and interest rates by grade
SELECT
    grade,
    COUNT(*)                                   AS loans,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct,
    ROUND(AVG(funded_amnt), 0)                 AS avg_amount,
    ROUND(SUM(funded_amnt), 0)                 AS total_amount,
    ROUND(100.0 * MIN(int_rate), 2)            AS min_rate_pct,
    ROUND(100.0 * AVG(int_rate), 2)            AS avg_rate_pct,
    ROUND(100.0 * MAX(int_rate), 2)            AS max_rate_pct
FROM vw_loans
GROUP BY grade
ORDER BY grade;


-- Q04: Default rate by grade — does LendingClub's grade rank risk correctly?
SELECT
    grade,
    COUNT(*)                                          AS loans,
    SUM(is_default)                                   AS defaults,
    ROUND(100.0 * AVG(is_default), 2)                 AS default_rate_pct,
    ROUND(100.0 * AVG(int_rate), 2)                   AS avg_rate_pct,
    ROUND(SUM(principal_lost), 0)                     AS principal_lost,
    ROUND(SUM(at_risk_amount), 0)                     AS at_risk_value
FROM vw_loans
GROUP BY grade
ORDER BY grade;


-- Q05: Is a higher interest rate associated with higher default?
SELECT
    rate_band,
    COUNT(*)                                          AS loans,
    ROUND(100.0 * AVG(int_rate), 2)                   AS avg_rate_pct,
    ROUND(100.0 * AVG(is_default), 2)                 AS default_rate_pct,
    -- interest earned per $100 lent vs principal lost per $100 lent
    ROUND(100.0 * SUM(total_rec_int) / SUM(funded_amnt), 2)   AS interest_received_per_100,
    ROUND(100.0 * SUM(principal_lost) / SUM(funded_amnt), 2)  AS principal_lost_per_100
FROM vw_loans
GROUP BY rate_band
ORDER BY rate_band;


-- Q06: Credit score vs default
SELECT
    fico_band,
    COUNT(*)                                  AS loans,
    ROUND(AVG(fico_score), 0)                 AS avg_fico,
    ROUND(100.0 * AVG(is_default), 2)         AS default_rate_pct,
    ROUND(100.0 * AVG(int_rate), 2)           AS avg_rate_pct
FROM vw_loans
GROUP BY fico_band
ORDER BY fico_band;


-- Q07: Income vs default
SELECT
    income_band,
    COUNT(*)                                  AS loans,
    ROUND(AVG(funded_amnt), 0)                AS avg_loan,
    ROUND(100.0 * AVG(is_default), 2)         AS default_rate_pct,
    ROUND(100.0 * AVG(1.0 * funded_amnt / NULLIF(annual_inc, 0)), 1) AS avg_loan_to_income_pct
FROM vw_loans
GROUP BY income_band
ORDER BY income_band;


-- Q08: Debt-to-income vs default
SELECT dti_band, COUNT(*) AS loans, ROUND(100.0 * AVG(is_default), 2) AS default_rate_pct
FROM vw_loans GROUP BY dti_band ORDER BY dti_band;


-- Q09: Loan type (purpose) — which loan types carry the greatest risk?
SELECT
    loan_type,
    COUNT(*)                                                    AS loans,
    ROUND(SUM(funded_amnt), 0)                                  AS total_amount,
    ROUND(100.0 * SUM(funded_amnt) / SUM(SUM(funded_amnt)) OVER (), 1) AS share_of_value_pct,
    ROUND(100.0 * AVG(is_default), 2)                           AS default_rate_pct,
    ROUND(SUM(principal_lost), 0)                               AS principal_lost,
    ROUND(SUM(at_risk_amount), 0)                               AS at_risk_value,
    RANK() OVER (ORDER BY AVG(is_default) DESC)                 AS risk_rank
FROM vw_loans
GROUP BY loan_type
ORDER BY default_rate_pct DESC;


-- Q10: Term (tenure) — 36 vs 60 months
SELECT
    term_months,
    COUNT(*)                                  AS loans,
    ROUND(AVG(funded_amnt), 0)                AS avg_loan,
    ROUND(100.0 * AVG(int_rate), 2)           AS avg_rate_pct,
    ROUND(100.0 * AVG(is_default), 2)         AS default_rate_pct,
    ROUND(100.0 * SUM(is_delinquent) / NULLIF(SUM(is_active), 0), 2) AS delinquency_rate_pct,
    ROUND(SUM(out_prncp), 0)                  AS outstanding
FROM vw_loans
GROUP BY term_months;


-- Q11: Customer profile — home ownership, employment length, income verification
SELECT 'Home ownership' AS dimension, home_ownership AS segment, COUNT(*) AS loans,
       ROUND(100.0 * AVG(is_default), 2) AS default_rate_pct
FROM vw_loans GROUP BY home_ownership
UNION ALL
SELECT 'Employment length', emp_band, COUNT(*), ROUND(100.0 * AVG(is_default), 2)
FROM vw_loans GROUP BY emp_band
UNION ALL
SELECT 'Income verified', CASE WHEN income_verified = 1 THEN 'Verified' ELSE 'Not verified' END,
       COUNT(*), ROUND(100.0 * AVG(is_default), 2)
FROM vw_loans GROUP BY income_verified
UNION ALL
SELECT 'Recent credit inquiries', CASE WHEN inq_last_6mths IS NULL THEN 'Unknown' WHEN inq_last_6mths >= 3 THEN '3+' ELSE CAST(inq_last_6mths AS TEXT) END,
       COUNT(*), ROUND(100.0 * AVG(is_default), 2)
FROM vw_loans GROUP BY CASE WHEN inq_last_6mths IS NULL THEN 'Unknown' WHEN inq_last_6mths >= 3 THEN '3+' ELSE CAST(inq_last_6mths AS TEXT) END
UNION ALL
SELECT 'Meets current credit policy', CASE WHEN meets_credit_policy = 1 THEN 'Yes' ELSE 'No' END,
       COUNT(*), ROUND(100.0 * AVG(is_default), 2)
FROM vw_loans GROUP BY meets_credit_policy
ORDER BY 1, 2;


-- Q12: Default trend over time — by issue year (vintage)
SELECT
    issue_year,
    COUNT(*)                                          AS loans,
    ROUND(SUM(funded_amnt), 0)                        AS funded,
    ROUND(100.0 * AVG(is_default), 2)                 AS default_rate_pct,
    ROUND(100.0 * AVG(is_active), 1)                  AS still_active_pct,
    ROUND(100.0 * AVG(int_rate), 2)                   AS avg_rate_pct,
    ROUND(AVG(fico_score), 0)                         AS avg_fico
FROM vw_loans
GROUP BY issue_year
ORDER BY issue_year;


-- Q13: Default trend by quarter, with a 4-quarter moving average
WITH q AS (
    SELECT issue_quarter, COUNT(*) AS loans, AVG(is_default) AS dr
    FROM vw_loans GROUP BY issue_quarter
)
SELECT
    issue_quarter, loans,
    ROUND(100.0 * dr, 2)                                                            AS default_rate_pct,
    ROUND(100.0 * AVG(dr) OVER (ORDER BY issue_quarter ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 2) AS moving_avg_4q_pct
FROM q
ORDER BY issue_quarter;


-- Q14: Geographic risk — regions
SELECT
    region,
    COUNT(*)                                  AS loans,
    ROUND(SUM(funded_amnt), 0)                AS funded,
    ROUND(100.0 * AVG(is_default), 2)         AS default_rate_pct,
    ROUND(SUM(at_risk_amount), 0)             AS at_risk_value
FROM vw_loans
GROUP BY region
ORDER BY default_rate_pct DESC;


-- Q15: Geographic risk — states with at least 500 loans, ranked by default rate
SELECT
    state, state_name, region,
    COUNT(*)                                            AS loans,
    ROUND(100.0 * AVG(is_default), 2)                   AS default_rate_pct,
    ROUND(SUM(at_risk_amount), 0)                       AS at_risk_value,
    RANK() OVER (ORDER BY AVG(is_default) DESC)         AS risk_rank
FROM vw_loans
GROUP BY state, state_name, region
HAVING COUNT(*) >= 500
ORDER BY default_rate_pct DESC;


-- Q16: Delinquency — the active book by days past due
SELECT
    loan_status, days_past_due,
    COUNT(*)                                                AS loans,
    ROUND(SUM(out_prncp), 0)                                AS outstanding,
    ROUND(100.0 * SUM(out_prncp) / (SELECT SUM(out_prncp) FROM vw_loans), 2) AS share_of_outstanding_pct,
    ROUND(100.0 * AVG(int_rate), 2)                         AS avg_rate_pct
FROM vw_loans
WHERE is_active = 1
GROUP BY loan_status, days_past_due
ORDER BY MIN(CASE loan_status WHEN 'Current' THEN 1 WHEN 'In Grace Period' THEN 2
             WHEN 'Late (16-30 days)' THEN 3 WHEN 'Late (31-120 days)' THEN 4 ELSE 5 END);


-- Q17: Repayment trends — how much principal has come back, by vintage and status group
SELECT
    issue_year, status_group,
    COUNT(*)                                                      AS loans,
    ROUND(100.0 * SUM(total_rec_prncp) / SUM(funded_amnt), 1)     AS principal_repaid_pct,
    ROUND(100.0 * SUM(total_pymnt) / SUM(funded_amnt), 1)         AS cash_returned_pct,
    ROUND(100.0 * AVG(ever_paid_late), 1)                         AS paid_late_at_least_once_pct
FROM vw_loans
GROUP BY issue_year, status_group
ORDER BY issue_year, status_group;


-- Q18: High-risk segments — grade x term x home ownership (min. 300 loans), top 10 by default rate
SELECT
    grade, term_months, home_ownership,
    COUNT(*)                                     AS loans,
    ROUND(SUM(funded_amnt), 0)                   AS funded,
    ROUND(100.0 * AVG(is_default), 2)            AS default_rate_pct,
    ROUND(100.0 * AVG(int_rate), 2)              AS avg_rate_pct,
    ROUND(SUM(at_risk_amount), 0)                AS at_risk_value
FROM vw_loans
GROUP BY grade, term_months, home_ownership
HAVING COUNT(*) >= 300
ORDER BY default_rate_pct DESC
LIMIT 10;


-- Q19: Where does the at-risk money sit? (loan type x term)
SELECT
    loan_type, term_months,
    SUM(CASE WHEN at_risk_amount > 0 THEN 1 ELSE 0 END)           AS at_risk_loans,
    ROUND(SUM(at_risk_amount), 0)                                 AS at_risk_value,
    ROUND(100.0 * SUM(at_risk_amount) / (SELECT SUM(at_risk_amount) FROM vw_loans), 1) AS share_of_at_risk_pct,
    ROUND(100.0 * SUM(SUM(at_risk_amount)) OVER (ORDER BY SUM(at_risk_amount) DESC)
          / (SELECT SUM(at_risk_amount) FROM vw_loans), 1)          AS cumulative_share_pct
FROM vw_loans
GROUP BY loan_type, term_months
HAVING SUM(at_risk_amount) > 0
ORDER BY at_risk_value DESC
LIMIT 10;


-- Q20: Does pricing cover losses? Lifetime results by grade on MATURED loans
--      (36-month loans whose full term ended before the snapshot, i.e. issued on or
--       before 2010-08-17, so every loan's final outcome is known — no partial-life bias)
SELECT
    grade,
    COUNT(*)                                                                   AS matured_loans,
    ROUND(100.0 * AVG(is_default), 2)                                          AS lifetime_default_rate_pct,
    ROUND(100.0 * AVG(int_rate), 2)                                            AS avg_rate_pct,
    ROUND(100.0 * (SUM(total_pymnt) - SUM(funded_amnt)) / SUM(funded_amnt), 2) AS net_return_pct
FROM vw_loans
WHERE term_months = 36 AND issue_date <= '2010-08-17'
GROUP BY grade
ORDER BY grade;
