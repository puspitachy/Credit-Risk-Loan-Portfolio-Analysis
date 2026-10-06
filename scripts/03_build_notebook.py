"""
03_build_notebook.py
Writes notebooks/credit_risk_analysis.ipynb. Execute afterwards with:
  jupyter nbconvert --to notebook --execute --inplace notebooks/credit_risk_analysis.ipynb
Insight text (written after reviewing results) comes from scripts/notebook_insights.json.
"""
import json
import nbformat as nbf
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "scripts" / "notebook_insights.json"
INS = json.loads(P.read_text()) if P.exists() else {}
nb = nbf.v4.new_notebook(); C = []
md = lambda s: C.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: C.append(nbf.v4.new_code_cell(s.strip()))
insight = lambda k: md(INS.get(k, "**Insight:** _(see output above)_"))

md("""
# Credit Risk & Loan Portfolio Analysis
### Real LendingClub loans (2007–2011) · Python notebook

**Business problem:** a lender wants to understand the health of its loan portfolio, find the higher-risk customer segments, and see where losses may come from.

**Data:** 42,535 real consumer loans issued by LendingClub, Jun 2007 – Dec 2011 ($460M), with each loan's status and balance at the **snapshot date, 17 Aug 2013**.

| Term | Definition used here |
|---|---|
| **Default** | Loan status *Charged Off* or *Default* |
| **Delinquent** | Active loan *In Grace Period* or *Late* (1–120 days past due) |
| **At-risk loan value** | Principal still outstanding on delinquent + defaulted loans |
| **Matured loans** | 36-month loans issued on or before 17 Aug 2010: their full term ended before the snapshot, so their final outcome is known (no partial-life bias) |

**Workflow:** SQL (database + risk queries) → **Python (EDA, drivers, default-risk model)** → Excel (portfolio workbook + policy simulator) → Power BI (executive dashboard)
""")

md("## 1. Setup and load from the SQL database")
code("""
import sqlite3, warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.inspection import permutation_importance
warnings.filterwarnings("ignore")

BASE = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
IMG = BASE / "images"; IMG.mkdir(exist_ok=True)
pd.set_option("display.float_format", "{:,.2f}".format)
BLUE, ORANGE, AQUA, GRAY, INK = "#2a78d6", "#eb6834", "#1baf7a", "#b5b4ae", "#52514e"
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#e6e5e0", "grid.linewidth": 0.8, "axes.axisbelow": True, "axes.titleweight": "bold",
                     "axes.titlesize": 12, "axes.edgecolor": GRAY, "font.size": 10})
pctf = mtick.PercentFormatter(1.0, decimals=0)
def save(fig, name):
    fig.tight_layout(); fig.savefig(IMG / f"{name}.png", dpi=150, bbox_inches="tight")

con = sqlite3.connect(BASE / "data" / "credit_risk.db")
df = pd.read_sql("SELECT * FROM vw_loans", con, parse_dates=["issue_date"])
df["matured"] = ((df.term_months == 36) & (df.issue_date <= "2010-08-17")).astype(int)
print(df.shape); df.head(3)
""")

md("## 2. Data checks\nThe original file was checked and cleaned by `scripts/01_prepare_data.py`.")
code("""
display(pd.read_csv(BASE / "data" / "clean" / "cleaning_log.csv"))
print("Loans:", len(df), "| unique IDs:", df.loan_id.nunique(), "| missing FICO:", df.fico_score.isna().sum())
""")

