"""
Credit Risk & Loan Default Analysis - end-to-end pipeline.

Steps
  1. Load Lending Club loans into DuckDB (only application-time fields + outcome)
  2. Clean and analyze default drivers in SQL (grade, purpose, income x FICO, year, state)
  3. Train a logistic regression baseline and an XGBoost model to predict default
  4. Segment borrowers into 5 risk tiers and estimate expected loss
  5. Export an Excel risk report, a Tableau-ready sample, charts, and a results summary

Run from the project root:
    python src/run_pipeline.py
"""
from pathlib import Path
import time

import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, roc_curve
from xgboost import XGBClassifier

from excel_utils import write_sheet

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "credit.duckdb"
SQL_DIR = ROOT / "sql"
OUT = ROOT / "outputs"
IMG = ROOT / "images"

LGD = 0.60   # Loss Given Default assumption: 60% of the loan amount is lost when a borrower defaults
RAW_COLS = ["id", "loan_amnt", "term", "int_rate", "installment", "grade", "sub_grade", "emp_length",
            "home_ownership", "annual_inc", "verification_status", "issue_d", "loan_status", "purpose",
            "addr_state", "dti", "delinq_2yrs", "fico_range_low", "fico_range_high", "open_acc",
            "pub_rec", "revol_util", "total_acc"]
NUM_FEATURES = ["loan_amnt", "term_months", "int_rate", "installment", "emp_years", "annual_inc", "dti",
                "delinq_2yrs", "fico", "open_acc", "pub_rec", "revol_util", "total_acc", "loan_to_income"]
CAT_FEATURES = ["grade", "home_ownership", "verification_status", "purpose"]
TIER_LABELS = ["1 Very Low", "2 Low", "3 Medium", "4 High", "5 Very High"]

plt.rcParams.update({"figure.dpi": 120, "axes.spines.top": False, "axes.spines.right": False,
                     "font.size": 10})
NAVY, RED, GREY = "#1F3864", "#C0392B", "#B0B7C3"


def sql(name):
    return (SQL_DIR / name).read_text()


def fmt(v):
    if isinstance(v, (int, np.integer)):
        return f"{v:,}"
    if isinstance(v, (float, np.floating)):
        return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}"
    return str(v)


def to_md(df):
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(fmt(v) for v in row) + " |")
    return "\n".join(lines)


def find_raw_file():
    candidates = sorted(list(RAW_DIR.glob("accepted*.csv*")) + list(RAW_DIR.glob("*.csv.gz"))
                        + list(RAW_DIR.glob("*.csv")))
    if not candidates:
        raise FileNotFoundError(
            f"No loan file found in {RAW_DIR}. Download the Lending Club dataset from Kaggle and "
            "put accepted_2007_to_2018Q4.csv.gz in data/raw/ (see data/README.md).")
    return candidates[0]


def load_data(con):
    raw = find_raw_file()
    print(f"Loading {raw.name} into DuckDB (all columns as text, then typed in SQL) ...")
    cols = ", ".join(RAW_COLS)
    con.execute(f"""
        CREATE OR REPLACE TABLE loans_raw AS
        SELECT {cols}
        FROM read_csv('{raw.as_posix()}', header=true, all_varchar=true,
                      ignore_errors=true, null_padding=true)
    """)
    con.execute(sql("01_clean.sql"))
    n_raw = con.execute("SELECT COUNT(*) FROM loans_raw").fetchone()[0]
    n = con.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
    print(f"  {n_raw:,} raw rows -> {n:,} finished loans with known outcomes")
    return n_raw


def run_sql_analysis(con):
    print("Running SQL analysis ...")
    names = ["02_portfolio_summary", "03_default_by_grade", "04_default_by_purpose",
             "05_default_by_income_fico", "06_default_by_year", "07_default_by_state"]
    return {n[3:]: con.sql(sql(f"{n}.sql")).df() for n in names}


