import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")
PLOTS_DIR  = os.path.join(os.path.dirname(__file__), "..", "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)

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

BLUE   = "#2166ac"
RED    = "#d6604d"
GREEN  = "#4dac26"
ORANGE = "#f4a582"

# Load data
summary_df = pd.read_csv(
    os.path.join(OUTPUT_DIR, "kappa_summary_by_quarter.csv")
).sort_values("year")

all_kappa_files = [f for f in sorted(glob.glob(os.path.join(OUTPUT_DIR, "kappa_*.csv")))
                   if "summary" not in f]
all_kappa = pd.concat([pd.read_csv(f) for f in all_kappa_files], ignore_index=True)

latest_quarter = summary_df["quarter_label"].iloc[-1]
latest_kappa   = all_kappa[all_kappa["quarter_label"] == latest_quarter].copy()

print(f"Loaded: {len(all_kappa):,} pair observations, latest quarter {latest_quarter}\n")


def plot_kappa_over_time(summary_df):
    # Average κ over time — replicates paper Figure 1
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = summary_df["year"]

    ax.plot(x, summary_df["avg_kappa"], color=BLUE, linewidth=2.5,
            marker="o", markersize=7, label="Average κ (all firm pairs)")
    ax.fill_between(x, 0, summary_df["avg_kappa"], alpha=0.15, color=BLUE)
    ax.axhline(1.0, color="gray", linewidth=1, linestyle="--", alpha=0.5)
    ax.text(x.max() + 0.05, 1.02, "κ = 1\n(merger equivalent)", fontsize=8, color="gray")
    ax.axhline(0.0, color="gray", linewidth=1, linestyle="--", alpha=0.5)

    latest_val = summary_df["avg_kappa"].iloc[-1]
    latest_yr  = summary_df["year"].iloc[-1]
    ax.annotate(
        f"By {latest_yr}, avg κ ≈ {latest_val:.2f}\n(paper: κ ≈ 0.7 by 2017)",
        xy=(latest_yr, latest_val),
        xytext=(latest_yr - 5, latest_val + 0.15),
        arrowprops=dict(arrowstyle="->", color="black"),
        fontsize=9, bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray")
    )

    ax.set_xlabel("Year")
    ax.set_ylabel("Average Profit Weight (κ)")
    ax.set_title("Figure 1 Replica: Common Ownership Profit Weights Over Time\n"
                 "Average κ across all S&P500 firm pairs, 2013–2024\n"
                 "(Simplified κ — no retail share correction)", fontsize=11)
    ax.set_ylim(0, 1.1)
    ax.set_xticks(sorted(x.unique()))
    ax.legend(loc="lower right")

    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "fig1_kappa_over_time.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("Saved: fig1_kappa_over_time.png")


def plot_within_vs_across_industry(summary_df):
    # Within vs across industry — replicates paper Figure 11
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = summary_df["year"]

    ax.plot(x, summary_df["avg_kappa_within_industry"], color=RED,
            linewidth=2.5, marker="s", markersize=7, label="Same industry (2-digit SIC)")
    ax.plot(x, summary_df["avg_kappa_across_industry"], color=BLUE,
            linewidth=2.5, marker="o", markersize=7, label="Different industries")
    ax.plot(x, summary_df["avg_kappa"], color="gray",
            linewidth=1.5, linestyle="--", label="Overall average")

    ax.text(0.02, 0.05,
            "Industry = 2-digit SIC code\n(e.g., SIC 73 = Business Services,\n SIC 45 = Air Transportation)",
            transform=ax.transAxes, fontsize=8,
            bbox=dict(boxstyle="round", fc="white", ec="gray", alpha=0.8))

    ax.set_xlabel("Year")
    ax.set_ylabel("Average Profit Weight (κ)")
    ax.set_title("Figure 11 Replica: Within- vs Across-Industry Common Ownership\n"
                 "Firms that directly compete (same industry) have higher shared ownership",
                 fontsize=11)
    ax.set_ylim(0, 1.1)
    ax.set_xticks(sorted(x.unique()))
    ax.legend(loc="lower right")

    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "fig2_within_vs_across_industry.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("Saved: fig2_within_vs_across_industry.png")


def plot_firm_distribution(latest_kappa, latest_quarter):
    avg_per_firm = (latest_kappa
                    .groupby(["cik_f", "issuerTicker_f", "issuerName_f"])["kappa"]
                    .mean().reset_index()
                    .rename(columns={"kappa": "avg_kappa", "issuerTicker_f": "ticker",
                                     "issuerName_f": "name", "cik_f": "cik"})
                    .sort_values("avg_kappa", ascending=False))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    ax1.hist(avg_per_firm["avg_kappa"], bins=40, color=BLUE, alpha=0.7, edgecolor="white")
    ax1.axvline(avg_per_firm["avg_kappa"].mean(), color=RED, linewidth=2,
                label=f'Mean = {avg_per_firm["avg_kappa"].mean():.3f}')
    ax1.axvline(avg_per_firm["avg_kappa"].median(), color=ORANGE, linewidth=2, linestyle="--",
                label=f'Median = {avg_per_firm["avg_kappa"].median():.3f}')
    ax1.set_xlabel("Average κ with all other S&P500 firms")
    ax1.set_ylabel("Number of Firms")
    ax1.set_title(f"Distribution of Average κ Per Firm\n({latest_quarter})")
    ax1.legend()

    top25 = avg_per_firm.head(25)
    top25 = top25.copy()
    top25["label"] = top25["ticker"].fillna(top25["name"].str[:12])
    ax2.barh(range(len(top25)), top25["avg_kappa"].values, color=BLUE, alpha=0.8, edgecolor="white")
    ax2.set_yticks(range(len(top25)))
    ax2.set_yticklabels(top25["label"].values, fontsize=8)
    ax2.invert_yaxis()
    ax2.set_xlabel("Average κ with all other S&P500 firms")
    ax2.set_title(f"Top 25 Firms by Average κ\n({latest_quarter})")
    ax2.axvline(avg_per_firm["avg_kappa"].mean(), color=RED, linewidth=1.5, linestyle="--", alpha=0.7)

    plt.suptitle("Which S&P500 Firms Have the Highest Common Ownership?\n"
                 "Large-cap firms held by many index funds tend to score highest",
                 fontsize=12, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "fig3_firm_distribution_latest.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("Saved: fig3_firm_distribution_latest.png")
    return avg_per_firm


def plot_famous_pairs(all_kappa, summary_df):
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

    for idx, (ticker_f, ticker_g, label) in enumerate(FAMOUS_PAIRS):
        ax = axes[idx]

        pair    = all_kappa[(all_kappa["issuerTicker_f"] == ticker_f) &
                            (all_kappa["issuerTicker_g"] == ticker_g)].sort_values("year")
        reverse = all_kappa[(all_kappa["issuerTicker_f"] == ticker_g) &
                            (all_kappa["issuerTicker_g"] == ticker_f)].sort_values("year")

        if len(pair) == 0 and len(reverse) == 0:
            ax.text(0.5, 0.5, f"No data for\n{ticker_f} / {ticker_g}",
                    ha="center", va="center", transform=ax.transAxes, fontsize=9)
            ax.set_title(label, fontsize=9)
            continue

        if len(pair) > 0:
            ax.plot(pair["year"], pair["kappa"], color=BLUE, linewidth=2,
                    marker="o", markersize=6, label=f"κ({ticker_f}→{ticker_g})")
            ax.fill_between(pair["year"], 0, pair["kappa"], alpha=0.1, color=BLUE)
        if len(reverse) > 0:
            ax.plot(reverse["year"], reverse["kappa"], color=RED, linewidth=2,
                    marker="s", markersize=6, linestyle="--", label=f"κ({ticker_g}→{ticker_f})")

        ax.set_ylim(0, 1.1)
        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.set_xlabel("Year", fontsize=9)
        ax.set_ylabel("κ", fontsize=9)
        ax.legend(fontsize=7)
        ax.axhline(1.0, color="gray", linewidth=0.5, linestyle=":")

    plt.suptitle("κ Over Time for Specific Firm Pairs\n"
                 "κ = 1 means merger-equivalent; κ = 0 means perfect competition",
                 fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "fig4_famous_firm_pairs.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("Saved: fig4_famous_firm_pairs.png")


def plot_big_three_contribution(all_kappa_files, summary_df):
    DATA_DIR         = os.path.join(os.path.dirname(__file__), "..", "data")
    BIG_THREE_CIKS   = {"102909", "1364742", "93751"}
    BIG_THREE_NAMES  = ["Vanguard", "BlackRock", "State Street"]

    big_three_rows = []
    for filepath in sorted(glob.glob(os.path.join(DATA_DIR, "holdings_*.csv"))):
        label = os.path.basename(filepath).replace("holdings_", "").replace(".csv", "")
        df_q  = pd.read_csv(filepath)
        year  = int(label[:4])
        n_firms = df_q["issuerCik"].nunique()

        for cik, name in zip(["102909", "1364742", "93751"], BIG_THREE_NAMES):
            inv = df_q[df_q["filerCik"].astype(str).str.lstrip("0") == cik.lstrip("0")]
            n_firms_held = inv["issuerCik"].nunique()
            if len(inv) > 0:
                firm_totals = df_q.groupby("issuerCik")["shrsOrPrnAmt"].sum()
                frac        = (inv.set_index("issuerCik")["shrsOrPrnAmt"] / firm_totals).dropna()
                avg_pct     = frac.mean() * 100
            else:
                avg_pct = 0
            big_three_rows.append({
                "quarter_label": label, "year": year, "investor": name,
                "n_firms_held": n_firms_held, "avg_ownership_pct": avg_pct,
                "coverage_pct": 100 * n_firms_held / n_firms if n_firms > 0 else 0,
            })

    bt_df = pd.DataFrame(big_three_rows)
    colors = [BLUE, RED, GREEN]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))
    for investor, color in zip(BIG_THREE_NAMES, colors):
        sub = bt_df[bt_df["investor"] == investor].sort_values("year")
        ax1.plot(sub["year"], sub["avg_ownership_pct"], color=color,
                 linewidth=2.5, marker="o", markersize=7, label=investor)
        ax2.plot(sub["year"], sub["coverage_pct"], color=color,
                 linewidth=2.5, marker="s", markersize=7, label=investor)

    ax1.set_xlabel("Year")
    ax1.set_ylabel("Average Ownership Stake (%)")
    ax1.set_title("Big Three: Average Stake in a Typical S&P500 Firm")
    ax1.legend()
    ax1.yaxis.set_major_formatter(mtick.PercentFormatter())

    ax2.set_xlabel("Year")
    ax2.set_ylabel("Fraction of S&P500 Firms Held (%)")
    ax2.set_title("Breadth: % of S&P500 Covered by Each Giant")
    ax2.legend()
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter())

    plt.suptitle('The "Big Three": Vanguard, BlackRock, State Street', fontsize=12)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "fig5_big_three_ownership.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("Saved: fig5_big_three_ownership.png")


