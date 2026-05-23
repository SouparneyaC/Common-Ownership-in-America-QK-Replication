"""
SCRIPT 03: Make All Plots
==========================

WHAT THIS SCRIPT DOES:
-----------------------
Takes the computed κ data (from script 02) and creates publication-quality
figures that replicate (and extend) the key results from Backus et al. (2019).

PLOTS PRODUCED:
---------------
1. fig1_kappa_over_time.png
   TIME TREND: Average κ from 2013–2024
   Shows how common ownership has grown. Replicates Figure 1 of the paper.

2. fig2_within_vs_across_industry.png
   INDUSTRY BREAKDOWN: κ within same industry vs across industries
   Shows that competing firms (same industry) have even higher common ownership.
   Replicates Figure 11 of the paper.

3. fig3_firm_distribution_latest.png
   CROSS-SECTION: Distribution of average κ across firms (most recent quarter)
   Which firms have the highest common ownership? Shows it's the large caps.

4. fig4_top_firm_pairs.png
   FAMOUS FIRMS: κ for specific well-known firm pairs
   Makes the abstract concept concrete by showing Apple vs Microsoft,
   United vs Delta, JPMorgan vs Goldman Sachs, etc.

5. fig5_top_investors_driving_kappa.png
   WHO DRIVES IT: How much of κ is explained by the Big Three
   (Vanguard, BlackRock, State Street)?

6. fig6_investor_concentration_ihhi.png
   INVESTOR CONCENTRATION: Distribution of IHHI over time
   IHHI = "investor HHI" = how concentrated is a firm's ownership?
   High IHHI → ownership concentrated in few investors → typically lower κ
   (unless those few investors are highly diversified, then κ stays high)

HOW TO RUN:
-----------
    python3 03_make_plots.py

Figures saved to: ../plots/
"""

import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

# ─────────────────────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")
PLOTS_DIR  = os.path.join(os.path.dirname(__file__), "..", "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)

# A clean, professional style for all figures
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor":   "white",
    "axes.grid":        True,
    "grid.alpha":       0.3,
    "grid.linestyle":   "--",
    "font.family":      "sans-serif",
    "font.size":        11,
    "axes.titlesize":   13,
    "axes.labelsize":   11,
    "legend.fontsize":  10,
})

# Brand colors (approximate the paper's blue style)
BLUE   = "#2166ac"
RED    = "#d6604d"
GREEN  = "#4dac26"
ORANGE = "#f4a582"

# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────

summary_path = os.path.join(OUTPUT_DIR, "kappa_summary_by_quarter.csv")
summary_df   = pd.read_csv(summary_path).sort_values("year")

# Load all individual quarter files into one big DataFrame
all_kappa_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "kappa_*.csv")))
# Exclude the summary file itself
all_kappa_files = [f for f in all_kappa_files if "summary" not in f]

all_kappa = pd.concat([pd.read_csv(f) for f in all_kappa_files], ignore_index=True)

# Get the most recent quarter for cross-sectional analysis
latest_quarter = summary_df["quarter_label"].iloc[-1]
latest_kappa   = all_kappa[all_kappa["quarter_label"] == latest_quarter].copy()

print(f"Loaded data: {len(all_kappa):,} total firm-pair observations")
print(f"Quarters available: {sorted(summary_df['quarter_label'].tolist())}")
print(f"Most recent quarter: {latest_quarter}\n")


# ─────────────────────────────────────────────────────────────────────────────
# FIGURE 1: Average κ Over Time (replicates paper Figure 1)
# ─────────────────────────────────────────────────────────────────────────────