def build_features(df):
    df = df.copy()
    df["loan_to_income"] = df["loan_amnt"] / df["annual_inc"]
    X = pd.get_dummies(df[NUM_FEATURES + CAT_FEATURES], columns=CAT_FEATURES, drop_first=True, dtype=float)
    X[NUM_FEATURES] = X[NUM_FEATURES].fillna(X[NUM_FEATURES].median())
    return X, df["is_default"].astype(int)


def train_models(con):
    print("Training models ...")
    df = con.sql("SELECT * FROM loans").df()
    X, y = build_features(df)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    # Model A: logistic regression - the interpretable baseline credit teams expect
    scaler = StandardScaler().fit(X_train)
    lr = LogisticRegression(max_iter=2000, class_weight="balanced")
    lr.fit(scaler.transform(X_train), y_train)
    lr_score = lr.predict_proba(scaler.transform(X_test))[:, 1]

    # Model B: XGBoost - captures non-linear effects and interactions
    pos = y_train.sum()
    xgb = XGBClassifier(n_estimators=400, max_depth=5, learning_rate=0.05, subsample=0.8,
                        colsample_bytree=0.8, tree_method="hist",
                        scale_pos_weight=(len(y_train) - pos) / pos,
                        eval_metric="auc", random_state=42, n_jobs=-1)
    xgb.fit(X_train, y_train)
    xgb_score = xgb.predict_proba(X_test)[:, 1]

    results = {"lr_auc": roc_auc_score(y_test, lr_score), "xgb_auc": roc_auc_score(y_test, xgb_score),
               "n_train": len(X_train), "n_test": len(X_test), "y_test": y_test,
               "lr_score": lr_score, "xgb_score": xgb_score}

    # scale_pos_weight inflates raw scores, so rescale to the true default rate for expected-loss math
    calib = y_train.mean() / xgb.predict_proba(X_train)[:, 1].mean()
    pd_est = np.clip(xgb_score * calib, 0, 1)

    tiers = pd.DataFrame({"loan_amnt": X_test["loan_amnt"].values, "score": xgb_score,
                          "pd_estimate": pd_est, "actual_default": y_test.values})
    tiers["risk_tier"] = pd.qcut(tiers["score"], 5, labels=TIER_LABELS)
    tiers["expected_loss"] = tiers["pd_estimate"] * tiers["loan_amnt"] * LGD
    tier_table = (tiers.groupby("risk_tier", observed=True)
                  .agg(loans=("score", "size"), volume=("loan_amnt", "sum"),
                       predicted_pd_pct=("pd_estimate", "mean"),
                       actual_default_pct=("actual_default", "mean"),
                       expected_loss=("expected_loss", "sum"))
                  .reset_index())
    tier_table["predicted_pd_pct"] = (100 * tier_table["predicted_pd_pct"]).round(2)
    tier_table["actual_default_pct"] = (100 * tier_table["actual_default_pct"]).round(2)
    tier_table["expected_loss"] = tier_table["expected_loss"].round(0)
    tier_table["volume"] = tier_table["volume"].round(0)

    importance = (pd.Series(xgb.feature_importances_, index=X.columns).sort_values(ascending=False)
                  .head(15).rename("importance").reset_index().rename(columns={"index": "feature"}))
    lr_coef = (pd.Series(lr.coef_[0], index=X.columns).sort_values(key=abs, ascending=False)
               .head(15).round(3).rename("coefficient").reset_index().rename(columns={"index": "feature"}))
    return df, results, tier_table, importance, lr_coef