def plot_kappa_heatmap(latest_kappa, latest_quarter):
    SELECTED = ["AAPL", "MSFT", "GOOGL", "AMZN", "META",
                "JPM", "GS", "BAC", "WFC",
                "JNJ", "PFE", "MRK",
                "XOM", "CVX", "UAL", "DAL", "WMT", "TGT"]

    available = latest_kappa["issuerTicker_f"].unique()
    selected  = [t for t in SELECTED if t in available]
    if len(selected) < 4:
        print("  Not enough named firms for heatmap — skipping")
        return

    heatmap = (latest_kappa[latest_kappa["issuerTicker_f"].isin(selected) &
                             latest_kappa["issuerTicker_g"].isin(selected)]
               .pivot_table(index="issuerTicker_f", columns="issuerTicker_g", values="kappa")
               .reindex(index=[t for t in selected if t in latest_kappa["issuerTicker_f"].unique()],
                        columns=[t for t in selected if t in latest_kappa["issuerTicker_g"].unique()]))

    fig, ax = plt.subplots(figsize=(12, 9))
    im   = ax.imshow(heatmap.values, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("κ (0 = ignore competitor, 1 = merger equivalent)",
                   rotation=270, labelpad=20)

    for i in range(len(heatmap.index)):
        for j in range(len(heatmap.columns)):
            val = heatmap.values[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=7, color="white" if val > 0.7 else "black")

    ax.set_xticks(range(len(heatmap.columns)))
    ax.set_yticks(range(len(heatmap.index)))
    ax.set_xticklabels(heatmap.columns, rotation=45, ha="right")
    ax.set_yticklabels(heatmap.index)
    ax.set_xlabel("Firm g")
    ax.set_ylabel("Firm f")
    ax.set_title(f"κ Heatmap: Pairwise Profit Weights\n({latest_quarter})\n"
                 "Row = firm f, Column = firm g, Color = κ_fg", fontsize=11)

    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "fig6_kappa_heatmap.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("Saved: fig6_kappa_heatmap.png")


print("Generating figures...")
plot_kappa_over_time(summary_df)
plot_within_vs_across_industry(summary_df)
plot_firm_distribution(latest_kappa, latest_quarter)
plot_famous_pairs(all_kappa, summary_df)
plot_big_three_contribution(all_kappa_files, summary_df)
plot_kappa_heatmap(latest_kappa, latest_quarter)
print(f"\nAll figures saved to {PLOTS_DIR}")
