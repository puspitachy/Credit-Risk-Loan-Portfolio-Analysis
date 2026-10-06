# Data source

**LendingClub — LoanStats3a.csv (loans issued June 2007 – December 2011)**

Real, anonymised loan-level data published by LendingClub, a US peer-to-peer consumer lender, as part
of its public statistics (originally downloadable from lendingclub.com; the first line of the file is
LendingClub's own note pointing to its prospectus).

- 42,535 loans, 102 columns (40 of them empty in this vintage)
- Loan status and balances as of LendingClub's data extract in **August 2013**
  (latest payment date in the file: 16 Aug 2013 — used as the snapshot date 17 Aug 2013)

The file here was downloaded unchanged from a public GitHub copy
(github.com/yhat/demo-lending-club, `model/LoanStats3a.csv`). It is used for educational,
non-commercial purposes; the data belongs to LendingClub.

This file is **never modified**. All cleaning happens in `scripts/01_prepare_data.py`, which writes
to `data/clean/`.

On GitHub the file is stored gzip-compressed as `LoanStats3a.csv.gz` (GitHub's web upload limit is 25 MB); the prepare script reads either version.