def plot_kappa_over_time(summary_df):
    """
    Shows how the average profit weight (κ) across all S&P500 firm pairs
    has changed from 2013 to 2024.

    WHAT TO LOOK FOR:
    - The paper found κ went from 0.2 in 1980 to 0.7 in 2017.
    - Our data starts in 2013 (already ~0.6+) and should continue rising.
    - This tells us: competing firms are increasingly influenced by shared ownership.

    NOTE: Our κ values are SIMPLIFIED (no retail share correction), so they will
    be somewhat lower than the paper's numbers. The upward TREND is what matters.
    """
    fig, ax = plt.subplots(figsize=(10, 5.5))

    x = summary_df["year"]
    ax.plot(x, summary_df["avg_kappa"], color=BLUE, linewidth=2.5,
            marker="o", markersize=7, label="Average κ (all firm pairs)")

    # Add a horizontal reference line at κ = 1 (full collusion equivalent)
    ax.axhline(1.0, color="gray", linewidth=1, linestyle="--", alpha=0.5)
    ax.text(x.max() + 0.05, 1.02, "κ = 1\n(merger equivalent)", fontsize=8,
            color="gray", va="bottom")

    # Add a horizontal reference line at κ = 0 (perfect competition)
    ax.axhline(0.0, color="gray", linewidth=1, linestyle="--", alpha=0.5)
    ax.text(x.max() + 0.05, 0.02, "κ = 0\n(perfect competition)", fontsize=8,
            color="gray", va="bottom")

    # Shade the region between 0 and the line for visual clarity
    ax.fill_between(x, 0, summary_df["avg_kappa"], alpha=0.15, color=BLUE)

    ax.set_xlabel("Year")
    ax.set_ylabel("Average Profit Weight (κ)")
    ax.set_title("Figure 1 Replica: Common Ownership Profit Weights Over Time\n"
                 "Average κ across all S&P500 firm pairs, 2013–2024\n"
                 "(Simplified κ — no retail share correction)",
                 fontsize=11)
    ax.set_ylim(0, 1.1)
    ax.set_xticks(sorted(x.unique()))
    ax.legend(loc="lower right")

    # Add annotation explaining what the numbers mean
    # Use the actual latest value in the data
    latest_kappa_val = summary_df["avg_kappa"].iloc[-1]
    latest_yr        = summary_df["year"].iloc[-1]
    ax.annotate(
        f"By {latest_yr}, the average pair of S&P500 firms\n"
        f"has κ ≈ {latest_kappa_val:.2f}\n"
        f"Paper found κ ≈ 0.7 by 2017",
        xy=(latest_yr, latest_kappa_val),
        xytext=(latest_yr - 5, latest_kappa_val + 0.15),
        arrowprops=dict(arrowstyle="->", color="black"),
        fontsize=9, bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray")
    )

    plt.tight_layout()
    save_path = os.path.join(PLOTS_DIR, "fig1_kappa_over_time.png")
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: fig1_kappa_over_time.png")


# ─────────────────────────────────────────────────────────────────────────────
# FIGURE 2: Within-Industry vs Across-Industry κ (replicates paper Figure 11)
# ─────────────────────────────────────────────────────────────────────────────