md("## 3. Portfolio health at a glance")
code("""
active = df[df.is_active == 1]
kpi = pd.Series({
    "Total loan value (funded)": f"${df.funded_amnt.sum()/1e6:,.1f}M",
    "Number of loans": f"{len(df):,}",
    "Default rate (all loans, at snapshot)": f"{df.is_default.mean():.2%}",
    "Lifetime default rate (matured loans)": f"{df[df.matured == 1].is_default.mean():.2%}",
    "Delinquency rate (active loans)": f"{active.is_delinquent.mean():.2%}",
    "Average interest rate": f"{df.int_rate.mean():.2%}",
    "Outstanding balance": f"${df.out_prncp.sum()/1e6:,.1f}M",
    "At-risk loan value (delinquent + defaulted balance)": f"${df.at_risk_amount.sum()/1e6:,.2f}M",
    "At-risk share of outstanding": f"{df.at_risk_amount.sum()/df.out_prncp.sum():.1%}",
    "Principal already lost to charge-offs": f"${df.principal_lost.sum()/1e6:,.1f}M",
})
display(kpi.to_frame("value"))

st = df.groupby("status_group").agg(loans=("loan_id", "size"), outstanding=("out_prncp", "sum"))
order = ["Closed - repaid", "Active - current", "Active - delinquent", "Defaulted"]
st = st.reindex(order)
fig, ax = plt.subplots(1, 2, figsize=(13, 3.8))
cols = [GRAY, BLUE, ORANGE, "#c0392b"]
ax[0].barh(order[::-1], st.loans[::-1], color=cols[::-1], height=0.6)
for i, v in enumerate(st.loans[::-1]): ax[0].text(v, i, f" {v:,} ({v/len(df):.1%})", va="center", color=INK)
ax[0].set(title="Loans by status at 17 Aug 2013", xlabel="Loans"); ax[0].set_xlim(0, st.loans.max() * 1.35)
ob = st.outstanding.drop("Closed - repaid")
ax[1].barh(ob.index[::-1], ob[::-1] / 1e6, color=cols[1:][::-1], height=0.6)
for i, v in enumerate(ob[::-1]): ax[1].text(v / 1e6, i, f" ${v/1e6:,.1f}M", va="center", color=INK)
ax[1].set(title="Outstanding balance by status", xlabel="$ millions"); ax[1].set_xlim(0, ob.max() / 1e6 * 1.25)
save(fig, "01_portfolio_status"); plt.show()
""")
insight("health")

md("## 4. Which customers default most?")
code("""
def rate(col, data=df, min_n=100):
    g = data.groupby(col).agg(loans=("loan_id", "size"), default_rate=("is_default", "mean"))
    return g[g.loans >= min_n]

panels = [("grade", "Grade (A = best)"), ("fico_band", "FICO credit score"), ("income_band", "Annual income"),
          ("dti_band", "Debt-to-income"), ("emp_band", "Employment length"), ("home_ownership", "Home ownership")]
fig, axes = plt.subplots(2, 3, figsize=(15, 7.5))
overall = df.is_default.mean()
for ax, (col, ttl) in zip(axes.flat, panels):
    r = rate(col)
    labels = [str(x).split(". ", 1)[-1] for x in r.index]
    ax.bar(labels, r.default_rate, color=[ORANGE if v > overall else BLUE for v in r.default_rate], width=0.65)
    ax.axhline(overall, color=INK, ls="--", lw=1)
    ax.yaxis.set_major_formatter(pctf); ax.set_title(ttl); ax.tick_params(axis="x", labelsize=8, rotation=20)
axes[0, 0].text(-0.4, overall * 1.04, f"portfolio {overall:.1%}", color=INK, fontsize=8)
fig.suptitle("Default rate by customer segment (orange = above portfolio average)", fontweight="bold", y=1.0)
save(fig, "02_default_by_segment"); plt.show()

seg = pd.concat({c: rate(c) for c, _ in panels})
print("Highest-default customer segments (min. 100 loans):")
display(seg.sort_values("default_rate", ascending=False).head(8).style.format({"default_rate": "{:.1%}", "loans": "{:,}"}))
""")
insight("customers")

