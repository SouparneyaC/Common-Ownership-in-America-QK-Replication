import os
import sqlite3
import numpy as np
import pandas as pd

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outputs")
DB_PATH    = os.path.join(DATA_DIR, "holdings.db")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_quarter_from_db(year, quarter):
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query(
        """SELECT issuer_cik, issuer_name, issuer_ticker, issuer_sic,
                  filer_cik, filer_name, shares_held
           FROM holdings
           WHERE year = ? AND quarter = ?""",
        conn, params=(year, quarter)
    )
    conn.close()
    return df.rename(columns={
        "issuer_cik":    "issuerCik",
        "issuer_name":   "issuerName",
        "issuer_ticker": "issuerTicker",
        "issuer_sic":    "issuerSIC",
        "filer_cik":     "filerCik",
        "filer_name":    "filerName",
        "shares_held":   "shrsOrPrnAmt",
    })


def list_available_quarters():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT DISTINCT year, quarter, COUNT(*) as n_firms
           FROM completed_firms
           GROUP BY year, quarter
           ORDER BY year, quarter"""
    ).fetchall()
    conn.close()
    return rows


def compute_kappa_for_quarter(df_quarter):
    # Build β_fs = shares_held / total_institutional_shares (simplified, no retail correction)
    # κ_fg = B'B[f,g] / diag(B'B)[f]  where B is the investors × firms ownership matrix
    firm_totals = (df_quarter
                   .groupby("issuerCik")["shrsOrPrnAmt"]
                   .sum()
                   .rename("total_inst_shares"))

    df_q = df_quarter.merge(firm_totals, on="issuerCik")
    df_q["beta"] = df_q["shrsOrPrnAmt"] / df_q["total_inst_shares"]

    beta_matrix = df_q.pivot_table(
        index="filerCik",
        columns="issuerCik",
        values="beta",
        aggfunc="sum",
        fill_value=0.0
    )

    B         = beta_matrix.values
    firm_ciks = list(beta_matrix.columns)
    n_firms   = len(firm_ciks)

    print(f"    Matrix: {B.shape[0]:,} investors × {n_firms} firms")

    BTB      = B.T @ B
    diag_BTB = np.diag(BTB)

    with np.errstate(divide="ignore", invalid="ignore"):
        kappa_matrix = np.where(
            diag_BTB[:, None] > 0,
            BTB / diag_BTB[:, None],
            0.0
        )

    rows = [
        {"cik_f": cik_f, "cik_g": cik_g, "kappa": kappa_matrix[i, j]}
        for i, cik_f in enumerate(firm_ciks)
        for j, cik_g in enumerate(firm_ciks)
        if i != j
    ]
    return pd.DataFrame(rows), beta_matrix, firm_ciks


def add_firm_metadata(kappa_df, df_quarter):
    meta = (df_quarter
            .drop_duplicates("issuerCik")
            [["issuerCik", "issuerTicker", "issuerName", "issuerSIC"]]
            .set_index("issuerCik"))

    kappa_df = kappa_df.join(
        meta.rename(columns={c: c + "_f" for c in meta.columns}), on="cik_f"
    )
    kappa_df = kappa_df.join(
        meta.rename(columns={c: c + "_g" for c in meta.columns}), on="cik_g"
    )

    kappa_df["same_sic4"] = kappa_df["issuerSIC_f"] == kappa_df["issuerSIC_g"]
    kappa_df["same_sic2"] = (
        (kappa_df["issuerSIC_f"] // 100) == (kappa_df["issuerSIC_g"] // 100)
    ).where(kappa_df["issuerSIC_f"].notna() & kappa_df["issuerSIC_g"].notna())

    return kappa_df


if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}. Run 01_pull_data.py first.")
    raise SystemExit(1)

available    = list_available_quarters()
summary_rows = []

print(f"Quarters available: {[(y, q) for y, q, _ in available]}\n")

for year, quarter, n_firms in available:
    label       = f"{year}Q{quarter}"
    output_path = os.path.join(OUTPUT_DIR, f"kappa_{label}.csv")

    print(f"Processing {label} ({n_firms} firms)...")

    if os.path.exists(output_path):
        existing  = pd.read_csv(output_path)
        avg_kappa = existing["kappa"].mean()
        print(f"  Already computed — avg κ = {avg_kappa:.4f}. Skipping.")
        summary_rows.append({
            "quarter_label": label, "year": year, "quarter": quarter,
            "avg_kappa": avg_kappa,
            "avg_kappa_within": existing[existing["same_sic2"] == True]["kappa"].mean(),
            "avg_kappa_cross":  existing[existing["same_sic2"] == False]["kappa"].mean(),
            "n_pairs": len(existing), "n_firms": existing["cik_f"].nunique(),
        })
        continue

    df_q     = load_quarter_from_db(year, quarter)
    print(f"  Loaded: {df_q['issuerCik'].nunique()} firms, {len(df_q):,} rows")

    kappa_df, _, _ = compute_kappa_for_quarter(df_q)
    kappa_df       = add_firm_metadata(kappa_df, df_q)
    kappa_df["quarter_label"] = label
    kappa_df["year"]          = year
    kappa_df["quarter"]       = quarter

    kappa_df.to_csv(output_path, index=False)
    print(f"  Saved: {len(kappa_df):,} pairs")

    avg_kappa = kappa_df["kappa"].mean()
    within    = kappa_df[kappa_df["same_sic2"] == True]["kappa"].mean()
    cross     = kappa_df[kappa_df["same_sic2"] == False]["kappa"].mean()
    print(f"  avg κ: {avg_kappa:.4f}  (within {within:.4f}, cross {cross:.4f})")

    summary_rows.append({
        "quarter_label": label, "year": year, "quarter": quarter,
        "avg_kappa": avg_kappa, "avg_kappa_within": within, "avg_kappa_cross": cross,
        "n_pairs": len(kappa_df), "n_firms": kappa_df["cik_f"].nunique(),
    })

summary_df = pd.DataFrame(summary_rows).sort_values("year")
summary_df.to_csv(os.path.join(OUTPUT_DIR, "kappa_summary_by_quarter.csv"), index=False)

print("\nSummary across all quarters:")
print(summary_df[["quarter_label", "avg_kappa", "avg_kappa_within",
                   "avg_kappa_cross", "n_firms"]].to_string(index=False))
print("\nDone. Run 03_make_plots.py to generate figures.")