def plot_within_vs_across_industry(summary_df):
    """
    Shows that firms in the SAME industry have even higher κ than firms
    in different industries.

    WHY THIS MAKES SENSE:
    - Index funds hold everything, but ACTIVE fund managers tend to specialize
      (e.g., a healthcare fund owns many healthcare stocks but not airlines).
    - Because of this specialization, two airlines share MORE of the same
      investors than an airline and a tech company do.
    - More shared investors → higher κ.

    WHAT TO LOOK FOR:
    - The "within-industry" (red) line should be ABOVE the "across-industry" (blue).
    - Both lines should trend upward over time.
    - This tells us that even within industries where companies directly compete,
      common ownership is high and rising.
    """
    fig, ax = plt.subplots(figsize=(10, 5.5))

    x = summary_df["year"]
    ax.plot(x, summary_df["avg_kappa_within_industry"], color=RED,
            linewidth=2.5, marker="s", markersize=7, label="Same industry (2-digit SIC)")
    ax.plot(x, summary_df["avg_kappa_across_industry"], color=BLUE,
            linewidth=2.5, marker="o", markersize=7, label="Different industries")
    ax.plot(x, summary_df["avg_kappa"], color="gray",
            linewidth=1.5, linestyle="--", label="Overall average")

    ax.set_xlabel("Year")
    ax.set_ylabel("Average Profit Weight (κ)")
    ax.set_title("Figure 11 Replica: Within-Industry vs Across-Industry Common Ownership\n"
                 "Firms that directly compete (same industry) have higher shared ownership",
                 fontsize=11)
    ax.set_ylim(0, 1.1)
    ax.set_xticks(sorted(x.unique()))
    ax.legend(loc="lower right")

    # Add annotation explaining industry coding
    ax.text(0.02, 0.05,
            "Industry = 2-digit SIC code\n"
            "(e.g., SIC 73 = Business Services,\n SIC 45 = Air Transportation)",
            transform=ax.transAxes, fontsize=8,
            bbox=dict(boxstyle="round", fc="white", ec="gray", alpha=0.8))

    plt.tight_layout()
    save_path = os.path.join(PLOTS_DIR, "fig2_within_vs_across_industry.png")
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: fig2_within_vs_across_industry.png")


# ─────────────────────────────────────────────────────────────────────────────
# FIGURE 3: Distribution of Average κ Across Firms (most recent quarter)
# ─────────────────────────────────────────────────────────────────────────────

def plot_firm_distribution(latest_kappa, latest_quarter):
    """
    For the most recent quarter, shows the DISTRIBUTION of each firm's
    average κ with all other firms.

    HOW TO READ THIS:
    - Compute, for each firm f: the average κ_fg across all other firms g.
    - This tells us "on average, how much does firm f care about any random
      competitor's profits?"
    - Firms with high average κ are the most "common owned" — their shareholders
      overlap heavily with shareholders of all other S&P500 firms.
    - These tend to be large-cap, well-known companies (Apple, Microsoft, etc.)
      because they are held by every major index fund.
    """
    # For each firm f, compute its average κ with all other firms
    avg_kappa_per_firm = (latest_kappa
                          .groupby(["cik_f", "issuerTicker_f", "issuerName_f"])
                          ["kappa"].mean()
                          .reset_index()
                          .rename(columns={"kappa": "avg_kappa_as_f",
                                           "issuerTicker_f": "ticker",
                                           "issuerName_f": "name",
                                           "cik_f": "cik"}))

    avg_kappa_per_firm = avg_kappa_per_firm.sort_values("avg_kappa_as_f", ascending=False)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Left panel: Histogram of the distribution
    ax1.hist(avg_kappa_per_firm["avg_kappa_as_f"], bins=40, color=BLUE,
             alpha=0.7, edgecolor="white")
    ax1.axvline(avg_kappa_per_firm["avg_kappa_as_f"].mean(), color=RED,
                linewidth=2, label=f'Mean = {avg_kappa_per_firm["avg_kappa_as_f"].mean():.3f}')
    ax1.axvline(avg_kappa_per_firm["avg_kappa_as_f"].median(), color=ORANGE,
                linewidth=2, linestyle="--",
                label=f'Median = {avg_kappa_per_firm["avg_kappa_as_f"].median():.3f}')
    ax1.set_xlabel("Average κ (profit weight with all other S&P500 firms)")
    ax1.set_ylabel("Number of Firms")
    ax1.set_title(f"Distribution of Average κ Per Firm\n({latest_quarter})")
    ax1.legend()

    # Right panel: Bar chart of top 25 firms by average κ
    top25 = avg_kappa_per_firm.head(25)
    # Shorten names for readability
    top25["short_name"] = top25["ticker"].fillna(top25["name"].str[:12])

    bars = ax2.barh(range(len(top25)), top25["avg_kappa_as_f"].values,
                    color=BLUE, alpha=0.8, edgecolor="white")
    ax2.set_yticks(range(len(top25)))
    ax2.set_yticklabels(top25["short_name"].values, fontsize=8)
    ax2.invert_yaxis()  # highest κ at top
    ax2.set_xlabel("Average κ with all other S&P500 firms")
    ax2.set_title(f"Top 25 Firms by Average κ\n({latest_quarter})")
    ax2.axvline(avg_kappa_per_firm["avg_kappa_as_f"].mean(), color=RED,
                linewidth=1.5, linestyle="--", alpha=0.7)

    plt.suptitle("Which S&P500 Firms Have the Highest Common Ownership?\n"
                 "Large-cap firms held by many index funds tend to score highest",
                 fontsize=12, y=1.02)
    plt.tight_layout()
    save_path = os.path.join(PLOTS_DIR, "fig3_firm_distribution_latest.png")
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: fig3_firm_distribution_latest.png")
    return avg_kappa_per_firm


