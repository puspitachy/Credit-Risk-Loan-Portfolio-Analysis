"""
04_build_excel.py
Builds excel/loan_portfolio_risk.xlsx — the Excel part of the project.
All KPIs and tables are live formulas (COUNTIFS / SUMIFS / SUMPRODUCT / INDEX-MATCH)
over the Loan_Data sheet. Includes an interactive segment explorer and a credit-policy
simulator. Run the LibreOffice recalc afterwards so values are stored in the file.
"""
import sqlite3
import pandas as pd
from pathlib import Path
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, ScatterChart, Reference, Series
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "excel"; OUT.mkdir(exist_ok=True)
con = sqlite3.connect(BASE / "data" / "credit_risk.db")

F, NAVY, BLUE, ORANGE, GREEN = "Arial", "1F3A5F", "2A78D6", "EB6834", "1BAF7A"
h_font, h_fill = Font(name=F, bold=True, color="FFFFFF", size=10), PatternFill("solid", fgColor=NAVY)
title_font, sub_font = Font(name=F, bold=True, size=16, color=NAVY), Font(name=F, italic=True, size=10, color="52514E")
bold, norm = Font(name=F, bold=True, size=10), Font(name=F, size=10)
blue_input = Font(name=F, bold=True, size=11, color="0000FF")
input_fill, kpi_fill = PatternFill("solid", fgColor="FFF2CC"), PatternFill("solid", fgColor="EEF3FA")
bad_fill, good_fill = PatternFill("solid", fgColor="FCE3D8"), PatternFill("solid", fgColor="DDF3EA")
thin = Side(style="thin", color="C9C8C2"); box = Border(left=thin, right=thin, top=thin, bottom=thin)
MONEY, MONEY_M, PCT, PCT2, INT = '$#,##0;($#,##0);-', '$#,##0.0,,"M"', '0.0%', '0.00%', '#,##0'

def title(ws, t, s):
    ws["A1"], ws["A2"] = t, s; ws["A1"].font, ws["A2"].font = title_font, sub_font; ws.sheet_view.showGridLines = False

def header(ws, row, col, labels, widths=None):
    for i, lab in enumerate(labels):
        c = ws.cell(row=row, column=col + i, value=lab)
        c.font, c.fill, c.border = h_font, h_fill, box
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 32
    for i, w in enumerate(widths or []):
        ws.column_dimensions[get_column_letter(col + i)].width = w

def put(ws, ref, value, fmt=None, font=norm, fill=None, align=None):
    c = ws[ref]; c.value = value; c.font = font; c.border = box
    if fmt: c.number_format = fmt
    if fill: c.fill = fill
    if align: c.alignment = Alignment(horizontal=align)
    return c

def note(ws, ref, text):
    ws[ref] = text; ws[ref].font = sub_font

def vlabels():
    d = DataLabelList(); d.showVal, d.showSerName, d.showCatName, d.showLegendKey = True, False, False, False
    return d

def risk_scale(ws, rng):
    ws.conditional_formatting.add(rng, ColorScaleRule(start_type="min", start_color="FFFFFF", end_type="max", end_color=ORANGE))

wb = Workbook()

# ================================================================== LOAN DATA
cols = ["loan_id", "issue_date", "issue_year", "funded_amnt", "term_months", "int_rate", "grade", "grade_num", "sub_grade",
        "loan_type", "loan_status", "status_group", "is_active", "is_delinquent", "is_default", "out_prncp",
        "at_risk_amount", "principal_lost", "total_pymnt", "fico_score", "fico_band", "income_band", "dti_band",
        "rate_band", "home_ownership", "state", "region", "inq_last_6mths", "meets_credit_policy", "matured",
        "risk_score", "risk_band", "watchlist"]
d = pd.read_sql("""SELECT v.*, s.risk_score, s.risk_band, s.watchlist, s.matured
                   FROM vw_loans v JOIN loan_risk_scores s USING (loan_id) ORDER BY v.issue_date, v.loan_id""",
                con, parse_dates=["issue_date"])
d["grade_num"] = d.grade.map({g: i + 1 for i, g in enumerate("ABCDEFG")})
for c in ["fico_band", "income_band", "dti_band", "rate_band"]:
    d[c] = d[c].str.split(". ", n=1).str[1]
d["term_months"] = d.term_months.astype(str) + " months"
d = d[cols]
L = wb.active; L.title = "Loan_Data"
header(L, 1, 1, cols + ["declined_by_policy"])
fmts = {"issue_date": "yyyy-mm-dd", "funded_amnt": MONEY, "int_rate": PCT2, "out_prncp": MONEY, "at_risk_amount": MONEY,
        "principal_lost": MONEY, "total_pymnt": MONEY, "risk_score": PCT}
