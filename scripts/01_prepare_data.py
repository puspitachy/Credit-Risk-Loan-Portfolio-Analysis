"""
01_prepare_data.py
Reads the original LendingClub file (data/source/LoanStats3a.csv, never modified),
checks and cleans it, and writes normalised, database-ready CSVs to data/clean/:

  loans.csv           one row per loan: terms, purpose, issue date, status
  borrowers.csv       one row per borrower at application: income, FICO, DTI, credit history
  loan_performance.csv  payments received and balance outstanding at the snapshot date
  loan_status_map.csv   raw LendingClub status -> clean status, status group and risk flags
  states.csv            US state -> name and Census region

Snapshot date: 17 Aug 2013 (latest payment date in the file is 16 Aug 2013).
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SRC, CLEAN = BASE / "data" / "source", BASE / "data" / "clean"
CLEAN.mkdir(parents=True, exist_ok=True)
SNAPSHOT = pd.Timestamp("2013-08-17")
log = []

def note(table, check, rows, action):
    log.append({"table": table, "check": check, "rows": int(rows), "action": action})
    print(f"[{table}] {check}: {rows:,} -> {action}")

src_file = SRC / "LoanStats3a.csv"
if not src_file.exists():                       # GitHub copy stores it compressed (GitHub's 25 MB upload limit)
    src_file = SRC / "LoanStats3a.csv.gz"
raw = pd.read_csv(src_file, skiprows=1, low_memory=False)   # line 1 is a prospectus note
note("source", "Rows loaded (first line is a text note, skipped)", len(raw), "42,535 loans, 102 columns")
empty = [c for c in raw.columns if raw[c].isna().all()]
note("source", "Columns that are completely empty", len(empty), "dropped (LendingClub added them for later years)")
raw = raw.drop(columns=empty)
note("source", "Duplicate loan IDs", raw.id.duplicated().sum(), "none found")

# ---------------------------------------------------------------- status mapping
raw["meets_credit_policy"] = (~raw.loan_status.str.startswith("Does not meet")).astype(int)
raw["loan_status_raw"] = raw.loan_status
raw["loan_status"] = raw.loan_status.str.replace("Does not meet the credit policy.  Status:", "", regex=False).str.strip()
note("loans", "Loans that did not meet LendingClub's current credit policy", (raw.meets_credit_policy == 0).sum(),
     "status prefix removed; kept and flagged in meets_credit_policy = 0")
status_map = pd.DataFrame([
    # status, group, is_active, is_delinquent, is_default, days_past_due, sort
    ("Fully Paid",          "Closed - repaid",   0, 0, 0, "0",       1),
    ("Current",             "Active - current",  1, 0, 0, "0",       2),
    ("In Grace Period",     "Active - delinquent", 1, 1, 0, "1-15",  3),
    ("Late (16-30 days)",   "Active - delinquent", 1, 1, 0, "16-30", 4),
    ("Late (31-120 days)",  "Active - delinquent", 1, 1, 0, "31-120", 5),
    ("Default",             "Defaulted",         1, 0, 1, "121+",    6),
    ("Charged Off",         "Defaulted",         0, 0, 1, "charged off", 7),
], columns=["loan_status", "status_group", "is_active", "is_delinquent", "is_default", "days_past_due", "sort_order"])
assert raw.loan_status.isin(status_map.loan_status).all()

# ---------------------------------------------------------------- type conversions
pct = lambda s: pd.to_numeric(s.astype(str).str.replace("%", "").str.strip(), errors="coerce") / 100
raw["int_rate"] = pct(raw.int_rate); raw["revol_util"] = pct(raw.revol_util)
note("loans", "Interest rate stored as text like ' 10.99%'", len(raw), "converted to a number (0.1099)")
raw["term_months"] = raw.term.str.extract(r"(\d+)").astype(int)
emp = raw.emp_length.replace({"< 1 year": "0", "10+ years": "10"}).str.extract(r"(\d+)")[0]
raw["emp_length_years"] = pd.to_numeric(emp, errors="coerce")
note("borrowers", "Employment length missing ('n/a')", raw.emp_length_years.isna().sum(),
     "left blank; grouped as 'Unknown' in analysis")
for c in ["issue_d", "last_pymnt_d", "next_pymnt_d", "earliest_cr_line"]:
    raw[c] = pd.to_datetime(raw[c], errors="coerce")
raw["credit_history_years"] = ((raw.issue_d - raw.earliest_cr_line).dt.days / 365.25).round(1)
raw["fico_score"] = (raw.fico_range_low + raw.fico_range_high) / 2
note("borrowers", "FICO given as a range (e.g. 735-739)", len(raw), "fico_score = midpoint of the range")
miss_inc = raw.annual_inc.isna().sum()
note("borrowers", "Missing annual income", miss_inc, "left blank (excluded from income analysis)")
hi_inc = (raw.annual_inc > 1_000_000).sum()
note("borrowers", "Annual income above $1M", hi_inc, "kept (self-reported); income bands cap at '$150K+'")
n_none = (raw.home_ownership == "NONE").sum()
raw["home_ownership"] = raw.home_ownership.replace({"NONE": "OTHER"})
note("borrowers", "Home ownership 'NONE'", n_none, "merged into 'OTHER'")
raw["purpose"] = raw.purpose.str.replace("_", " ").str.title()
note("loans", "Purpose codes like 'debt_consolidation'", raw.purpose.nunique(), "relabelled 'Debt Consolidation' etc.")
pol = (raw.funded_amnt < raw.loan_amnt).sum()
note("loans", "Funded amount lower than amount requested", pol, "kept - funded_amnt is used as the loan value")
note("borrowers", "Credit history before issue date could not be parsed", raw.credit_history_years.isna().sum(),
     "left blank")
# money columns: clip tiny negative balances caused by rounding
raw["out_prncp"] = raw.out_prncp.clip(lower=0)

# ---------------------------------------------------------------- build tables
loans = raw[["id", "member_id", "issue_d", "funded_amnt", "loan_amnt", "term_months", "int_rate", "installment",
             "grade", "sub_grade", "purpose", "loan_status", "meets_credit_policy", "pymnt_plan"]].rename(
    columns={"id": "loan_id", "issue_d": "issue_date"})
loans["pymnt_plan"] = (loans.pymnt_plan == "y").astype(int)

borrowers = raw[["member_id", "emp_length_years", "home_ownership", "annual_inc", "is_inc_v", "addr_state", "dti",
                 "fico_score", "delinq_2yrs", "inq_last_6mths", "open_acc", "pub_rec", "pub_rec_bankruptcies",
                 "revol_bal", "revol_util", "total_acc", "credit_history_years"]].rename(
    columns={"is_inc_v": "income_verified", "addr_state": "state"})
borrowers["income_verified"] = borrowers.income_verified.astype(int)
note("borrowers", "Borrowers with more than one loan", borrowers.member_id.duplicated().sum(),
     "none - one loan per borrower")

perf = raw[["id", "total_pymnt", "total_rec_prncp", "total_rec_int", "total_rec_late_fee", "out_prncp",
            "last_pymnt_d", "next_pymnt_d"]].rename(columns={"id": "loan_id", "last_pymnt_d": "last_payment_date",
                                                           "next_pymnt_d": "next_payment_date"})
perf["snapshot_date"] = SNAPSHOT
perf["principal_lost"] = np.where(raw.loan_status == "Charged Off",
                                  (raw.funded_amnt - raw.total_rec_prncp).clip(lower=0), 0).round(2)
note("loan_performance", "Charged-off loans", (raw.loan_status == "Charged Off").sum(),
     "principal_lost = funded amount - principal repaid (recoveries not in this file)")

REGION = {**{s: "Northeast" for s in "CT ME MA NH RI VT NJ NY PA".split()},
          **{s: "Midwest" for s in "IL IN MI OH WI IA KS MN MO NE ND SD".split()},
          **{s: "South" for s in "DE FL GA MD NC SC VA DC WV AL KY MS TN AR LA OK TX".split()},
          **{s: "West" for s in "AZ CO ID MT NV NM UT WY AK CA HI OR WA".split()}}
NAMES = dict(AL="Alabama", AK="Alaska", AZ="Arizona", AR="Arkansas", CA="California", CO="Colorado", CT="Connecticut",
             DE="Delaware", DC="District of Columbia", FL="Florida", GA="Georgia", HI="Hawaii", ID="Idaho",
             IL="Illinois", IN="Indiana", IA="Iowa", KS="Kansas", KY="Kentucky", LA="Louisiana", ME="Maine",
             MD="Maryland", MA="Massachusetts", MI="Michigan", MN="Minnesota", MS="Mississippi", MO="Missouri",
             MT="Montana", NE="Nebraska", NV="Nevada", NH="New Hampshire", NJ="New Jersey", NM="New Mexico",
             NY="New York", NC="North Carolina", ND="North Dakota", OH="Ohio", OK="Oklahoma", OR="Oregon",
             PA="Pennsylvania", RI="Rhode Island", SC="South Carolina", SD="South Dakota", TN="Tennessee",
             TX="Texas", UT="Utah", VT="Vermont", VA="Virginia", WA="Washington", WV="West Virginia",
             WI="Wisconsin", WY="Wyoming")
states = pd.DataFrame({"state": sorted(borrowers.state.unique())})
states["state_name"] = states.state.map(NAMES); states["region"] = states.state.map(REGION)
assert states.notna().all().all()
note("states", "States in the data", len(states), "mapped to name and US Census region")

for df in (loans, perf):
    for c in df.columns:
        if "date" in c:
            df[c] = pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d")
loans.to_csv(CLEAN / "loans.csv", index=False)
borrowers.to_csv(CLEAN / "borrowers.csv", index=False)
perf.to_csv(CLEAN / "loan_performance.csv", index=False)
status_map.to_csv(CLEAN / "loan_status_map.csv", index=False)
states.to_csv(CLEAN / "states.csv", index=False)
pd.DataFrame(log).to_csv(CLEAN / "cleaning_log.csv", index=False)
print(f"\nloans {len(loans):,} | funded ${loans.funded_amnt.sum()/1e6:,.1f}M | snapshot {SNAPSHOT.date()}")