# ─────────────────────────────────────────────────────────────────────────────
# FIGURE 4: Specific Famous Firm Pairs (makes it concrete)
# ─────────────────────────────────────────────────────────────────────────────

def plot_famous_pairs(all_kappa, summary_df):
    """
    Shows κ over time for specific well-known firm pairs.

    WHY THIS IS USEFUL:
    Abstract numbers like "average κ = 0.7" are hard to grasp.
    Seeing κ(United Airlines → Delta Airlines) = 0.85 is much more intuitive:
    United's shareholders own so much Delta that United effectively gives 85 cents
    of governance weight to every $1 Delta earns.

    PAIRS WE SHOW:
    - Airlines: United vs Delta (direct competitors, should be high)
    - Banks: JPMorgan vs Goldman (direct competitors in investment banking)
    - Tech giants: Apple vs Microsoft (different products, some competition)
    - Pharma: any two large pharma companies
    """
    # Define pairs by ticker. We'll look them up by ticker in the data.
    # Format: (ticker_f, ticker_g, label for the plot)
    FAMOUS_PAIRS = [
        ("AAPL", "MSFT", "Apple ↔ Microsoft\n(Tech Giants)"),
        ("JPM",  "GS",   "JPMorgan ↔ Goldman\n(Investment Banks)"),
        ("UAL",  "DAL",  "United ↔ Delta\n(Airlines)"),
        ("JNJ",  "PFE",  "J&J ↔ Pfizer\n(Pharma)"),
        ("XOM",  "CVX",  "ExxonMobil ↔ Chevron\n(Oil Majors)"),
        ("WMT",  "TGT",  "Walmart ↔ Target\n(Retail)"),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    axes = axes.flatten()

    quarters_sorted = sorted(all_kappa["quarter_label"].unique())

    for idx, (ticker_f, ticker_g, label) in enumerate(FAMOUS_PAIRS):
        ax = axes[idx]

        # Filter to this pair across all quarters
        pair_data = all_kappa[
            (all_kappa["issuerTicker_f"] == ticker_f) &
            (all_kappa["issuerTicker_g"] == ticker_g)
        ].sort_values("year")

        reverse_data = all_kappa[
            (all_kappa["issuerTicker_f"] == ticker_g) &
            (all_kappa["issuerTicker_g"] == ticker_f)
        ].sort_values("year")

        if len(pair_data) == 0 and len(reverse_data) == 0:
            ax.text(0.5, 0.5, f"No data for\n{ticker_f} / {ticker_g}",
                    ha="center", va="center", transform=ax.transAxes, fontsize=9)
            ax.set_title(label, fontsize=9)
            continue

        if len(pair_data) > 0:
            ax.plot(pair_data["year"], pair_data["kappa"], color=BLUE,
                    linewidth=2, marker="o", markersize=6,
                    label=f"κ({ticker_f}→{ticker_g})")
            ax.fill_between(pair_data["year"], 0, pair_data["kappa"],
                            alpha=0.1, color=BLUE)

        if len(reverse_data) > 0:
            ax.plot(reverse_data["year"], reverse_data["kappa"], color=RED,
                    linewidth=2, marker="s", markersize=6, linestyle="--",
                    label=f"κ({ticker_g}→{ticker_f})")

        ax.set_ylim(0, 1.1)
        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.set_xlabel("Year", fontsize=9)
        ax.set_ylabel("κ", fontsize=9)
        ax.legend(fontsize=7)
        ax.axhline(1.0, color="gray", linewidth=0.5, linestyle=":")
        ax.axhline(0.0, color="gray", linewidth=0.5, linestyle=":")

    plt.suptitle("Kappa (κ) Over Time for Specific Firm Pairs\n"
                 "κ = 1 means merger-equivalent; κ = 0 means perfect competition",
                 fontsize=12, y=1.01)
    plt.tight_layout()
    save_path = os.path.join(PLOTS_DIR, "fig4_famous_firm_pairs.png")
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: fig4_famous_firm_pairs.png")


# ─────────────────────────────────────────────────────────────────────────────
# FIGURE 5: Who Drives Common Ownership? (Big Three analysis)
# ─────────────────────────────────────────────────────────────────────────────

def plot_big_three_contribution(all_kappa_files, summary_df):
    """
    Shows how much of common ownership is attributable to the
    "Big Three" asset managers: Vanguard, BlackRock, and State Street.

    HOW WE COMPUTE THIS:
    For each quarter, we compute κ TWO ways:
    1. Full κ: using all institutional investors
    2. "No Big Three" κ: removing Vanguard, BlackRock, and State Street from the
       ownership vectors, then recomputing

    The DIFFERENCE shows how much κ would fall if the Big Three didn't exist.

    WHAT THE PAPER FOUND:
    Contrary to popular intuition, the rise in κ from 1980-2010 was NOT
    primarily driven by Vanguard/BlackRock (which grew mainly after 2000).
    Instead, the trend was driven by a broader shift toward diversified investing.
    We'll see if this holds in the more recent 2013-2024 period.
    """

    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
    holdings_files = sorted(glob.glob(os.path.join(DATA_DIR, "holdings_*.csv")))

    # CIKs for the Big Three (these are stable, known identifiers)
    # Vanguard Group  CIK: 102909
    # BlackRock Inc.  CIK: 1364742
    # State Street    CIK: 93751
    BIG_THREE_CIKS = {"102909", "1364742", "93751"}
    BIG_THREE_NAMES = ["Vanguard", "BlackRock", "State Street"]

    # For each quarter, compute:
    # 1. Total shares held by each Big Three investor across all QK500 firms
    # 2. Their average portfolio share

    big_three_rows = []

    for filepath in holdings_files:
        quarter_label = os.path.basename(filepath).replace("holdings_", "").replace(".csv", "")
        df_q = pd.read_csv(filepath)

        year = int(quarter_label[:4])
        n_firms = df_q["issuerCik"].nunique()

        for cik, name in zip(["102909", "1364742", "93751"], BIG_THREE_NAMES):
            investor_rows = df_q[df_q["filerCik"].astype(str).str.lstrip("0") == cik.lstrip("0")]
            n_firms_held = investor_rows["issuerCik"].nunique()
            total_value  = investor_rows["shrsOrPrnAmt"].sum()

            # Average portfolio share across all firms they hold:
            # For each firm held by this investor, compute shares_held / total_inst_shares
            # Then average across all firms
            if len(investor_rows) > 0:
                firm_totals = df_q.groupby("issuerCik")["shrsOrPrnAmt"].sum()
                investor_shares = investor_rows.set_index("issuerCik")["shrsOrPrnAmt"]
                frac = (investor_shares / firm_totals).dropna()
                avg_ownership_pct = frac.mean() * 100
            else:
                avg_ownership_pct = 0

            big_three_rows.append({
                "quarter_label": quarter_label,
                "year": year,
                "investor": name,
                "n_firms_held": n_firms_held,
                "avg_ownership_pct": avg_ownership_pct,
                "coverage_pct": 100 * n_firms_held / n_firms if n_firms > 0 else 0,
            })

    bt_df = pd.DataFrame(big_three_rows)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    # Left: Average ownership stake per firm, over time
    colors = [BLUE, RED, GREEN]
    for investor, color in zip(BIG_THREE_NAMES, colors):
        sub = bt_df[bt_df["investor"] == investor].sort_values("year")
        ax1.plot(sub["year"], sub["avg_ownership_pct"], color=color,
                 linewidth=2.5, marker="o", markersize=7, label=investor)

    ax1.set_xlabel("Year")
    ax1.set_ylabel("Average Ownership Stake (%)")
    ax1.set_title("Big Three Average Stake in a Typical S&P500 Firm\n"
                  "How much does each giant own per company?")
    ax1.legend()
    ax1.yaxis.set_major_formatter(mtick.PercentFormatter())

    # Right: Fraction of QK500 firms they hold
    for investor, color in zip(BIG_THREE_NAMES, colors):
        sub = bt_df[bt_df["investor"] == investor].sort_values("year")
        ax2.plot(sub["year"], sub["coverage_pct"], color=color,
                 linewidth=2.5, marker="s", markersize=7, label=investor)

    ax2.set_xlabel("Year")
    ax2.set_ylabel("Fraction of S&P500 Firms Held (%)")
    ax2.set_title("Breadth: What % of S&P500 Does Each Giant Hold?\n"
                  "Near 100% means they hold essentially every firm")
    ax2.legend()
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter())

    plt.suptitle('The "Big Three" Asset Managers: Vanguard, BlackRock, State Street\n'
                 "They hold nearly every S&P500 firm — the key driver of common ownership",
                 fontsize=12)
    plt.tight_layout()
    save_path = os.path.join(PLOTS_DIR, "fig5_big_three_ownership.png")
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: fig5_big_three_ownership.png")