for r, row in enumerate(d.itertuples(index=False), 2):
    for c, v in enumerate(row, 1):
        if pd.isna(v): continue
        cell = L.cell(row=r, column=c, value=v.to_pydatetime() if isinstance(v, pd.Timestamp) else v)
        if cols[c - 1] in fmts: cell.number_format = fmts[cols[c - 1]]
N = len(d) + 1
CL = {c: get_column_letter(i + 1) for i, c in enumerate(cols + ["declined_by_policy"])}
t = Table(displayName="Loans", ref=f"A1:{CL['declined_by_policy']}{N}")
t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True); L.add_table(t)
L.freeze_panes = "B2"
for c in cols: L.column_dimensions[CL[c]].width = max(11, len(c) + 2)
R = lambda c: f"Loan_Data!${CL[c]}$2:${CL[c]}${N}"

# ================================================================== LISTS (segment explorer)
LS = wb.create_sheet("Lists")
dims = [("Grade", "grade"), ("FICO band", "fico_band"), ("Income band", "income_band"), ("Debt-to-income", "dti_band"),
        ("Interest rate band", "rate_band"), ("Loan type", "loan_type"), ("Term", "term_months"),
        ("Home ownership", "home_ownership"), ("Region", "region"), ("Risk band (model)", "risk_band")]
orders = {"fico_band": ["<660", "660-679", "680-699", "700-719", "720-739", "740-759", "760+"],
          "income_band": ["<$30K", "$30-50K", "$50-75K", "$75-100K", "$100-150K", "$150K+"],
          "dti_band": ["<5%", "5-10%", "10-15%", "15-20%", "20-25%", "25%+"],
          "rate_band": ["<8%", "8-11%", "11-14%", "14-17%", "17-20%", "20%+"],
          "risk_band": ["Low", "Medium", "High", "Very high"]}
LS["A1"] = "Dimension"; LS["B1"] = "Data column #"
for i, (lab, col) in enumerate(dims):
    LS.cell(row=2 + i, column=1, value=lab); LS.cell(row=2 + i, column=2, value=cols.index(col) + 1)
    vals = orders.get(col, sorted(d[col].dropna().unique()))
    LS.cell(row=1, column=4 + i, value=lab)
    for k, v in enumerate(vals): LS.cell(row=2 + k, column=4 + i, value=v)
LS.sheet_state = "hidden"
DATA_BLOCK = f"Loan_Data!$A$2:${CL['risk_band']}${N}"

# ================================================================== SEGMENT EXPLORER
S = wb.create_sheet("Segment_Explorer", 0)
title(S, "Segment Risk Explorer", "Choose a dimension in the yellow cell - the table and chart rebuild for that customer or loan segment.")
put(S, "A4", "Dimension", font=bold); put(S, "B4", "Loan type", font=blue_input, fill=input_fill)
dv = DataValidation(type="list", formula1=f"=Lists!$A$2:$A${1 + len(dims)}", allow_blank=False); S.add_data_validation(dv); dv.add("B4")
S["D4"] = "=MATCH(B4,Lists!$A$2:$A$11,0)"; S["E4"] = "=INDEX(Lists!$B$2:$B$11,D4)"
for ref in ("D4", "E4"): S[ref].font = Font(name=F, size=8, color="999999")
note(S, "F4", "(helper cells: dimension number and data column)")
header(S, 6, 1, ["Segment", "Loans", "Loan value", "Share of value", "Default rate", "Avg interest rate",
                 "Outstanding", "At-risk value", "Principal lost", "Lift vs portfolio"], [22, 10, 15, 10, 10, 10, 14, 13, 13, 10])
for k in range(15):
    r = 7 + k
    seg = f"$A{r}"
    colrng = f"INDEX({DATA_BLOCK},0,$E$4)"
    S[f"A{r}"] = f'=IF(INDEX(Lists!$D$2:$M$16,{k + 1},$D$4)="","",INDEX(Lists!$D$2:$M$16,{k + 1},$D$4))'; S[f"A{r}"].font = bold; S[f"A{r}"].border = box
    put(S, f"B{r}", f'=IF({seg}="","",COUNTIFS({colrng},{seg}))', INT)
    put(S, f"C{r}", f'=IF({seg}="","",SUMIFS({R("funded_amnt")},{colrng},{seg}))', MONEY)
    put(S, f"D{r}", f'=IF({seg}="","",C{r}/SUM({R("funded_amnt")}))', PCT)
    put(S, f"E{r}", f'=IF({seg}="","",IFERROR(COUNTIFS({colrng},{seg},{R("is_default")},1)/B{r},0))', PCT)
    put(S, f"F{r}", f'=IF({seg}="","",IFERROR(AVERAGEIFS({R("int_rate")},{colrng},{seg}),0))', PCT2)
    put(S, f"G{r}", f'=IF({seg}="","",SUMIFS({R("out_prncp")},{colrng},{seg}))', MONEY)
    put(S, f"H{r}", f'=IF({seg}="","",SUMIFS({R("at_risk_amount")},{colrng},{seg}))', MONEY)
    put(S, f"I{r}", f'=IF({seg}="","",SUMIFS({R("principal_lost")},{colrng},{seg}))', MONEY)
    put(S, f"J{r}", f'=IF({seg}="","",E{r}/$E$23)', "0.00x")