def export_excel(tables, tier_table, importance, lr_coef, results):
    print("Writing Excel report ...")
    models = pd.DataFrame({"model": ["Logistic regression", "XGBoost"],
                           "test_auc": [round(results["lr_auc"], 4), round(results["xgb_auc"], 4)],
                           "train_rows": [results["n_train"]] * 2, "test_rows": [results["n_test"]] * 2})
    money = {"volume": "$#,##0", "total_volume": "$#,##0", "avg_loan": "$#,##0",
             "expected_loss": "$#,##0", "loans": "#,##0"}
    path = OUT / "credit_risk_report.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        write_sheet(xw, tables["portfolio_summary"], "Portfolio Summary", money)
        write_sheet(xw, tier_table, "Risk Tiers", money, color_scale_cols=["actual_default_pct"])
        write_sheet(xw, tables["default_by_grade"], "By Grade", money, color_scale_cols=["default_rate_pct"])
        write_sheet(xw, tables["default_by_purpose"], "By Purpose", money, color_scale_cols=["default_rate_pct"])
        write_sheet(xw, tables["default_by_income_fico"], "Income x FICO", money,
                    color_scale_cols=["default_rate_pct"])
        write_sheet(xw, tables["default_by_year"], "By Year", money)
        write_sheet(xw, tables["default_by_state"], "By State", money, color_scale_cols=["default_rate_pct"])
        write_sheet(xw, models, "Model Comparison")
        write_sheet(xw, importance, "XGB Feature Importance")
        write_sheet(xw, lr_coef, "Logistic Coefficients")
        notes = pd.DataFrame({"assumption": ["Loss Given Default (LGD)", "Scope", "Test set"],
                              "value": [f"{LGD:.0%} of loan amount lost on default",
                                        "Finished loans only (Fully Paid / Charged Off)",
                                        "Random 20% stratified hold-out"]})
        write_sheet(xw, notes, "Assumptions")
    return path