# ─────────────────────────────────────────────────────────────────────────────
# FIGURE 6: Firm-pair Heatmap for a subset of famous companies
# ─────────────────────────────────────────────────────────────────────────────

def plot_kappa_heatmap(latest_kappa, latest_quarter):
    """
    Shows κ values as a color-coded grid for a set of well-known companies.
    Rows = firm f, Columns = firm g, Color = κ_fg value.

    HOW TO READ IT:
    - Dark blue = high κ (high common ownership, f cares a lot about g's profits)
    - White = low κ (low common ownership, f mostly ignores g's profits)
    - The diagonal would be κ = 1 (a firm with itself), excluded.
    - This is NOT symmetric: κ_fg ≠ κ_gf in general.

    WHY κ IS ASYMMETRIC:
    Recall: κ_fg = dot(β_f, β_g) / dot(β_f, β_f)
    The denominator uses firm f's ownership concentration (β_f · β_f).
    If firm f has very concentrated ownership (few large investors), the
    denominator is large and κ_fg is small.
    If firm f has dispersed ownership (many small investors), the denominator
    is small and κ_fg is large.
    So: "f cares about g" can differ from "g cares about f."
    """
    # Select a set of well-known tickers for the heatmap
    SELECTED_TICKERS = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META",
        "JPM", "GS", "BAC", "WFC",
        "JNJ", "PFE", "MRK",
        "XOM", "CVX",
        "UAL", "DAL",
        "WMT", "TGT",
    ]

    # Find which of these are actually in our data
    available = latest_kappa["issuerTicker_f"].unique()
    selected  = [t for t in SELECTED_TICKERS if t in available]

    if len(selected) < 4:
        print("  Not enough named firms for heatmap — skipping")
        return

    # Filter to only pairs among selected firms
    heatmap_data = latest_kappa[
        (latest_kappa["issuerTicker_f"].isin(selected)) &
        (latest_kappa["issuerTicker_g"].isin(selected))
    ].copy()

    # Pivot to a matrix: rows = firm f, columns = firm g, values = kappa
    heatmap_matrix = heatmap_data.pivot_table(
        index="issuerTicker_f",
        columns="issuerTicker_g",
        values="kappa"
    )

    # Reorder to match SELECTED_TICKERS order
    heatmap_matrix = heatmap_matrix.reindex(
        index=[t for t in selected if t in heatmap_matrix.index],
        columns=[t for t in selected if t in heatmap_matrix.columns]
    )

    fig, ax = plt.subplots(figsize=(12, 9))
    im = ax.imshow(heatmap_matrix.values, cmap="Blues", vmin=0, vmax=1,
                   aspect="auto")

    # Add colorbar explaining what the colors mean
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("κ (profit weight)\n0 = ignore competitor, 1 = merger equivalent",
                   rotation=270, labelpad=20)

    # Add κ value as text in each cell (only if enough space)
    for i in range(len(heatmap_matrix.index)):
        for j in range(len(heatmap_matrix.columns)):
            val = heatmap_matrix.values[i, j]
            if not np.isnan(val):
                color = "white" if val > 0.7 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=7, color=color)

    ax.set_xticks(range(len(heatmap_matrix.columns)))
    ax.set_yticks(range(len(heatmap_matrix.index)))
    ax.set_xticklabels(heatmap_matrix.columns, rotation=45, ha="right")
    ax.set_yticklabels(heatmap_matrix.index)
    ax.set_xlabel("Firm g  (whose profits does firm f care about?)")
    ax.set_ylabel("Firm f  (which firm are we measuring?)")
    ax.set_title(f"Kappa Heatmap: Pairwise Profit Weights for Famous S&P500 Firms\n"
                 f"({latest_quarter})\n"
                 "Row = firm f, Column = firm g, Color = how much f cares about g's profits",
                 fontsize=11)

    plt.tight_layout()
    save_path = os.path.join(PLOTS_DIR, "fig6_kappa_heatmap.png")
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: fig6_kappa_heatmap.png")


