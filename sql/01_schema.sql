-- =====================================================================
-- Credit Risk & Loan Portfolio Analysis (LendingClub 2007-2011 loans)
-- 01_schema.sql — database schema
--
-- Standard SQL; runs in SQLite and PostgreSQL as written.
--
--   states 1──< borrowers 1──1 loans >──1 loan_status_map
--                               loans 1──1 loan_performance
-- Snapshot date of balances and statuses: 2013-08-17
-- =====================================================================

DROP TABLE IF EXISTS loan_performance;
DROP TABLE IF EXISTS loans;
DROP TABLE IF EXISTS borrowers;
DROP TABLE IF EXISTS loan_status_map;
DROP TABLE IF EXISTS states;

CREATE TABLE states (
    state       CHAR(2) PRIMARY KEY,
    state_name  VARCHAR(30) NOT NULL,
    region      VARCHAR(10) NOT NULL          -- US Census region
);

CREATE TABLE loan_status_map (
    loan_status    VARCHAR(30) PRIMARY KEY,   -- LendingClub status
    status_group   VARCHAR(30) NOT NULL,      -- Closed - repaid / Active - current / Active - delinquent / Defaulted
    is_active      INTEGER NOT NULL,          -- still has a balance at the snapshot
    is_delinquent  INTEGER NOT NULL,          -- active and behind on payments (1-120 days)
    is_default     INTEGER NOT NULL,          -- Charged Off or Default
    days_past_due  VARCHAR(15),
    sort_order     INTEGER
);

CREATE TABLE borrowers (
    member_id             INTEGER PRIMARY KEY,
    emp_length_years      INTEGER,            -- 0 = under 1 year, 10 = 10+ years, NULL = unknown
    home_ownership        VARCHAR(10),
    annual_inc            DECIMAL(12,2),
    income_verified       INTEGER,
    state                 CHAR(2) REFERENCES states(state),
    dti                   DECIMAL(6,2),       -- debt-to-income ratio, %
    fico_score            DECIMAL(5,1),       -- midpoint of FICO range at application
    delinq_2yrs           INTEGER,            -- 30+ day delinquencies in the 2 years before applying
    inq_last_6mths        INTEGER,            -- credit inquiries in the last 6 months
    open_acc              INTEGER,
    pub_rec               INTEGER,            -- derogatory public records
    pub_rec_bankruptcies  INTEGER,
    revol_bal             DECIMAL(12,2),
    revol_util            DECIMAL(6,4),       -- revolving credit used / limit
    total_acc             INTEGER,
    credit_history_years  DECIMAL(5,1)
);

CREATE TABLE loans (
    loan_id              INTEGER PRIMARY KEY,
    member_id            INTEGER NOT NULL REFERENCES borrowers(member_id),
    issue_date           DATE NOT NULL,
    funded_amnt          DECIMAL(12,2) NOT NULL,   -- loan value used in all analysis
    loan_amnt            DECIMAL(12,2),            -- amount requested
    term_months          INTEGER NOT NULL,         -- 36 or 60
    int_rate             DECIMAL(6,4) NOT NULL,    -- 0.1099 = 10.99%
    installment          DECIMAL(10,2),
    grade                CHAR(1) NOT NULL,         -- LendingClub risk grade A (best) - G
    sub_grade            CHAR(2),
    purpose              VARCHAR(30),              -- loan type
    loan_status          VARCHAR(30) NOT NULL REFERENCES loan_status_map(loan_status),
    meets_credit_policy  INTEGER NOT NULL,
    pymnt_plan           INTEGER
);

CREATE TABLE loan_performance (
    loan_id             INTEGER PRIMARY KEY REFERENCES loans(loan_id),
    total_pymnt         DECIMAL(12,2),        -- all payments received
    total_rec_prncp     DECIMAL(12,2),        -- principal repaid
    total_rec_int       DECIMAL(12,2),        -- interest received
    total_rec_late_fee  DECIMAL(10,2),        -- late fees received (> 0 = paid late at least once)
    out_prncp           DECIMAL(12,2),        -- principal still outstanding at the snapshot
    last_payment_date   DATE,
    next_payment_date   DATE,
    snapshot_date       DATE,
    principal_lost      DECIMAL(12,2)         -- charged off: funded - principal repaid
);

CREATE INDEX idx_loans_status ON loans(loan_status);
CREATE INDEX idx_loans_grade  ON loans(grade);
CREATE INDEX idx_loans_issue  ON loans(issue_date);
CREATE INDEX idx_borr_state   ON borrowers(state);