md("## 5. Which loan types carry the greatest risk?")
code("""
lt = df.groupby("loan_type").agg(loans=("loan_id", "size"), value=("funded_amnt", "sum"),
                                 default_rate=("is_default", "mean"), lost=("principal_lost", "sum"),
                                 at_risk=("at_risk_amount", "sum")).sort_values("default_rate")
lt["share_of_value"] = lt.value / lt.value.sum()
fig, ax = plt.subplots(1, 2, figsize=(14, 4.8))
ax[0].barh(lt.index, lt.default_rate, color=[ORANGE if v > overall else BLUE for v in lt.default_rate], height=0.65)
ax[0].axvline(overall, color=INK, ls="--", lw=1); ax[0].xaxis.set_major_formatter(pctf)
ax[0].set(title="Default rate by loan type")
l2 = lt.sort_values("lost")
ax[1].barh(l2.index, l2.lost / 1e6, color=BLUE, height=0.65)
ax[1].set(title="Principal lost to charge-offs by loan type", xlabel="$ millions")
save(fig, "03_loan_type_risk"); plt.show()

tm = df.groupby("term_months").agg(loans=("loan_id", "size"), default_rate=("is_default", "mean"),
                                   delinquency=("is_delinquent", "sum"), active=("is_active", "sum"),
                                   outstanding=("out_prncp", "sum"), at_risk=("at_risk_amount", "sum"))
tm["delinquency_rate"] = tm.delinquency / tm.active
tm["share_of_outstanding"] = tm.outstanding / tm.outstanding.sum()
tm["share_of_at_risk"] = tm.at_risk / tm.at_risk.sum()
display(tm[["loans", "default_rate", "delinquency_rate", "share_of_outstanding", "share_of_at_risk"]]
        .style.format({"loans": "{:,}", "default_rate": "{:.1%}", "delinquency_rate": "{:.1%}",
                       "share_of_outstanding": "{:.0%}", "share_of_at_risk": "{:.0%}"}))
""")
insight("loantypes")

md("""
## 6. Is a higher interest rate associated with higher default — and is it worth it?
Interest rates are set from the grade, so rate and default rise together. The real question for the business is whether the **extra interest covers the extra losses**. That can only be judged on **matured loans**, where every final outcome is known.
""")
code("""
mat = df[df.matured == 1]
sg = mat.groupby("sub_grade").agg(loans=("loan_id", "size"), rate=("int_rate", "mean"), dr=("is_default", "mean"))
sg = sg[sg.loans >= 50]
r_corr = np.corrcoef(sg.rate, sg.dr)[0, 1]
gr = mat.groupby("grade").agg(loans=("loan_id", "size"), rate=("int_rate", "mean"), dr=("is_default", "mean"),
                              paid=("total_pymnt", "sum"), funded=("funded_amnt", "sum"))
gr["net_return"] = gr.paid / gr.funded - 1

fig, ax = plt.subplots(1, 2, figsize=(14, 4.8))
ax[0].scatter(sg.rate, sg.dr, s=sg.loans / 6, color=BLUE, alpha=0.75, edgecolor="white", linewidth=1.5)
b = np.polyfit(sg.rate, sg.dr, 1); xs = np.linspace(sg.rate.min(), sg.rate.max(), 50)
ax[0].plot(xs, np.polyval(b, xs), color=ORANGE, lw=1.5, ls="--")
for s_, r_ in sg.iloc[::5].iterrows(): ax[0].annotate(s_, (r_.rate, r_.dr), xytext=(4, 4), textcoords="offset points", fontsize=8, color=INK)
ax[0].xaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0)); ax[0].yaxis.set_major_formatter(pctf)
ax[0].set(title=f"Interest rate vs lifetime default rate (sub-grades, r = {r_corr:.2f})",
          xlabel="Average interest rate", ylabel="Lifetime default rate")
ax[1].bar(gr.index, gr.net_return, color=[AQUA if v > 0 else ORANGE for v in gr.net_return], width=0.6)
ax[1].axhline(0, color=INK, lw=1); ax[1].yaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
for i, (g_, r_) in enumerate(gr.iterrows()):
    ax[1].text(i, r_.net_return + (0.004 if r_.net_return >= 0 else -0.004), f"{r_.net_return:+.1%}",
               ha="center", va="bottom" if r_.net_return >= 0 else "top", color=INK, fontsize=9)
ax[1].set_ylim(gr.net_return.min() - 0.02, gr.net_return.max() + 0.015)
ax[1].set(title="Lifetime net return by grade (matured loans)", ylabel="Cash returned / funded - 1")
save(fig, "04_rate_vs_default"); plt.show()
display(gr[["loans", "rate", "dr", "net_return"]].style.format({"loans": "{:,}", "rate": "{:.2%}", "dr": "{:.1%}", "net_return": "{:+.2%}"}))
""")
insight("rate")