def make_charts(tables, results, tier_table, importance):
    print("Saving charts ...")
    g = tables["default_by_grade"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(g["grade"], g["default_rate_pct"], color=NAVY)
    for x, v in zip(g["grade"], g["default_rate_pct"]):
        ax.text(x, v, f"{v:.1f}%", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Default rate %"); ax.set_xlabel("Lending Club grade")
    ax.set_title("Default rate by credit grade", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(IMG / "default_by_grade.png"); plt.close(fig)

    yr = tables["default_by_year"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.bar(yr["issue_year"].astype(int).astype(str), yr["volume"] / 1e9, color=GREY, label="Volume ($B)")
    ax.set_ylabel("Loan volume ($B)")
    ax2 = ax.twinx()
    ax2.plot(yr["issue_year"].astype(int).astype(str), yr["default_rate_pct"], color=RED, marker="o",
             label="Default rate %")
    ax2.set_ylabel("Default rate %"); ax2.spines["top"].set_visible(False)
    ax.set_ylim(0, (yr["volume"] / 1e9).max() * 1.3)
    ax2.set_ylim(0, yr["default_rate_pct"].max() * 1.3)
    ax.set_title("Loan volume and default rate by issue year (finished loans)", loc="left", fontweight="bold")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", ncol=2, frameon=False)
    fig.tight_layout(); fig.savefig(IMG / "volume_default_by_year.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.6))
    x = np.arange(len(tier_table))
    ax.bar(x - 0.2, tier_table["predicted_pd_pct"], 0.4, color=NAVY, label="Predicted default %")
    ax.bar(x + 0.2, tier_table["actual_default_pct"], 0.4, color=RED, label="Actual default %")
    ax.set_xticks(x, tier_table["risk_tier"].astype(str))
    ax.set_ylabel("%"); ax.legend(frameon=False)
    ax.set_title("Risk tiers: predicted vs actual default (test set)", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(IMG / "risk_tiers.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 4.5))
    for name, score, color in [("Logistic regression", results["lr_score"], GREY),
                               ("XGBoost", results["xgb_score"], NAVY)]:
        fpr, tpr, _ = roc_curve(results["y_test"], score)
        auc = roc_auc_score(results["y_test"], score)
        ax.plot(fpr, tpr, color=color, label=f"{name} (AUC {auc:.3f})")
    ax.plot([0, 1], [0, 1], ls="--", color="black", lw=0.8)
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
    ax.set_title("ROC curve (test set)", loc="left", fontweight="bold"); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(IMG / "roc_curve.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.2))
    imp = importance.head(12).sort_values("importance")
    ax.barh(imp["feature"], imp["importance"], color=NAVY)
    ax.set_title("Top default drivers (XGBoost importance)", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(IMG / "feature_importance.png"); plt.close(fig)


def write_summary(n_raw, tables, results, tier_table, importance):
    s = tables["portfolio_summary"].iloc[0]
    low, high = tier_table.iloc[0], tier_table.iloc[-1]
    top3 = ", ".join(importance["feature"].head(3))
    best_name, best_auc = max([("logistic regression", results["lr_auc"]), ("XGBoost", results["xgb_auc"])],
                              key=lambda t: t[1])
    ratio = high["actual_default_pct"] / max(low["actual_default_pct"], 0.01)
    text = f"""# Results summary (auto-generated by src/run_pipeline.py)

| Metric | Value |
|---|---|
| Raw loan records | {n_raw:,} |
| Finished loans analyzed | {int(s.loans):,} |
| Loan volume | ${s.total_volume:,.0f} |
| Overall default rate | {s.default_rate_pct}% |
| Logistic regression AUC (test) | {results['lr_auc']:.3f} |
| XGBoost AUC (test) | {results['xgb_auc']:.3f} |
| Default rate, lowest-risk tier | {low.actual_default_pct}% |
| Default rate, highest-risk tier | {high.actual_default_pct}% ({ratio:.1f}x the lowest tier) |
| Top 3 drivers | {top3} |

### Risk tiers (test set, LGD = {LGD:.0%})
{to_md(tier_table)}

## Resume bullets (numbers filled in from this run)
- Analyzed {s.loans/1e6:.1f}M+ consumer loan records using SQL and Python to identify key drivers of default across credit grade, income, FICO, and loan purpose.
- Built and compared logistic regression and XGBoost default prediction models ({best_name} best, {best_auc:.2f} AUC), and segmented borrowers into 5 risk tiers ranging from {low.actual_default_pct:.1f}% to {high.actual_default_pct:.1f}% actual default rates.
- Estimated expected loss by risk tier and delivered an Excel risk report and dashboard-ready dataset covering portfolio risk, default trends, and segment performance.
"""
    (OUT / "results_summary.md").write_text(text)
    return text


def update_readme(summary_text):
    readme = ROOT / "README.md"
    start, end = "<!-- RESULTS_START -->", "<!-- RESULTS_END -->"
    text = readme.read_text()
    if start in text and end in text:
        body = summary_text.split("\n", 2)[2].split("## Resume bullets")[0].strip()
        readme.write_text(text.split(start)[0] + start + "\n" + body + "\n" + end + text.split(end)[1])


def main():
    t0 = time.time()
    OUT.mkdir(exist_ok=True); IMG.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    n_raw = load_data(con)
    tables = run_sql_analysis(con)
    loans, results, tier_table, importance, lr_coef = train_models(con)

    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
    tier_table.to_csv(OUT / "risk_tiers.csv", index=False)
    importance.to_csv(OUT / "feature_importance.csv", index=False)

    # Tableau-ready sample (keeps the file small enough for Tableau Public and GitHub)
    cols = ["issue_date", "grade", "sub_grade", "purpose", "addr_state", "home_ownership", "loan_amnt",
            "int_rate", "annual_inc", "fico", "dti", "term_months", "is_default"]
    loans[cols].sample(min(100_000, len(loans)), random_state=1).to_csv(
        OUT / "loans_sample_for_tableau.csv", index=False)

    export_excel(tables, tier_table, importance, lr_coef, results)
    make_charts(tables, results, tier_table, importance)
    summary = write_summary(n_raw, tables, results, tier_table, importance)
    update_readme(summary)
    print("\n" + summary)
    con.close()
    print(f"Done in {time.time() - t0:.0f}s. See outputs/ and images/.")


if __name__ == "__main__":
    main()
