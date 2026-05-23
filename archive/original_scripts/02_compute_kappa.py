"""
SCRIPT 02: Compute Kappa (κ) From Holdings Data
=================================================

WHAT THIS SCRIPT DOES:
-----------------------
Takes the raw holdings data (downloaded in script 01) and computes
kappa (κ) for every pair of firms in each quarter.

QUICK RECAP OF WHAT κ MEANS:
------------------------------
κ_fg = "how much does firm f care about firm g's profits?"
  - κ = 0: Normal competition. f ignores g entirely.
  - κ = 1: Full collusion or merger equivalent. f values g's $1 as its own $1.
  - κ = 0.7: Firm f gives 70 cents of weight to every $1 earned by firm g.
             This is what the paper found for the average S&P500 pair by 2017.

THE FORMULA:
-------------
For two firms f and g, and all institutional investors s:

         sum_over_s( β_fs × β_gs )
κ_fg  =  ──────────────────────────
         sum_over_s( β_fs × β_fs )

where β_fs = shares held by investor s in firm f / total shares of firm f

NOTE ON SIMPLIFIED κ:
---------------------
Ideally β_fs = shares_held / total_shares_outstanding.
Computing this properly requires "total shares outstanding" from CRSP (a
financial database). We don't have CRSP, so we compute a SIMPLIFIED version:

    β_fs_simplified = shares_held_by_s / total_institutional_shares_of_f

This treats all shares as if they were held by institutions (no retail investors).
This UNDERSTATES the true κ by a factor of roughly (1-retail_share), but
preserves all the relative patterns we care about.

We then apply a RETAIL SHARE CORRECTION where possible:
    If we know total shares from an external source (or can estimate it),
    we multiply by 1/(1-retail_share_f) to adjust upward.

HOW TO RUN:
-----------
Make sure script 01 has already been run first (data must exist).
    python3 02_compute_kappa.py

Outputs saved to: ../outputs/
"""

import os
import sqlite3
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUTPUT_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outputs")
DB_PATH     = os.path.join(DATA_DIR, "holdings.db")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_quarter_from_db(year, quarter):
    """
    Loads one quarter of holdings from the SQLite database.
    Returns a DataFrame with columns:
        issuer_cik, issuer_name, issuer_ticker, issuer_sic,
        filer_cik, filer_name, shares_held
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT issuer_cik, issuer_name, issuer_ticker, issuer_sic,
               filer_cik, filer_name, shares_held
        FROM holdings
        WHERE year = ? AND quarter = ?
        """,
        conn,
        params=(year, quarter)
    )
    conn.close()
    # Rename to match the rest of the script's expected column names
    df = df.rename(columns={
        "issuer_cik":    "issuerCik",
        "issuer_name":   "issuerName",
        "issuer_ticker": "issuerTicker",
        "issuer_sic":    "issuerSIC",
        "filer_cik":     "filerCik",
        "filer_name":    "filerName",
        "shares_held":   "shrsOrPrnAmt",
    })
    return df


def list_available_quarters():
    """
    Returns a list of (year, quarter) tuples that have data in the DB.
    Only includes quarters where at least one firm is marked complete.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT DISTINCT year, quarter, COUNT(*) as n_firms
        FROM completed_firms
        GROUP BY year, quarter
        ORDER BY year, quarter
        """
    ).fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# CORE FUNCTION: Compute κ for all pairs in one quarter
# ─────────────────────────────────────────────────────────────────────────────

