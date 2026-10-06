# Power BI Executive Dashboard Guide
**Credit Risk & Loan Portfolio Analysis — LendingClub loans 2007–2011 (snapshot 17 Aug 2013)**

Build the dashboard in **Power BI Desktop** (Windows) from `data/powerbi/`. Save it as `powerbi/credit_risk_dashboard.pbix`.

> **On a Mac?** Power BI Desktop is Windows-only. Use a Windows PC or Parallels, or follow the Tableau Public notes at the end.

---

## 1. Files
| File | Rows | Contents |
|---|---|---|
| `fact_loans.csv` | 42,535 | One row per loan: amount, rate, grade, type, term, status, balances, borrower profile, segment bands, **model risk score, risk band, watchlist flag** |
| `dim_state.csv` | 50 | State code, name, US Census region |
| `dim_loan_status.csv` | 7 | Status → group, delinquent / default flags, days past due |
| `dim_grade.csv` | 7 | Grade and sort order |
| `policy_simulation.csv` | 7 | Effect of stricter lending rules (from Python) |
| `model_comparison.csv`, `model_lift_table.csv`, `model_coefficients.csv` | – | Default-risk model results |

## 2. Power Query (Transform Data)
1. `fact_loans`: `issue_date`, `last_payment_date` → **Date**. Money columns (`funded_amnt`, `out_prncp`, `at_risk_amount`, `principal_lost`, `total_pymnt`, `annual_inc`) → **Fixed decimal**. `int_rate`, `revol_util`, `risk_score` → **Percentage**.
2. Band columns (`fico_band`, `income_band`, `dti_band`, `rate_band`, `amount_band`, `emp_band`) start with a sort number, e.g. `1. <660`. Add a clean label: **Add Column → Extract → Text After Delimiter** (". ") → e.g. `FICO Band`. Then **sort the label column by the original column**.
3. Add a column `Term` = `Text.From([term_months]) & " months"`.
4. Close & Apply.

## 3. Model
- Date table: **New table** → `Dim_Date = CALENDAR(DATE(2007,1,1), DATE(2013,12,31))`. Add `Year = YEAR([Date])` and `Quarter = "Q" & QUARTER([Date])`, then mark it as a date table.
- Relationships (one-to-many, single direction):
  - `Dim_Date[Date]` → `fact_loans[issue_date]`
  - `dim_state[state]` → `fact_loans[state]`
  - `dim_loan_status[loan_status]` → `fact_loans[loan_status]`
  - `dim_grade[grade]` → `fact_loans[grade]`
- Sort `dim_grade[grade]` by `grade_order`.

## 4. DAX measures (create a `_Measures` table)
### The six executive KPIs
```DAX
Total Loan Value  = SUM ( fact_loans[funded_amnt] )                       -- $ #,0.0,,"M"
Number of Loans   = COUNTROWS ( fact_loans )
Default Rate      = DIVIDE ( SUM ( fact_loans[is_default] ), [Number of Loans] )            -- %
Delinquency Rate  = DIVIDE ( SUM ( fact_loans[is_delinquent] ), SUM ( fact_loans[is_active] ) )
Average Interest Rate = AVERAGE ( fact_loans[int_rate] )
At-Risk Loan Value    = SUM ( fact_loans[at_risk_amount] )                 -- delinquent + defaulted balance
```
### Supporting measures
```DAX
Outstanding Balance    = SUM ( fact_loans[out_prncp] )
At-Risk % of Outstanding = DIVIDE ( [At-Risk Loan Value], [Outstanding Balance] )
Principal Lost         = SUM ( fact_loans[principal_lost] )
Loss Rate              = DIVIDE ( [Principal Lost], [Total Loan Value] )
Weighted Avg Rate      = DIVIDE ( SUMX ( fact_loans, fact_loans[int_rate] * fact_loans[funded_amnt] ), [Total Loan Value] )

Watchlist Balance      = CALCULATE ( [Outstanding Balance], fact_loans[watchlist] = 1 )
Total Potentially At Risk = [At-Risk Loan Value] + [Watchlist Balance]
Potentially At Risk %  = DIVIDE ( [Total Potentially At Risk], [Outstanding Balance] )

Lifetime Default Rate (Matured) = CALCULATE ( [Default Rate], fact_loans[matured] = 1 )
Lifetime Net Return (Matured) =
    DIVIDE ( CALCULATE ( SUM ( fact_loans[total_pymnt] ), fact_loans[matured] = 1 ),
             CALCULATE ( [Total Loan Value], fact_loans[matured] = 1 ) ) - 1

Default Rate Lift =                                   -- 1.0 = portfolio average
    DIVIDE ( [Default Rate], CALCULATE ( [Default Rate], ALL ( fact_loans ) ) )

Avg Risk Score = AVERAGE ( fact_loans[risk_score] )
Avg FICO       = AVERAGE ( fact_loans[fico_score] )
Avg Loan       = AVERAGE ( fact_loans[funded_amnt] )
```
### Segment selector (field parameter)
**Modeling → New parameter → Fields** → name `Segment` → add `FICO Band`, `Income Band`, `DTI Band`, `grade`, `home_ownership`, `Term`, `region`, `risk_band`, `emp_band`. Power BI creates a slicer: one chart then switches between all customer segments.