put(S, "A23", "Portfolio", font=bold)
put(S, "B23", f"=COUNT({R('loan_id')})", INT, bold); put(S, "C23", f"=SUM({R('funded_amnt')})", MONEY, bold)
put(S, "E23", f"=SUM({R('is_default')})/B23", PCT, bold); put(S, "F23", f"=AVERAGE({R('int_rate')})", PCT2, bold)
put(S, "G23", f"=SUM({R('out_prncp')})", MONEY, bold); put(S, "H23", f"=SUM({R('at_risk_amount')})", MONEY, bold)
put(S, "I23", f"=SUM({R('principal_lost')})", MONEY, bold)
risk_scale(S, "E7:E21")
S.conditional_formatting.add("J7:J21", CellIsRule(operator="greaterThan", formula=["1.2"], fill=bad_fill))
S.conditional_formatting.add("J7:J21", CellIsRule(operator="lessThan", formula=["0.8"], fill=good_fill))
note(S, "A24", "Lift = segment default rate / portfolio default rate. Red > 1.2x (riskier), green < 0.8x (safer).")
ch = BarChart(); ch.type = "col"; ch.title = "Default rate by selected segment"; ch.style = 10
ch.add_data(Reference(S, min_col=5, min_row=6, max_row=21), titles_from_data=True)
ch.set_categories(Reference(S, min_col=1, min_row=7, max_row=21)); ch.legend = None
ch.series[0].graphicalProperties.solidFill = ORANGE; ch.y_axis.numFmt = "0%"; ch.height, ch.width = 8, 18
S.add_chart(ch, "L6")

# ================================================================== LOAN TYPE & TERM
T = wb.create_sheet("Loan_Types", 1)
title(T, "Loan Performance by Loan Type and Term", "Which loan types carry the greatest risk and where the losses sit.")
types = d.groupby("loan_type").is_default.mean().sort_values(ascending=False).index.tolist()
header(T, 4, 1, ["Loan type", "Loans", "Loan value", "Share of value", "Default rate", "Principal lost", "Share of losses",
                 "At-risk value", "Share of at-risk", "Risk rank"], [22, 9, 15, 10, 10, 14, 10, 13, 10, 8])
n = len(types)
for i, lt in enumerate(types):
    r = 5 + i; c = f'{R("loan_type")},$A{r}'
    put(T, f"A{r}", lt, font=bold)
    put(T, f"B{r}", f"=COUNTIFS({c})", INT); put(T, f"C{r}", f"=SUMIFS({R('funded_amnt')},{c})", MONEY)
    put(T, f"D{r}", f"=C{r}/SUM($C$5:$C${4 + n})", PCT)
    put(T, f"E{r}", f"=COUNTIFS({c},{R('is_default')},1)/B{r}", PCT)
    put(T, f"F{r}", f"=SUMIFS({R('principal_lost')},{c})", MONEY); put(T, f"G{r}", f"=F{r}/SUM($F$5:$F${4 + n})", PCT)
    put(T, f"H{r}", f"=SUMIFS({R('at_risk_amount')},{c})", MONEY); put(T, f"I{r}", f"=H{r}/SUM($H$5:$H${4 + n})", PCT)
    put(T, f"J{r}", f"=RANK(E{r},$E$5:$E${4 + n})", "0", align="center")
risk_scale(T, f"E5:E{4 + n}")
T.conditional_formatting.add(f"G5:G{4 + n}", DataBarRule(start_type="num", start_value=0, end_type="max", color=BLUE))
tr = 6 + n
header(T, tr, 1, ["Term", "Loans", "Loan value", "Avg interest rate", "Default rate", "Active loans", "Delinquency rate",
                  "Outstanding", "Share of outstanding", "Share of at-risk"])