def compute_kappa_for_quarter(df_quarter):
    """
    Given a DataFrame of holdings for one quarter, compute κ for all firm pairs.

    INPUT DataFrame has these key columns:
        issuerCik    : the firm being held (e.g., "320193" for Apple)
        issuerTicker : e.g., "AAPL"
        issuerName   : e.g., "APPLE INC"
        issuerSIC    : industry code (e.g., 3674 for semiconductors)
        filerCik     : the investor (e.g., "884821" for Vanguard)
        shrsOrPrnAmt : shares held by this investor in this firm

    OUTPUT: A DataFrame with one row per firm PAIR (f, g) with column:
        kappa        : the κ value for that pair
        kappa_simple : κ without retail share correction (always available)
        retail_share_f, retail_share_g : if we can estimate these

    HOW THE COMPUTATION WORKS:
    ---------------------------
    Think of it as building a big matrix:
      - Rows = institutional investors (there are ~3,000-5,000)
      - Columns = firms (up to 500)
      - Each cell = β_fs = ownership fraction

    For each pair of columns (f, g), κ_fg = dot(col_f, col_g) / dot(col_f, col_f)

    In matrix language: κ = (B'B) / diag(B'B)
    where B is the ownership matrix.

    We compute this efficiently without looping through all 500×500=250,000 pairs.
    """

    # ── BUILD THE OWNERSHIP MATRIX ─────────────────────────────────────────

    # Step 1: For each firm, get total institutional shares
    # (this is our denominator for the simplified β)
    firm_totals = (df_quarter
                   .groupby("issuerCik")["shrsOrPrnAmt"]
                   .sum()
                   .rename("total_inst_shares"))

    # Step 2: Compute β_fs_simplified for each (investor, firm) pair
    # This is: shares_held / total_institutional_shares_for_that_firm
    df_q = df_quarter.merge(firm_totals, on="issuerCik")
    df_q["beta_simplified"] = df_q["shrsOrPrnAmt"] / df_q["total_inst_shares"]

    # Step 3: Pivot into a matrix
    # Rows = investors (filerCik), Columns = firms (issuerCik)
    # Missing values (investor doesn't hold firm) → 0
    # This creates the matrix B described above
    beta_matrix = df_q.pivot_table(
        index="filerCik",       # rows = investors
        columns="issuerCik",    # columns = firms
        values="beta_simplified",
        aggfunc="sum",          # in case of duplicates, sum them
        fill_value=0.0          # investors who don't hold a firm get 0
    )

    # The matrix is investors × firms (shape: ~4000 × 500)
    # We need firms × investors for the dot products
    B = beta_matrix.values      # numpy array for fast math

    firm_ciks = list(beta_matrix.columns)  # list of firm CIKs
    n_firms = len(firm_ciks)

    print(f"    Matrix shape: {B.shape[0]:,} investors × {n_firms} firms")

    # ── COMPUTE κ EFFICIENTLY ─────────────────────────────────────────────

    # For each pair (f, g):
    #   numerator   = sum_s(β_fs × β_gs) = dot product of column f and column g
    #   denominator = sum_s(β_fs × β_fs) = dot product of column f with itself

    # Computing all dot products at once:
    # B'B is a (firms × firms) matrix where entry [f,g] = sum_s(β_fs × β_gs)
    # This is the NUMERATOR for all pairs
    BTB = B.T @ B   # matrix multiplication: (n_firms × n_investors) × (n_investors × n_firms)
                    # result: n_firms × n_firms matrix

    # The diagonal of BTB gives sum_s(β_fs²) for each firm f
    # This is the DENOMINATOR for κ_fg
    diag_BTB = np.diag(BTB)   # shape: (n_firms,)

    # κ_fg = BTB[f,g] / diag_BTB[f]
    # (we divide each ROW by the firm's own denominator)
    # Using broadcasting: divide each row by the corresponding diagonal element
    with np.errstate(divide="ignore", invalid="ignore"):
        kappa_matrix = np.where(
            diag_BTB[:, None] > 0,           # avoid division by zero
            BTB / diag_BTB[:, None],          # κ_fg = BTB[f,g] / diag_BTB[f]
            0.0
        )

    print(f"    κ matrix computed: {n_firms} × {n_firms} = {n_firms**2:,} pairs")

    # ── BUILD OUTPUT DATAFRAME ─────────────────────────────────────────────

    # We want one row per pair (f, g) where f ≠ g
    # (excluding a firm's κ with itself, which is always 1 by definition)

    rows = []
    for i, cik_f in enumerate(firm_ciks):
        for j, cik_g in enumerate(firm_ciks):
            if i == j:
                continue   # skip self-pairs (κ_ff = 1 always, not interesting)

            kappa_val = kappa_matrix[i, j]

            rows.append({
                "cik_f":   cik_f,
                "cik_g":   cik_g,
                "kappa":   kappa_val,
                # We'll add names and industries next
            })

    kappa_df = pd.DataFrame(rows)
    return kappa_df, beta_matrix, firm_ciks