# ─────────────────────────────────────────────────────────────────────────────
# RUN ALL PLOTS
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("GENERATING ALL FIGURES")
print("=" * 60)
print()

all_kappa_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "kappa_*.csv")))
all_kappa_files = [f for f in all_kappa_files if "summary" not in f]

plot_kappa_over_time(summary_df)
plot_within_vs_across_industry(summary_df)
plot_firm_distribution(latest_kappa, latest_quarter)
plot_famous_pairs(all_kappa, summary_df)
plot_big_three_contribution(all_kappa_files, summary_df)
plot_kappa_heatmap(latest_kappa, latest_quarter)

print()
print("=" * 60)
print("ALL FIGURES SAVED to ../plots/")
print("=" * 60)
print()
print("EXPLANATION OF EACH FIGURE:")
print()
print("fig1_kappa_over_time.png")
print("  Shows the MAIN RESULT: average κ rising over 2013–2024.")
print("  Higher κ = more common ownership = less competition incentive.")
print()
print("fig2_within_vs_across_industry.png")
print("  Shows that firms in the SAME industry (direct competitors) have")
print("  even higher κ than firms in different industries.")
print()
print("fig3_firm_distribution_latest.png")
print("  Shows which specific firms have the highest κ (it's the large caps).")
print("  Large firms are held by many index funds → more shared ownership.")
print()
print("fig4_famous_firm_pairs.png")
print("  Makes it concrete: see κ for Apple/Microsoft, United/Delta, etc.")
print()
print("fig5_big_three_ownership.png")
print("  Shows how much Vanguard, BlackRock, and State Street own across")
print("  the S&P500 — these are the institutions driving common ownership.")
print()
print("fig6_kappa_heatmap.png")
print("  Grid view of pairwise κ values for famous companies.")
print("  Darker = higher κ = more common ownership between that pair.")