for i, tm in enumerate(["36 months", "60 months"]):
    r = tr + 1 + i; c = f'{R("term_months")},$A{r}'
    put(T, f"A{r}", tm, font=bold)
    put(T, f"B{r}", f"=COUNTIFS({c})", INT); put(T, f"C{r}", f"=SUMIFS({R('funded_amnt')},{c})", MONEY)
    put(T, f"D{r}", f"=AVERAGEIFS({R('int_rate')},{c})", PCT2); put(T, f"E{r}", f"=COUNTIFS({c},{R('is_default')},1)/B{r}", PCT)
    put(T, f"F{r}", f"=COUNTIFS({c},{R('is_active')},1)", INT)
    put(T, f"G{r}", f"=COUNTIFS({c},{R('is_delinquent')},1)/F{r}", PCT)
    put(T, f"H{r}", f"=SUMIFS({R('out_prncp')},{c})", MONEY)
    put(T, f"I{r}", f"=H{r}/SUM({R('out_prncp')})", PCT); put(T, f"J{r}", f"=SUMIFS({R('at_risk_amount')},{c})/SUM({R('at_risk_amount')})", PCT)
ch = BarChart(); ch.type = "bar"; ch.title = "Default rate by loan type"; ch.style = 10
ch.add_data(Reference(T, min_col=5, min_row=4, max_row=4 + n), titles_from_data=True)
ch.set_categories(Reference(T, min_col=1, min_row=5, max_row=4 + n)); ch.legend = None
ch.x_axis.scaling.orientation = "maxMin"; ch.series[0].graphicalProperties.solidFill = ORANGE; ch.y_axis.numFmt = "0%"
ch.height, ch.width = 9, 15; T.add_chart(ch, "L4")

# ================================================================== RATE vs DEFAULT
RT = wb.create_sheet("Rate_vs_Default", 2)
title(RT, "Interest Rate vs Default - Does Pricing Cover the Risk?", "Lifetime figures use MATURED loans (36-month loans issued by Aug 2010), so every outcome is known.")
header(RT, 4, 1, ["Grade", "All loans", "Avg interest rate", "Default rate (all, today)", "Matured loans",
                  "Lifetime default rate", "Money lent (matured)", "Cash returned (matured)", "Lifetime net return", "Verdict"],
       [8, 10, 11, 12, 10, 11, 15, 15, 11, 26])
for i, g in enumerate("ABCDEFG"):
    r = 5 + i; c = f'{R("grade")},$A{r}'; m = f'{c},{R("matured")},1'
    put(RT, f"A{r}", g, font=bold, align="center")
    put(RT, f"B{r}", f"=COUNTIFS({c})", INT); put(RT, f"C{r}", f"=AVERAGEIFS({R('int_rate')},{c})", PCT2)
    put(RT, f"D{r}", f"=COUNTIFS({c},{R('is_default')},1)/B{r}", PCT)
    put(RT, f"E{r}", f"=COUNTIFS({m})", INT); put(RT, f"F{r}", f"=COUNTIFS({m},{R('is_default')},1)/E{r}", PCT)
    put(RT, f"G{r}", f"=SUMIFS({R('funded_amnt')},{m})", MONEY); put(RT, f"H{r}", f"=SUMIFS({R('total_pymnt')},{m})", MONEY)
    put(RT, f"I{r}", f"=H{r}/G{r}-1", '+0.0%;-0.0%')
    put(RT, f"J{r}", f'=IF(I{r}<0,"Loses money",IF(I{r}<0.05,"Barely covers losses","Rate covers the risk"))')
RT.conditional_formatting.add("I5:I11", CellIsRule(operator="lessThan", formula=["0.05"], fill=bad_fill))
RT.conditional_formatting.add("I5:I11", CellIsRule(operator="greaterThanOrEqual", formula=["0.05"], fill=good_fill))
put(RT, "A13", "Correlation of interest rate and default (grade level):", font=bold); RT.merge_cells("A13:E13")
put(RT, "F13", "=CORREL(C5:C11,D5:D11)", "0.00", bold)
note(RT, "A14", "Net return = cash returned / money lent - 1, over the full life of matured loans (recoveries after charge-off not included).")
sc = ScatterChart(); sc.title = "Interest rate vs default rate by grade"; sc.style = 13
s_ = Series(Reference(RT, min_col=4, min_row=5, max_row=11), Reference(RT, min_col=3, min_row=5, max_row=11), title="Grades A-G")
s_.marker.symbol = "circle"; s_.marker.size = 9; s_.graphicalProperties.line.noFill = True
s_.marker.graphicalProperties.solidFill = BLUE; sc.series.append(s_)
sc.x_axis.title = "Average interest rate"; sc.y_axis.title = "Default rate"; sc.x_axis.numFmt = "0%"; sc.y_axis.numFmt = "0%"
sc.legend = None; sc.height, sc.width = 8, 13; RT.add_chart(sc, "A16")
ch = BarChart(); ch.type = "col"; ch.title = "Lifetime net return by grade"; ch.style = 10
ch.add_data(Reference(RT, min_col=9, min_row=4, max_row=11), titles_from_data=True)
ch.set_categories(Reference(RT, min_col=1, min_row=5, max_row=11)); ch.legend = None
ch.series[0].graphicalProperties.solidFill = GREEN; ch.y_axis.numFmt = "0%"; ch.dataLabels = vlabels(); ch.height, ch.width = 8, 13
RT.add_chart(ch, "G16")