## 5. Report pages
Apply the theme: **View → Themes → Browse** → `powerbi/theme/credit_theme.json`.
Slicers (synced on all pages): `Dim_Date[Year]`, `fact_loans[Term]`, `fact_loans[loan_type]`, `dim_grade[grade]`.

### Page 1 — Executive overview
| Visual | Fields |
|---|---|
| **6 cards** | Total Loan Value · Number of Loans · Default Rate · Delinquency Rate · Average Interest Rate · At-Risk Loan Value |
| **Clustered column** — *Default rate by customer segment* | X: `Segment` field parameter; Y: `Default Rate`; conditional colour by `Default Rate Lift` (> 1.2 orange) |
| **Bar** — *Loan performance by loan type* | Y: `loan_type`; X: `Default Rate`; tooltip `Total Loan Value`, `Principal Lost`, `At-Risk Loan Value` |
| **Line** — *Default trend over time* | X: `Dim_Date[Year]` → `Quarter` (drill down); Y: `Default Rate` (add `issue_year` share-active as a second line) |
| **Text box** | 3 key findings + 3 recommendations from the README |

### Page 2 — Customer segments & credit score
| Visual | Fields |
|---|---|
| **Line + column** — *Credit score vs default* | X: `FICO Band`; columns `Number of Loans`; line `Default Rate` |
| **Small multiples (column)** | X: `Segment` parameter; Y: `Default Rate`; small multiples: `Term` |
| **Matrix** | Rows `grade`; columns `home_ownership`; values `Default Rate` with background colour scale |

### Page 3 — Loan performance & pricing
| Visual | Fields |
|---|---|
| **Matrix** | Rows `loan_type`; values `Number of Loans`, `Total Loan Value`, `Default Rate`, `Principal Lost`, `At-Risk Loan Value`, `Average Interest Rate` |
| **Scatter** — *Loan amount vs risk* | Values `sub_grade`; X `Avg Loan`; Y `Default Rate`; size `Total Loan Value` (also try X = `Average Interest Rate`) |
| **Column** | X `grade`; Y `Lifetime Net Return (Matured)`: shows grade F losing money |
| **Column** | X `amount_band`; Y `Default Rate` |

### Page 4 — Geographic risk
| Visual | Fields |
|---|---|
| **Filled map** | Location `dim_state[state_name]`; colour saturation `Default Rate`; tooltip `Number of Loans`, `At-Risk Loan Value` |
| **Bar** | Y `dim_state[region]`; X `Default Rate` |
| **Table** | States with `Number of Loans` ≥ 500 (visual-level filter), sorted by `Default Rate` |

### Page 5 — High-risk loan portfolio
| Visual | Fields |
|---|---|
| **Cards** | At-Risk Loan Value · Watchlist Balance · Total Potentially At Risk · Potentially At Risk % |
| **Stacked bar** | Y `grade`; X `At-Risk Loan Value` and `Watchlist Balance` |
| **Table** (the action list) | Filter: `watchlist = 1` OR `status_group = "Active - delinquent"`; columns `loan_id`, `loan_status`, `grade`, `loan_type`, `state`, `out_prncp`, `risk_score`, `fico_score`; sorted by `risk_score` descending |
| **Table** | `policy_simulation.csv`: rule, % declined, defaults avoided, net return after |
| **Column** | `model_lift_table`: decile vs actual default |

## 6. Check your numbers (no filters)
**Total Loan Value $460.3M · 42,535 loans · Default Rate 10.98% · Delinquency Rate 5.86% · Average Interest Rate 12.16% · At-Risk Loan Value $7.60M · Watchlist $12.78M · Lifetime Default Rate (matured) 14.32%.**

## 7. Tableau Public (Mac alternative)
Connect `fact_loans.csv` (and relate `dim_state.csv` on `state`). Calculated fields:
| Measure | Tableau formula |
|---|---|
| Default Rate | `SUM([is_default]) / COUNT([loan_id])` |
| Delinquency Rate | `SUM([is_delinquent]) / SUM([is_active])` |
| At-Risk Loan Value | `SUM([at_risk_amount])` |
| Lifetime Net Return (Matured) | `SUM(IF [matured]=1 THEN [total_pymnt] END) / SUM(IF [matured]=1 THEN [funded_amnt] END) - 1` |
| Segment selector | Create a **parameter** with the segment names, then a calculated field `CASE [Segment] WHEN "FICO" THEN [fico_band] WHEN "Income" THEN [income_band] ... END` |

Use the state name for a filled map. Build the same five pages as dashboards and publish with **File → Save to Tableau Public**.