md("## 7. Default trend over time and geography")
code("""
q = df.groupby("issue_quarter").agg(loans=("loan_id", "size"), dr=("is_default", "mean"), active=("is_active", "mean"))
fig, ax = plt.subplots(1, 2, figsize=(14, 4.4))
x = np.arange(len(q))
ax[0].plot(x, q.dr, color=ORANGE, lw=2, marker="o", ms=4, label="Default rate so far")
ax[0].plot(x, q.active, color=GRAY, lw=1.5, ls="--", label="Share still active")
ax[0].set_xticks(x[::2], q.index[::2], rotation=45, fontsize=8); ax[0].yaxis.set_major_formatter(pctf)
ax[0].legend(frameon=False); ax[0].set(title="Default rate by issue quarter (vintage)")

stt = df.groupby(["state", "state_name"]).agg(loans=("loan_id", "size"), dr=("is_default", "mean")).reset_index()
stt = stt[stt.loans >= 500].sort_values("dr")
ax[1].barh(stt.state, stt.dr, color=[ORANGE if v > overall else BLUE for v in stt.dr], height=0.7)
ax[1].axvline(overall, color=INK, ls="--", lw=1); ax[1].xaxis.set_major_formatter(pctf)
ax[1].set(title="Default rate by state (states with 500+ loans)"); ax[1].tick_params(axis="y", labelsize=8)
save(fig, "05_trend_and_geography"); plt.show()
reg = df.groupby("region").agg(loans=("loan_id", "size"), dr=("is_default", "mean"), at_risk=("at_risk_amount", "sum"))
display(reg.sort_values("dr", ascending=False).style.format({"loans": "{:,}", "dr": "{:.1%}", "at_risk": "${:,.0f}"}))
""")
insight("trend")