# ================================================================== TREND & GEOGRAPHY
TG = wb.create_sheet("Trend_Geography", 3)
title(TG, "Default Trend Over Time and Geographic Risk", "Vintage = year the loan was issued.")
header(TG, 4, 1, ["Issue year", "Loans", "Loan value", "Default rate", "Still active", "Avg interest rate"], [10, 9, 15, 10, 10, 10])
for i, y in enumerate(range(2007, 2012)):
    r = 5 + i; c = f'{R("issue_year")},$A{r}'
    put(TG, f"A{r}", y, "0", bold, align="center")
    put(TG, f"B{r}", f"=COUNTIFS({c})", INT); put(TG, f"C{r}", f"=SUMIFS({R('funded_amnt')},{c})", MONEY)
    put(TG, f"D{r}", f"=COUNTIFS({c},{R('is_default')},1)/B{r}", PCT); put(TG, f"E{r}", f"=COUNTIFS({c},{R('is_active')},1)/B{r}", PCT)
    put(TG, f"F{r}", f"=AVERAGEIFS({R('int_rate')},{c})", PCT2)
note(TG, "A10", "Recent vintages look safer partly because many of their loans are still active and could still default.")
states = d.groupby("state").size(); states = states[states >= 500].index.tolist()
header(TG, 12, 1, ["State", "Region", "Loans", "Default rate", "At-risk value", "Risk rank"])
for i, s in enumerate(states):
    r = 13 + i; c = f'{R("state")},$A{r}'
    put(TG, f"A{r}", s, font=bold, align="center")
    put(TG, f"B{r}", f"=INDEX({R('region')},MATCH(A{r},{R('state')},0))")
    put(TG, f"C{r}", f"=COUNTIFS({c})", INT); put(TG, f"D{r}", f"=COUNTIFS({c},{R('is_default')},1)/C{r}", PCT)
    put(TG, f"E{r}", f"=SUMIFS({R('at_risk_amount')},{c})", MONEY); put(TG, f"F{r}", f"=RANK(D{r},$D$13:$D${12 + len(states)})", "0", align="center")
risk_scale(TG, f"D13:D{12 + len(states)}")
note(TG, f"A{14 + len(states)}", "States with at least 500 loans. Use the filter or sort on 'Risk rank'.")
TG.auto_filter.ref = f"A12:F{12 + len(states)}"
lc = LineChart(); lc.title = "Default rate by issue year"; lc.style = 12
lc.add_data(Reference(TG, min_col=4, min_row=4, max_row=9), titles_from_data=True)
lc.add_data(Reference(TG, min_col=5, min_row=4, max_row=9), titles_from_data=True)
lc.set_categories(Reference(TG, min_col=1, min_row=5, max_row=9)); lc.y_axis.numFmt = "0%"
lc.series[0].graphicalProperties.line.solidFill = ORANGE; lc.series[1].graphicalProperties.line.solidFill = "8A8984"
lc.series[1].graphicalProperties.line.dashStyle = "dash"
for s_ in lc.series: s_.smooth = False
lc.height, lc.width = 7.5, 14; lc.legend.position = "b"; TG.add_chart(lc, "H4")

# ================================================================== AT RISK
AR = wb.create_sheet("At_Risk", 4)
title(AR, "How Much of the Portfolio Is at Risk?", "Balances at the 17 Aug 2013 snapshot. Watchlist = current loans with a high model risk score.")
header(AR, 4, 1, ["Layer", "Loans", "Outstanding", "Share of outstanding"], [42, 15, 16, 15])
AR.column_dimensions["E"].width = 12
layers = [("Delinquent (1-120 days late)", f'{R("is_delinquent")},1'),
          ("In default (121+ days)", f'{R("loan_status")},"Default"'),
          ("Watchlist: current but high risk score", f'{R("watchlist")},1')]
for i, (lab, c) in enumerate(layers):
    r = 5 + i
    put(AR, f"A{r}", lab, font=bold); put(AR, f"B{r}", f"=COUNTIFS({c})", INT)
    put(AR, f"C{r}", f"=SUMIFS({R('out_prncp')},{c})", MONEY); put(AR, f"D{r}", f"=C{r}/$C$10", PCT)
