-- =====================================================================
-- 02_views.sql — one analysis-ready row per loan, with risk flags and
-- the segment bands used throughout SQL, Python, Excel and Power BI.
--
-- Definitions
--   Default        : status Charged Off or Default
--   Delinquent     : active loan In Grace Period or Late (16-30 / 31-120 days)
--   At-risk value  : principal still outstanding on delinquent or defaulted loans
--   Principal lost : charged-off loans, funded amount minus principal repaid
-- =====================================================================

DROP VIEW IF EXISTS vw_loans;
CREATE VIEW vw_loans AS
SELECT
    l.loan_id, l.member_id, l.issue_date,
    CAST(strftime('%Y', l.issue_date) AS INTEGER)                            AS issue_year,
    strftime('%Y', l.issue_date) || '-Q' || ((CAST(strftime('%m', l.issue_date) AS INTEGER) + 2) / 3) AS issue_quarter,
    l.funded_amnt, l.loan_amnt, l.term_months, l.int_rate, l.installment,
    l.grade, l.sub_grade, l.purpose AS loan_type, l.meets_credit_policy,
    l.loan_status, m.status_group, m.is_active, m.is_delinquent, m.is_default, m.days_past_due,
    b.emp_length_years, b.home_ownership, b.annual_inc, b.income_verified, b.dti, b.fico_score,
    b.delinq_2yrs, b.inq_last_6mths, b.pub_rec, b.pub_rec_bankruptcies, b.revol_util, b.credit_history_years,
    b.state, s.state_name, s.region,
    p.total_pymnt, p.total_rec_prncp, p.total_rec_int, p.total_rec_late_fee, p.out_prncp, p.principal_lost, p.last_payment_date,
    CASE WHEN m.is_delinquent = 1 OR l.loan_status = 'Default' THEN p.out_prncp ELSE 0 END AS at_risk_amount,
    CASE WHEN p.total_rec_late_fee > 0 THEN 1 ELSE 0 END                     AS ever_paid_late,
    -- segment bands -------------------------------------------------------
    CASE WHEN b.fico_score < 660 THEN '1. <660'      WHEN b.fico_score < 680 THEN '2. 660-679'
         WHEN b.fico_score < 700 THEN '3. 680-699'   WHEN b.fico_score < 720 THEN '4. 700-719'
         WHEN b.fico_score < 740 THEN '5. 720-739'   WHEN b.fico_score < 760 THEN '6. 740-759'
         ELSE '7. 760+' END                                                   AS fico_band,
    CASE WHEN b.annual_inc IS NULL THEN '9. Unknown'
         WHEN b.annual_inc < 30000  THEN '1. <$30K'   WHEN b.annual_inc < 50000  THEN '2. $30-50K'
         WHEN b.annual_inc < 75000  THEN '3. $50-75K' WHEN b.annual_inc < 100000 THEN '4. $75-100K'
         WHEN b.annual_inc < 150000 THEN '5. $100-150K' ELSE '6. $150K+' END  AS income_band,
    CASE WHEN b.dti < 5 THEN '1. <5%'   WHEN b.dti < 10 THEN '2. 5-10%' WHEN b.dti < 15 THEN '3. 10-15%'
         WHEN b.dti < 20 THEN '4. 15-20%' WHEN b.dti < 25 THEN '5. 20-25%' ELSE '6. 25%+' END AS dti_band,
    CASE WHEN l.int_rate < 0.08 THEN '1. <8%'    WHEN l.int_rate < 0.11 THEN '2. 8-11%'
         WHEN l.int_rate < 0.14 THEN '3. 11-14%' WHEN l.int_rate < 0.17 THEN '4. 14-17%'
         WHEN l.int_rate < 0.20 THEN '5. 17-20%' ELSE '6. 20%+' END           AS rate_band,
    CASE WHEN l.funded_amnt < 5000 THEN '1. <$5K'     WHEN l.funded_amnt < 10000 THEN '2. $5-10K'
         WHEN l.funded_amnt < 15000 THEN '3. $10-15K' WHEN l.funded_amnt < 25000 THEN '4. $15-25K'
         ELSE '5. $25K+' END                                                  AS amount_band,
    CASE WHEN b.emp_length_years IS NULL THEN '6. Unknown' WHEN b.emp_length_years < 1 THEN '1. <1 yr'
         WHEN b.emp_length_years <= 3 THEN '2. 1-3 yrs'    WHEN b.emp_length_years <= 6 THEN '3. 4-6 yrs'
         WHEN b.emp_length_years <= 9 THEN '4. 7-9 yrs'    ELSE '5. 10+ yrs' END AS emp_band
FROM loans l
JOIN loan_status_map m  ON m.loan_status = l.loan_status
JOIN borrowers b        ON b.member_id   = l.member_id
JOIN states s           ON s.state       = b.state
JOIN loan_performance p ON p.loan_id     = l.loan_id;