md("""
## 8. Default-risk model
**Goal:** score every loan with a probability of default (PD) from information known **when the loan was made**: credit score, income, debt-to-income, employment, home ownership, credit history, loan amount, term, purpose and interest rate. Nothing from after the loan was issued is used, so there is no leakage.

**Target — "bad within 24 months":** the standard credit-risk *performance window*. A loan is *bad* if it defaulted with its last payment within 24 months of issue. Every loan issued on or before 17 Aug 2011 has had a full 24 months to show this, so **36- and 60-month loans are judged on equal terms** (simply using finished loans would overstate 60-month risk, because their early endings are mostly defaults). Data: 75% train / 25% test, stratified.
""")
code("""
df["last_payment_date"] = pd.to_datetime(df.last_payment_date)
res = df[df.issue_date <= "2011-08-17"].copy()
res["bad_24m"] = ((res.is_default == 1) & (res.last_payment_date.isna() |
                  (res.last_payment_date <= res.issue_date + pd.DateOffset(months=24)))).astype(int)
print(f"{len(res):,} loans with a full 24-month window; bad within 24 months: {res.bad_24m.mean():.1%}")
print(res.groupby("term_months").bad_24m.mean().map("{:.1%}".format).to_string())
def features(d):
    X = pd.DataFrame({
        "fico_score": d.fico_score, "log_income": np.log1p(d.annual_inc), "dti": d.dti,
        "emp_length_years": d.emp_length_years, "inq_last_6mths": d.inq_last_6mths, "revol_util": d.revol_util,
        "delinq_2yrs": d.delinq_2yrs, "pub_rec": d.pub_rec, "credit_history_years": d.credit_history_years,
        "log_amount": np.log(d.funded_amnt), "loan_to_income": d.funded_amnt / d.annual_inc.replace(0, np.nan),
        "int_rate": d.int_rate, "term_60": (d.term_months == 60).astype(int),
        "home_ownership": d.home_ownership, "loan_type": d.loan_type,
    })
    return X
num = ["fico_score", "log_income", "dti", "emp_length_years", "inq_last_6mths", "revol_util", "delinq_2yrs", "pub_rec",
       "credit_history_years", "log_amount", "loan_to_income", "int_rate", "term_60"]
cat = ["home_ownership", "loan_type"]
X, y = features(res), res.bad_24m
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)

pre = ColumnTransformer([("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num),
                         ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=50), cat)])
models = {
    "Logistic regression": Pipeline([("pre", pre), ("m", LogisticRegression(max_iter=2000, C=0.5))]),
    "Gradient boosting": Pipeline([("pre", pre), ("m", HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                                                                       max_leaf_nodes=15, l2_regularization=1.0,
                                                                                       random_state=42))]),
}
auc, probs = {}, {}
for n, m in models.items():
    m.fit(X_tr, y_tr); probs[n] = m.predict_proba(X_te)[:, 1]; auc[n] = roc_auc_score(y_te, probs[n])
grade_auc = roc_auc_score(y_te, res.loc[X_te.index, "grade"].map({g: i for i, g in enumerate("ABCDEFG")}))
fico_auc = roc_auc_score(y_te, -res.loc[X_te.index, "fico_score"])
comp = pd.Series({**auc, "LendingClub grade alone": grade_auc, "FICO score alone": fico_auc}).sort_values(ascending=False)
display(comp.to_frame("ROC-AUC (test set)").style.format("{:.3f}"))

fig, ax = plt.subplots(figsize=(6, 5))
for (n, p), c in zip(probs.items(), [BLUE, ORANGE]):
    f, t, _ = roc_curve(y_te, p); ax.plot(f, t, color=c, lw=2, label=f"{n} (AUC {auc[n]:.3f})")
ax.plot([0, 1], [0, 1], color=GRAY, ls="--", lw=1, label="Random (0.500)")
ax.set(title="ROC curve — test set", xlabel="False positive rate", ylabel="True positive rate"); ax.legend(frameon=False, loc="lower right")
save(fig, "06_roc_curve"); plt.show()
""")
code("""
best_name = max(auc, key=auc.get); best = models[best_name]
print("Model used for scoring:", best_name)
# lift table: test loans split into 10 equal groups by predicted risk
t = pd.DataFrame({"p": probs[best_name], "y": y_te.values})
t["decile"] = pd.qcut(t.p.rank(method="first"), 10, labels=range(1, 11))
lift = t.groupby("decile", observed=True).agg(loans=("y", "size"), actual_default=("y", "mean"), avg_score=("p", "mean"))
lift["capture"] = t.groupby("decile", observed=True).y.sum()[::-1].cumsum()[::-1] / t.y.sum()
display(lift.style.format({"actual_default": "{:.1%}", "avg_score": "{:.1%}", "capture": "{:.0%}"}))
top20 = t[t.decile.astype(int) >= 9].y.sum() / t.y.sum(); low20 = t[t.decile.astype(int) <= 2].y.sum() / t.y.sum()
print(f"Riskiest 20% of test loans hold {top20:.0%} of all test-set defaults; safest 20% hold {low20:.0%}")

# what drives the model? (logistic regression, easy to explain)
lr = models["Logistic regression"]
names = num + list(lr.named_steps["pre"].named_transformers_["cat"].get_feature_names_out(cat))
coef = pd.Series(lr.named_steps["m"].coef_[0], index=names)
label = {"fico_score": "FICO score", "log_income": "Income", "dti": "Debt-to-income", "emp_length_years": "Years employed",
         "inq_last_6mths": "Credit inquiries (6m)", "revol_util": "Revolving credit used", "delinq_2yrs": "Past delinquencies",
         "pub_rec": "Public records", "credit_history_years": "Credit history length", "log_amount": "Loan amount",
         "loan_to_income": "Loan-to-income", "int_rate": "Interest rate", "term_60": "60-month term"}
odds = np.exp(coef[num]).rename(index=label).sort_values()
fig, ax = plt.subplots(1, 2, figsize=(14, 5))
ax[0].barh(odds.index, odds.values - 1, left=1, color=[ORANGE if v > 1 else AQUA for v in odds.values], height=0.65)
ax[0].axvline(1, color=INK, lw=1)
ax[0].set(title="Borrower & loan factors: odds of default\\nper 1 standard deviation increase", xlabel="Odds multiplier (1 = no effect)")
lt_coef = coef[[n for n in names if n.startswith("loan_type_")]]
base = lt_coef.get("loan_type_Debt Consolidation", 0)
lt_odds = np.exp(lt_coef - base).rename(lambda n: n.replace("loan_type_", "")).drop("Debt Consolidation", errors="ignore").sort_values()
ax[1].barh(lt_odds.index, lt_odds.values - 1, left=1, color=[ORANGE if v > 1 else AQUA for v in lt_odds.values], height=0.65)
ax[1].axvline(1, color=INK, lw=1)
ax[1].set(title="Loan type: odds of default vs Debt Consolidation\\n(same borrower profile)", xlabel="Odds multiplier")
save(fig, "07_default_drivers"); plt.show()
""")
insight("model")