put(AR, "A8", "Total potentially at risk", font=bold); put(AR, "B8", "=SUM(B5:B7)", INT, bold)
put(AR, "C8", "=SUM(C5:C7)", MONEY, bold); put(AR, "D8", "=C8/$C$10", PCT, bold)
put(AR, "A10", "Total outstanding balance", font=bold); put(AR, "C10", f"=SUM({R('out_prncp')})", MONEY, bold)
put(AR, "A11", "Already lost to charge-offs (history)", font=bold); put(AR, "C11", f"=SUM({R('principal_lost')})", MONEY, bold)
put(AR, "D11", f"=C11/SUM({R('funded_amnt')})", PCT); note(AR, "E11", "of all money lent")
header(AR, 14, 1, ["Grade", "Outstanding", "At-risk (delinquent + default)", "Watchlist", "At-risk share"])
for i, g in enumerate("ABCDEFG"):
    r = 15 + i; c = f'{R("grade")},$A{r}'
    put(AR, f"A{r}", g, font=bold, align="center")
    put(AR, f"B{r}", f"=SUMIFS({R('out_prncp')},{c})", MONEY); put(AR, f"C{r}", f"=SUMIFS({R('at_risk_amount')},{c})", MONEY)
    put(AR, f"D{r}", f"=SUMIFS({R('out_prncp')},{c},{R('watchlist')},1)", MONEY); put(AR, f"E{r}", f"=IFERROR((C{r}+D{r})/B{r},0)", PCT)
risk_scale(AR, "E15:E21")
ch = BarChart(); ch.type = "col"; ch.grouping = "stacked"; ch.overlap = 100; ch.title = "At-risk and watchlist balance by grade"
ch.add_data(Reference(AR, min_col=3, max_col=4, min_row=14, max_row=21), titles_from_data=True)
ch.set_categories(Reference(AR, min_col=1, min_row=15, max_row=21))
ch.series[0].graphicalProperties.solidFill = ORANGE; ch.series[1].graphicalProperties.solidFill = "EDA100"
ch.y_axis.numFmt = '$#,##0.0,,"M"'; ch.height, ch.width = 8, 14; ch.legend.position = "b"; AR.add_chart(ch, "G4")

# ================================================================== POLICY SIMULATOR
P = wb.create_sheet("Policy_Simulator", 5)
title(P, "Credit Policy Simulator", "Change the yellow rules: see what would have happened to MATURED loans (full outcomes known) if those applicants had been declined.")
rules = [("Decline if FICO score below", 660, "0"), ("Decline grades at or worse than (1=A ... 7=G; 8 = off)", 6, "0"),
         ("Decline if credit inquiries in last 6 months at least (99 = off)", 3, "0"),
         ("Decline small business loans? (Yes/No)", "Yes", None), ("Decline loans failing credit policy? (Yes/No)", "Yes", None)]
header(P, 4, 1, ["Rule", "Setting"], [58, 12])
for i, (lab, v, f) in enumerate(rules):
    r = 5 + i
    put(P, f"A{r}", lab, font=bold); put(P, f"B{r}", v, f, blue_input, input_fill, "center")
dvp = DataValidation(type="list", formula1='"Yes,No"', allow_blank=False); P.add_data_validation(dvp); dvp.add("B8"); dvp.add("B9")
note(P, "A10", "Set FICO to 0, grade to 8 and inquiries to 99 to switch those rules off.")
# helper column in Loan_Data: 1 if a matured loan would be declined by the current rules
dc = CL["declined_by_policy"]
for r in range(2, N + 1):
    L[f"{dc}{r}"] = (f'=IF(${CL["matured"]}{r}=1,IF(OR(${CL["fico_score"]}{r}<Policy_Simulator!$B$5,'
                     f'${CL["grade_num"]}{r}>=Policy_Simulator!$B$6,${CL["inq_last_6mths"]}{r}>=Policy_Simulator!$B$7,'
                     f'AND(Policy_Simulator!$B$8="Yes",${CL["loan_type"]}{r}="Small Business"),'
                     f'AND(Policy_Simulator!$B$9="Yes",${CL["meets_credit_policy"]}{r}=0)),1,0),"")')
L.column_dimensions[dc].width = 18
M = f'{R("matured")},1'
dec = R("declined_by_policy")
header(P, 12, 1, ["Result on matured loans", "Actual book", "Declined by rules", "Book after rules"], [58, 15, 15, 15])
res = [
    ("Loans", f"=COUNTIFS({M})", f"=COUNTIFS({M},{dec},1)", "=B13-C13", INT),
    ("Money lent", f"=SUMIFS({R('funded_amnt')},{M})", f"=SUMIFS({R('funded_amnt')},{M},{dec},1)", "=B14-C14", MONEY),
    ("Defaults", f"=COUNTIFS({M},{R('is_default')},1)", f"=COUNTIFS({M},{dec},1,{R('is_default')},1)", "=B15-C15", INT),
    ("Default rate", "=B15/B13", "=IFERROR(C15/C13,0)", "=D15/D13", PCT2),
    ("Cash returned", f"=SUMIFS({R('total_pymnt')},{M})", f"=SUMIFS({R('total_pymnt')},{M},{dec},1)", "=B17-C17", MONEY),
    ("Lifetime net return", "=B17/B14-1", "=IFERROR(C17/C14-1,0)", "=D17/D14-1", '+0.00%;-0.00%'),
]
for i, (lab, b, c, dd, fmt) in enumerate(res):
    r = 13 + i
    put(P, f"A{r}", lab, font=bold); put(P, f"B{r}", b, fmt); put(P, f"C{r}", c, fmt); put(P, f"D{r}", dd, fmt)