def add_firm_metadata(kappa_df, df_quarter):
    """
    Add firm names, tickers, and SIC codes to the kappa DataFrame.
    This makes the output human-readable (CIK numbers alone are opaque).
    """
    # Build a lookup: CIK → (name, ticker, SIC)
    meta = (df_quarter
            .drop_duplicates("issuerCik")
            [["issuerCik", "issuerTicker", "issuerName", "issuerSIC"]]
            .set_index("issuerCik"))

    # Add info for firm f
    kappa_df = kappa_df.join(
        meta.rename(columns={c: c+"_f" for c in meta.columns}),
        on="cik_f"
    )
    # Add info for firm g
    kappa_df = kappa_df.join(
        meta.rename(columns={c: c+"_g" for c in meta.columns}),
        on="cik_g"
    )

    # Add a flag: are f and g in the SAME industry?
    # We compare 4-digit SIC codes (same 4 digits = very similar industry)
    # and 2-digit SIC codes (same 2 digits = same broad sector)
    kappa_df["same_sic4"] = (
        kappa_df["issuerSIC_f"] == kappa_df["issuerSIC_g"]
    )
    kappa_df["same_sic2"] = (
        (kappa_df["issuerSIC_f"] // 100) == (kappa_df["issuerSIC_g"] // 100)
    ).where(
        kappa_df["issuerSIC_f"].notna() & kappa_df["issuerSIC_g"].notna()
    )

    return kappa_df


def compute_retail_share_proxy(df_quarter):
    """
    Estimate the retail share (fraction of shares NOT held by institutions)
    for each firm.

    WHY THIS MATTERS:
    The paper shows that retail share is the BIGGEST driver of κ variation
    across firms. Here's the intuition:

    If 80% of a company is held by individual retail investors (who don't
    vote or exert governance pressure), then the institutional 20% effectively
    controls 100% of governance decisions. This amplifies κ by a factor of
    1/(1 - retail_share).

    HOW WE ESTIMATE IT:
    We don't know total shares outstanding from QK. But we know:
      - Total institutional shares = sum of all 13(F) reported shares
      - True total shares = institutional shares / (1 - retail_share)

    We estimate: retail_share ≈ 1 - (institutional_shares / estimated_total)

    For S&P500 firms in 2020, typical institutional ownership is 70-85%.
    In 2013 it was lower (~65-75%). Without CRSP, we use a ROUGH estimate
    based on what the paper found:
      - Large-cap firms: ~75-80% institutional ownership (20-25% retail)
      - Mid-cap firms: ~65-75% institutional ownership (25-35% retail)

    This is an approximation. In a full replication you'd use CRSP shrout data.
    """
    # Total institutional shares per firm (from our 13F data)
    inst_shares = (df_quarter
                   .groupby(["issuerCik", "issuerTicker", "issuerName"])
                   ["shrsOrPrnAmt"].sum()
                   .reset_index()
                   .rename(columns={"shrsOrPrnAmt": "total_inst_shares"}))

    # We cannot compute TRUE retail share without total shares outstanding.
    # We record this as NaN — plots will show the simplified κ without correction.
    inst_shares["retail_share_approx"] = np.nan

    return inst_shares


# ─────────────────────────────────────────────────────────────────────────────
# MAIN: Process all quarters
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("COMPUTING KAPPA FOR ALL DOWNLOADED QUARTERS")
print("=" * 60)

if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}")
    print("Run 01_pull_data.py first.")
    raise SystemExit(1)