md("""
## 9. How much of the portfolio is at risk?
Three layers of risk in the **$104M still outstanding** at the snapshot:
1. **Already in trouble:** delinquent or in default (the at-risk loan value).
2. **Watchlist:** loans still current but scoring as high as the riskiest 10% of test loans.
3. **Already lost:** principal written off on charged-off loans (history, not outstanding).
""")
code("""
df["risk_score"] = best.predict_proba(features(df))[:, 1]
# watchlist threshold = entry point of the riskiest 10% of test loans
cut = t.p.quantile(0.90)
print(f"Watchlist threshold: risk score >= {cut:.1%}")
df["risk_band"] = pd.cut(df.risk_score.rank(pct=True), [0, 0.4, 0.8, 0.95, 1.0],
                         labels=["Low", "Medium", "High", "Very high"]).astype(str)
df["watchlist"] = ((df.loan_status == "Current") & (df.risk_score >= cut)).astype(int)
act = df[df.is_active == 1]
chk = act.groupby("status_group").risk_score.mean()
print("Sanity check on loans the model never saw as outcomes: average score")
print(chk.map("{:.1%}".format).to_string())

layers = pd.Series({
    "Delinquent (1-120 days late)": act.loc[act.is_delinquent == 1, "out_prncp"].sum(),
    "In default (121+ days)": act.loc[act.loan_status == "Default", "out_prncp"].sum(),
    "Watchlist: current but high risk score": act.loc[act.watchlist == 1, "out_prncp"].sum(),
})
outstanding = act.out_prncp.sum()
tbl = layers.to_frame("outstanding"); tbl["share_of_outstanding"] = tbl.outstanding / outstanding
tbl.loc["Total potentially at risk"] = [layers.sum(), layers.sum() / outstanding]
display(tbl.style.format({"outstanding": "${:,.0f}", "share_of_outstanding": "{:.1%}"}))
print(f"Outstanding balance: ${outstanding/1e6:,.1f}M | already lost to charge-offs: ${df.principal_lost.sum()/1e6:,.1f}M "
      f"({df.principal_lost.sum()/df.funded_amnt.sum():.1%} of all money lent)")

fig, ax = plt.subplots(figsize=(10, 3.2))
left = 0
parts = [("Current, normal risk", outstanding - layers.sum(), GRAY), ("Watchlist", layers.iloc[2], "#eda100"),
         ("Delinquent", layers.iloc[0], ORANGE), ("Default", layers.iloc[1], "#c0392b")]
for lab, v, c in parts:
    ax.barh([0], [v / 1e6], left=left, color=c, height=0.5, edgecolor="white", linewidth=2)
    if v / outstanding > 0.03: ax.text(left + v / 2e6, 0, f"{lab}\\n${v/1e6:,.1f}M", ha="center", va="center", fontsize=9,
                                     color="white" if c != GRAY else INK)
    left += v / 1e6
ax.set_yticks([]); ax.set(title=f"Outstanding balance ${outstanding/1e6:,.1f}M: how much is at risk?", xlabel="$ millions")
ax.grid(axis="y", visible=False)
save(fig, "08_at_risk_layers"); plt.show()

wl = act[act.watchlist == 1]
print("Watchlist profile vs all current loans:")
display(pd.DataFrame({"Watchlist": [wl.fico_score.mean(), wl.int_rate.mean(), (wl.term_months == 60).mean(), wl.dti.mean(), len(wl)],
                      "All current": [act[act.loan_status == "Current"].fico_score.mean(), act[act.loan_status == "Current"].int_rate.mean(),
                                      (act[act.loan_status == "Current"].term_months == 60).mean(), act[act.loan_status == "Current"].dti.mean(),
                                      (act.loan_status == "Current").sum()]},
                     index=["Avg FICO", "Avg interest rate", "Share 60-month", "Avg DTI", "Loans"]).style.format("{:,.2f}"))
""")
insight("atrisk")