put(P, "A20", "Share of lending declined", font=bold); put(P, "B20", "=C14/B14", PCT, bold)
put(P, "A21", "Share of defaults avoided", font=bold); put(P, "B21", "=C15/B15", PCT, bold)
put(P, "A22", "Change in net return of the book", font=bold); put(P, "B22", "=D18-B18", '+0.00%;-0.00%', bold)
put(P, "A23", "Verdict", font=bold)
put(P, "B23", '=IF(B21>B20*1.3,"Good trade: avoids far more defaults than volume lost",IF(B21>B20,"Modest benefit","Not worth it"))', font=bold)
P.merge_cells("B23:D23")
P.conditional_formatting.add("B22", CellIsRule(operator="greaterThan", formula=["0"], fill=good_fill))
P.conditional_formatting.add("B22", CellIsRule(operator="lessThan", formula=["0"], fill=bad_fill))
note(P, "A25", "Matured loans = 36-month loans issued on or before 17 Aug 2010 (13,903 loans). Returns exclude post-charge-off recoveries.")

# ================================================================== CLEANING LOG
CLg = wb.create_sheet("Cleaning_Log")
title(CLg, "Data Checks and Cleaning", "From scripts/01_prepare_data.py - the original LendingClub file was never modified.")
log = pd.read_csv(BASE / "data" / "clean" / "cleaning_log.csv")
header(CLg, 4, 1, list(log.columns), [18, 56, 10, 80])
for i, row in enumerate(log.itertuples(index=False)):
    for j, v in enumerate(row):
        c = CLg.cell(row=5 + i, column=j + 1, value=v); c.font = norm; c.border = box
        if j == 2: c.number_format = INT

# ================================================================== DASHBOARD
DB = wb.create_sheet("Dashboard", 0)
title(DB, "Loan Portfolio Risk Dashboard", "LendingClub loans issued 2007-2011 | balances and statuses at 17 Aug 2013 | real data")
for c, w in zip("ABCDEFGHIJ", [2, 30, 15, 2, 30, 15, 2, 30, 15, 2]): DB.column_dimensions[c].width = w
tiles = [
    ("B4", "C4", "Total loan value", f"=SUM({R('funded_amnt')})", MONEY_M),
    ("E4", "F4", "Number of loans", f"=COUNT({R('loan_id')})", INT),
    ("H4", "I4", "Default rate", f"=SUM({R('is_default')})/F4", PCT2),
    ("B6", "C6", "Delinquency rate (active loans)", f"=SUM({R('is_delinquent')})/SUM({R('is_active')})", PCT2),
    ("E6", "F6", "Average interest rate", f"=AVERAGE({R('int_rate')})", PCT2),
    ("H6", "I6", "At-risk loan value", f"=SUM({R('at_risk_amount')})", MONEY_M),
    ("B8", "C8", "Outstanding balance", f"=SUM({R('out_prncp')})", MONEY_M),
    ("E8", "F8", "At-risk share of outstanding", "=I6/C8", PCT),
    ("H8", "I8", "Principal lost to charge-offs", f"=SUM({R('principal_lost')})", MONEY_M),
    ("B10", "C10", "Lifetime default rate (matured loans)", f"=COUNTIFS({M},{R('is_default')},1)/COUNTIFS({M})", PCT2),
    ("E10", "F10", "Watchlist balance (model)", "=At_Risk!C7", MONEY_M),
    ("H10", "I10", "Total potentially at risk", "=At_Risk!D8", PCT),
]
for lr, vr, lab, f, fmt in tiles:
    put(DB, lr, lab, font=bold, fill=kpi_fill)
    c = put(DB, vr, f, fmt, Font(name=F, bold=True, size=14, color=NAVY), kpi_fill); c.alignment = Alignment(horizontal="right")