available = list_available_quarters()
print(f"Quarters available in DB: {[(y, q, n) for y, q, n in available]}\n")

# Will store the AVERAGE κ per quarter for the time-trend plot
summary_rows = []

for year, quarter, n_firms in available:
    quarter_label = f"{year}Q{quarter}"
    output_path   = os.path.join(OUTPUT_DIR, f"kappa_{quarter_label}.csv")

    print(f"\nProcessing {quarter_label} ({n_firms} firms in DB)...")

    # CHECKPOINT: Skip if already computed
    if os.path.exists(output_path):
        existing  = pd.read_csv(output_path)
        avg_kappa = existing["kappa"].mean()
        print(f"  Already computed — avg κ = {avg_kappa:.4f}. Skipping.")
        summary_rows.append({
            "quarter_label": quarter_label,
            "year": year,
            "quarter": quarter,
            "avg_kappa": avg_kappa,
            "avg_kappa_within_industry": existing[existing["same_sic2"] == True]["kappa"].mean(),
            "avg_kappa_across_industry": existing[existing["same_sic2"] == False]["kappa"].mean(),
            "n_pairs": len(existing),
            "n_firms": existing["cik_f"].nunique(),
        })
        continue

    # Load from database
    df_q = load_quarter_from_db(year, quarter)
    print(f"  Loaded: {df_q['issuerCik'].nunique()} firms, {len(df_q):,} rows")

    # Compute κ
    kappa_df, beta_matrix, firm_ciks = compute_kappa_for_quarter(df_q)

    # Add human-readable firm names and industry info
    kappa_df = add_firm_metadata(kappa_df, df_q)

    # Add the quarter label
    kappa_df["quarter_label"] = quarter_label
    kappa_df["year"] = int(quarter_label[:4])
    kappa_df["quarter"] = int(quarter_label[5])

    # Save the full pairwise κ matrix
    kappa_df.to_csv(output_path, index=False)
    print(f"  ✓ Saved: {len(kappa_df):,} firm pairs")

    # Compute summary statistics for this quarter
    avg_kappa = kappa_df["kappa"].mean()
    within_industry = kappa_df[kappa_df["same_sic2"] == True]["kappa"].mean()
    across_industry = kappa_df[kappa_df["same_sic2"] == False]["kappa"].mean()

    print(f"  Average κ (all pairs):         {avg_kappa:.4f}")
    print(f"  Average κ (within industry):   {within_industry:.4f}")
    print(f"  Average κ (across industries): {across_industry:.4f}")

    summary_rows.append({
        "quarter_label": quarter_label,
        "year": int(quarter_label[:4]),
        "quarter": int(quarter_label[5]),
        "avg_kappa": avg_kappa,
        "avg_kappa_within_industry": within_industry,
        "avg_kappa_across_industry": across_industry,
        "n_pairs": len(kappa_df),
        "n_firms": kappa_df["cik_f"].nunique(),
    })

# Save the summary table (one row per quarter — used for time-trend plot)
summary_df = pd.DataFrame(summary_rows).sort_values("year")
summary_path = os.path.join(OUTPUT_DIR, "kappa_summary_by_quarter.csv")
summary_df.to_csv(summary_path, index=False)

print("\n" + "=" * 60)
print("SUMMARY ACROSS ALL QUARTERS")
print("=" * 60)
print(summary_df[["quarter_label", "avg_kappa", "avg_kappa_within_industry",
                   "avg_kappa_across_industry", "n_firms"]].to_string(index=False))

print("\nDone! Run script 03_make_plots.py to generate figures.")