md("""
## 10. What if we tightened lending rules? (policy simulation on matured loans)
Each rule removes a group of past loans. On matured loans, where the full outcome is known, we compare **how much lending volume would be lost** with **how many defaults would be avoided** and what happens to the **net return** of the remaining book.
""")
code("""
rules = {
    "No rule (actual book)": pd.Series(False, index=mat.index),
    "Decline FICO < 660": mat.fico_score < 660,
    "Decline grades F-G": mat.grade.isin(["F", "G"]),
    "Decline 3+ inquiries in 6 months": mat.inq_last_6mths >= 3,
    "Decline small business loans": mat.loan_type == "Small Business",
    "Decline loans failing credit policy": mat.meets_credit_policy == 0,
    "Combined: F-G, 3+ inquiries, failing policy": mat.grade.isin(["F", "G"]) | (mat.inq_last_6mths >= 3) | (mat.meets_credit_policy == 0),
}
rows = []
for name, drop in rules.items():
    keep = mat[~drop]; gone = mat[drop]
    rows.append({"rule": name, "loans_declined_pct": drop.mean(),
                 "volume_declined": gone.funded_amnt.sum(),
                 "default_rate_after": keep.is_default.mean(),
                 "defaults_avoided_pct": gone.is_default.sum() / mat.is_default.sum(),
                 "default_rate_of_declined": gone.is_default.mean() if len(gone) else np.nan,
                 "net_return_after": keep.total_pymnt.sum() / keep.funded_amnt.sum() - 1,
                 "net_return_of_declined": gone.total_pymnt.sum() / gone.funded_amnt.sum() - 1 if len(gone) else np.nan})
pol = pd.DataFrame(rows).set_index("rule")
display(pol.style.format({"loans_declined_pct": "{:.1%}", "volume_declined": "${:,.0f}", "default_rate_after": "{:.2%}",
                          "defaults_avoided_pct": "{:.1%}", "default_rate_of_declined": "{:.1%}",
                          "net_return_after": "{:+.2%}", "net_return_of_declined": "{:+.2%}"}))
""")
insight("policy")

md("## 11. Save scores to the database and export for Power BI / Excel")
code("""
scores = df[["loan_id", "risk_score", "risk_band", "watchlist", "matured"]].copy()
scores["risk_score"] = scores.risk_score.round(4)
scores.to_sql("loan_risk_scores", con, if_exists="replace", index=False); con.commit()
out = BASE / "data" / "powerbi"; out.mkdir(exist_ok=True)
fact = df.drop(columns=["member_id"]).copy()
fact["issue_date"] = fact.issue_date.dt.strftime("%Y-%m-%d"); fact["risk_score"] = fact.risk_score.round(4)
fact.to_csv(out / "fact_loans.csv", index=False)
pd.read_sql("SELECT * FROM states", con).to_csv(out / "dim_state.csv", index=False)
pd.read_sql("SELECT * FROM loan_status_map", con).to_csv(out / "dim_loan_status.csv", index=False)
pd.DataFrame({"grade": list("ABCDEFG"), "grade_order": range(1, 8)}).to_csv(out / "dim_grade.csv", index=False)
pol.reset_index().to_csv(out / "policy_simulation.csv", index=False)
comp.rename("roc_auc").rename_axis("model").reset_index().to_csv(out / "model_comparison.csv", index=False)
lift.reset_index().to_csv(out / "model_lift_table.csv", index=False)
coef.rename("coefficient").rename_axis("feature").reset_index().to_csv(out / "model_coefficients.csv", index=False)
print(sorted(p.name for p in out.iterdir()))
""")

md(INS.get("summary", "## Summary\n_(written after review)_"))
nb["cells"] = C
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
p = ROOT / "notebooks" / "credit_risk_analysis.ipynb"; p.parent.mkdir(exist_ok=True)
nbf.write(nb, p); print("written", p)