for r in (4, 6, 8, 10): DB.row_dimensions[r].height = 24
DB["B12"] = "Key findings"; DB["B12"].font = Font(name=F, bold=True, size=12, color=NAVY)
for i, t_ in enumerate([
    "1. Highest-default customers: FICO under 680, grades E-G, 3+ recent credit inquiries, income under $30K, loans outside credit policy.",
    "2. Riskiest loan type: small business (22% default, about 2x average). Debt consolidation is the largest exposure (53% of lending).",
    "3. Higher rates go with higher default (correlation about 0.95-0.98); pricing covers the risk for grades A-E but not grade F (see Rate_vs_Default).",
    "4. $7.6M (7.3%) of the outstanding balance is delinquent or in default; about 20% including the model's watchlist.",
    "5. The default rules in Policy_Simulator would have avoided ~49% of defaults while declining ~29% of lending, lifting net return from 7.2% to 9.7%.",
]):
    DB[f"B{13 + i}"] = t_; DB[f"B{13 + i}"].font = norm
note(DB, "B19", "Sheets: Segment_Explorer (pick any segment) | Loan_Types | Rate_vs_Default | Trend_Geography | At_Risk | Policy_Simulator | Loan_Data | Cleaning_Log")
ch = BarChart(); ch.type = "col"; ch.title = "Default rate by grade"; ch.style = 10
ch.add_data(Reference(RT, min_col=4, min_row=4, max_row=11), titles_from_data=True)
ch.set_categories(Reference(RT, min_col=1, min_row=5, max_row=11)); ch.legend = None
ch.series[0].graphicalProperties.solidFill = ORANGE; ch.y_axis.numFmt = "0%"; ch.dataLabels = vlabels(); ch.height, ch.width = 8, 13
DB.add_chart(ch, "B21")
ch = BarChart(); ch.type = "bar"; ch.title = "Default rate by loan type"; ch.style = 10
ch.add_data(Reference(T, min_col=5, min_row=4, max_row=4 + n), titles_from_data=True)
ch.set_categories(Reference(T, min_col=1, min_row=5, max_row=4 + n)); ch.legend = None; ch.x_axis.scaling.orientation = "maxMin"
ch.series[0].graphicalProperties.solidFill = BLUE; ch.y_axis.numFmt = "0%"; ch.height, ch.width = 8, 15
DB.add_chart(ch, "F21")

# ================================================================== README
RM = wb.create_sheet("README", 0)
title(RM, "Credit Risk & Loan Portfolio Analysis - Excel workbook", "42,535 real LendingClub loans (2007-2011), statuses at 17 Aug 2013.")
RM.column_dimensions["A"].width = 22; RM.column_dimensions["B"].width = 110
rows = [("Sheet", "What it does"),
        ("Dashboard", "The executive KPIs (total loan value, loans, default and delinquency rates, average rate, at-risk value) and key findings."),
        ("Segment_Explorer", "Pick any dimension (grade, FICO, income, DTI, rate, loan type, term, home ownership, region, model risk band)."),
        ("Loan_Types", "Default rate, losses and at-risk balance by loan type, plus 36- vs 60-month terms."),
        ("Rate_vs_Default", "Interest rate vs default by grade, and whether the extra interest covers the losses (matured loans)."),
        ("Trend_Geography", "Default rate by issue year (vintage) and by state."),
        ("At_Risk", "Delinquent, defaulted and watchlist balances; at-risk balance by grade."),
        ("Policy_Simulator", "EDIT the yellow rules to test stricter lending rules on matured loans."),
        ("Loan_Data", "One row per loan (Excel Table 'Loans'), including the Python model's risk score and band."),
        ("Cleaning_Log", "Every data check and fix applied to the original file."),
        ("", ""),
        ("Definitions", "Default = Charged Off or Default. Delinquent = active loan 1-120 days late. At-risk = outstanding balance of delinquent + defaulted loans."),
        ("Matured loans", "36-month loans issued by 17 Aug 2010: their full term has ended, so lifetime outcomes are known."),
        ("Formulas used", "COUNTIFS, SUMIFS, AVERAGEIFS, SUMPRODUCT-style helper column, INDEX/MATCH (incl. INDEX(range,0,col) for the explorer), RANK, CORREL."),
        ("Colour key", "Yellow + blue text = inputs. Orange shading = higher risk; green = safer / favourable.")]
for i, (a, b) in enumerate(rows):
    r = 4 + i; RM[f"A{r}"], RM[f"B{r}"] = a, b
    RM[f"A{r}"].font = h_font if i == 0 else bold; RM[f"B{r}"].font = h_font if i == 0 else norm
    if i == 0: RM[f"A{r}"].fill = RM[f"B{r}"].fill = h_fill

for ws_ in wb.worksheets:
    for chart in ws_._charts:
        for s_ in getattr(chart, "series", []): s_.smooth = False
RM.sheet_properties.tabColor = "52514E"; DB.sheet_properties.tabColor = NAVY; P.sheet_properties.tabColor = "EDA100"
wb.active = 1
path = OUT / "loan_portfolio_risk.xlsx"; wb.save(path); print("saved", path)
