"""
SCRIPT 09: Compute κ and Plot Figure 1 — Common Ownership Over Time
=====================================================================
Replicates Figure 1 of Backus, Conlon & Sinkinson (2019) using our
9-firm dataset: AAPL, MSFT, AAL, DAL, JPM, BAC, PFE, MRK, NVDA.

WHAT THIS SCRIPT DOES:
  1. Loads institutional holdings + shares outstanding
  2. Computes β_fs = shares_held / total_shares_outstanding  (proper version)
  3. For each quarter, computes κ_fg for every firm pair (f ≠ g):
         κ_fg = Σ_s(β_fs × β_gs) / Σ_s(β_fs²)
  4. Computes mean κ across all pairs per quarter
  5. Plots the time series — our Figure 1 replica

OUTPUT:
  plots/fig1_kappa_timeseries.png
  data/kappa_9firms.csv
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from itertools import combinations

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

BASE        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE, "..", "data")
PLOTS_DIR   = os.path.join(BASE, "..", "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)

HOLDINGS_CSV = os.path.join(DATA_DIR, "holdings_9firms.csv")
SHARES_CSV   = os.path.join(DATA_DIR, "shares_outstanding_9firms.csv")
KAPPA_CSV    = os.path.join(DATA_DIR, "kappa_9firms.csv")
PLOT_PATH    = os.path.join(PLOTS_DIR, "fig1_kappa_timeseries.png")

# Industry mapping for pair labels
SIC = {
    "AAPL": 3571, "MSFT": 7372,
    "AAL":  4512, "DAL":  4512,
    "JPM":  6021, "BAC":  6021,
    "PFE":  2834, "MRK":  2834,
    "NVDA": 3674,
}

# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────

print("Loading data...")
holdings = pd.read_csv(HOLDINGS_CSV, dtype={"filer_cik": str})
shares   = pd.read_csv(SHARES_CSV)

# Ensure numeric
holdings["shares_held"] = pd.to_numeric(holdings["shares_held"], errors="coerce")
shares["shares"]        = pd.to_numeric(shares["shares"], errors="coerce")

print(f"  Holdings rows:  {len(holdings):,}")
print(f"  Shares rows:    {len(shares):,}")

# ─────────────────────────────────────────────────────────────────────────────
# COMPUTE κ FOR EVERY PAIR × EVERY QUARTER
# ─────────────────────────────────────────────────────────────────────────────

tickers = sorted(holdings["ticker"].unique())
pairs   = list(combinations(tickers, 2))   # 36 unordered pairs from 9 firms
quarters = sorted(holdings[["year","quarter"]].drop_duplicates().values.tolist())

print(f"\nFirms:    {tickers}")
print(f"Pairs:    {len(pairs)}")
print(f"Quarters: {len(quarters)}")
print("\nComputing κ...")

records = []

for year, quarter in quarters:
    # Filter holdings and shares for this quarter
    h_q = holdings[(holdings.year == year) & (holdings.quarter == quarter)]
    s_q = shares[(shares.year == year) & (shares.quarter == quarter)]

    # Build β vectors: β_fs = shares_held / total_shares_outstanding
    beta = {}
    retail = {}
    ihhi = {}

    for ticker in tickers:
        h_f = h_q[h_q.ticker == ticker]
        s_f = s_q[s_q.ticker == ticker]

        if h_f.empty or s_f.empty:
            continue

        total_shares = s_f["shares"].iloc[0]
        if total_shares <= 0:
            continue

        # Aggregate across sub-managers by filer_cik
        agg = h_f.groupby("filer_cik")["shares_held"].sum()
        beta_f = agg / total_shares

        # Cap β at 1 per investor (data sanity)
        beta_f = beta_f.clip(upper=1.0)

        # Retail share = fraction not held by institutions
        inst_share = beta_f.sum()
        r_f = max(0.0, 1.0 - inst_share)

        beta[ticker]   = beta_f
        retail[ticker] = r_f
        ihhi[ticker]   = (beta_f ** 2).sum()

    # Compute κ for each pair
    for f, g in pairs:
        if f not in beta or g not in beta:
            continue

        b_f = beta[f]
        b_g = beta[g]

        # Align on common investor universe (fill missing with 0)
        all_investors = b_f.index.union(b_g.index)
        b_f_aligned   = b_f.reindex(all_investors, fill_value=0.0)
        b_g_aligned   = b_g.reindex(all_investors, fill_value=0.0)

        numerator   = np.dot(b_f_aligned.values, b_g_aligned.values)
        denominator = np.dot(b_f_aligned.values, b_f_aligned.values)   # IHHI_f

        if denominator <= 0:
            continue

        kappa_fg = numerator / denominator  # f's profit weight on g
        kappa_gf = numerator / np.dot(b_g_aligned.values, b_g_aligned.values)

        # Cosine similarity (decomposition component)
        norm_f = np.linalg.norm(b_f_aligned.values)
        norm_g = np.linalg.norm(b_g_aligned.values)
        cosine = (numerator / (norm_f * norm_g)) if (norm_f > 0 and norm_g > 0) else 0.0

        same_sic = int(SIC.get(f, -1) == SIC.get(g, -2))

        records.append({
            "year":      year,
            "quarter":   quarter,
            "firm_f":    f,
            "firm_g":    g,
            "kappa_fg":  round(kappa_fg, 6),
            "kappa_gf":  round(kappa_gf, 6),
            "ihhi_f":    round(ihhi.get(f, 0), 8),
            "ihhi_g":    round(ihhi.get(g, 0), 8),
            "retail_f":  round(retail.get(f, 0), 4),
            "retail_g":  round(retail.get(g, 0), 4),
            "cosine":    round(cosine, 6),
            "same_sic":  same_sic,
        })

kappa_df = pd.DataFrame(records)
kappa_df.to_csv(KAPPA_CSV, index=False)
print(f"  Saved {len(kappa_df):,} pair-quarter rows → {KAPPA_CSV}")

# ─────────────────────────────────────────────────────────────────────────────
# FIGURE 1 — Mean κ across all pairs over time
# ─────────────────────────────────────────────────────────────────────────────

# Use symmetric κ: average of κ_fg and κ_gf for each pair
kappa_df["kappa_sym"] = (kappa_df["kappa_fg"] + kappa_df["kappa_gf"]) / 2

# Time axis: decimal year (e.g. 2013.75 for Q3)
kappa_df["time"] = kappa_df["year"] + (kappa_df["quarter"] - 0.5) / 4

# Mean across all pairs per quarter
mean_all = kappa_df.groupby("time")["kappa_sym"].mean().reset_index()

# Within-industry pairs (same SIC)
mean_within = (kappa_df[kappa_df.same_sic == 1]
               .groupby("time")["kappa_sym"].mean().reset_index())

# Cross-industry pairs
mean_cross = (kappa_df[kappa_df.same_sic == 0]
              .groupby("time")["kappa_sym"].mean().reset_index())

print("\nPlotting Figure 1...")

fig, ax = plt.subplots(figsize=(13, 7))
fig.subplots_adjust(bottom=0.22)   # room for caption below

ax.plot(mean_all["time"],    mean_all["kappa_sym"],
        color="#1f77b4", linewidth=2.5, label="All pairs (mean κ)")
ax.plot(mean_within["time"], mean_within["kappa_sym"],
        color="#d62728", linewidth=2.0, linestyle="--",
        label="Same industry (AAL–DAL, JPM–BAC, PFE–MRK)")
ax.plot(mean_cross["time"],  mean_cross["kappa_sym"],
        color="#ff7f0e", linewidth=2.0, linestyle=":",
        label="Different industry")

# Reference lines
ax.axhline(0.0, color="black", linewidth=0.5, alpha=0.4)
ax.axhline(1.0, color="black", linewidth=0.8, linestyle="--", alpha=0.5,
           label="κ = 1  (merger equivalent / full collusion)")

# Shade COVID period
ax.axvspan(2020.0, 2020.75, alpha=0.10, color="steelblue")
ax.text(2020.05, 1.32, "COVID-19", fontsize=8, color="steelblue", va="top")

# Mark key events with vertical lines + labels at top
events = {
    2016.75: "NVDA GPU\nboom",
    2023.25: "ChatGPT /\nAI boom",
}
for t, label in events.items():
    ax.axvline(t, color="gray", linewidth=0.9, linestyle=":", alpha=0.7)
    ax.text(t + 0.05, 1.32, label, fontsize=8, color="gray", va="top")

ax.set_xlim(2013.5, 2026.2)
ax.set_ylim(0, 1.45)           # expanded headroom above κ = 1
ax.set_xlabel("Year", fontsize=12)
ax.set_ylabel("κ  (common ownership profit weight)", fontsize=12)
ax.set_title(
    "Common Ownership Profit Weights — 9 S&P 500 Firms, 2013Q3–2025Q4\n"
    "Replication of Backus, Conlon & Sinkinson (2019) Figure 1",
    fontsize=13, fontweight="bold", pad=10
)
ax.legend(loc="upper left", fontsize=9.5, framealpha=0.9)
ax.grid(axis="y", alpha=0.3)

# Caption below the plot (outside axes)
caption = (
    "Notes: Mean implied profit weight κ across all pairs of firms in the sample by quarter. "
    "κ = 0 indicates normal competition; κ = 1 is equivalent to a full merger (or collusion). "
    "Sample: 9 S&P 500 firms — AAPL, MSFT (Tech), AAL, DAL (Airlines), JPM, BAC (Banks), "
    "PFE, MRK (Pharma), NVDA (Semiconductors). "
    "β_fs computed as shares held / total shares outstanding from SEC EDGAR XBRL. "
    "Data source: QUANTkiosk 13(F) institutional holdings."
)
fig.text(0.5, 0.02, caption, ha="center", va="bottom", fontsize=8,
         color="#444444", wrap=True,
         bbox=dict(boxstyle="round,pad=0.4", facecolor="#f8f8f8",
                   edgecolor="#cccccc", alpha=0.8),
         transform=fig.transFigure)

plt.savefig(PLOT_PATH, dpi=150, bbox_inches="tight")
plt.show()
print(f"\nSaved → {PLOT_PATH}")

# ─────────────────────────────────────────────────────────────────────────────
# QUICK SUMMARY TABLE
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Mean κ by period ===")
kappa_df["period"] = pd.cut(
    kappa_df["year"],
    bins=[2012, 2015, 2018, 2021, 2025],
    labels=["2013–2015", "2016–2018", "2019–2021", "2022–2025"]
)
print(kappa_df.groupby("period")["kappa_sym"].mean().round(3).to_string())

print("\n=== Latest quarter κ for each pair ===")
latest = kappa_df[kappa_df["time"] == kappa_df["time"].max()]
print(latest[["firm_f","firm_g","kappa_fg","kappa_gf","retail_f","cosine","same_sic"]]
      .sort_values("kappa_fg", ascending=False)
      .to_string(index=False))
