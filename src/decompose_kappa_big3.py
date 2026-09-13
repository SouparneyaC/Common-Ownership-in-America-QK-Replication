# src/decompose_kappa_big3.py
# κ decomposed by institutional investor type, with the Big Three split into
# their three individual constituents (Vanguard / BlackRock / State Street)
# rather than one combined bucket — supersedes decompose_kappa.py for the
# 48-firm universe. See docs/methodology.md ("Big Three Split") and the
# README's Key Findings for the headline numbers this script reproduces.
#
# MATH
#   κ_fg = Σ_s(β_fs · β_gs) / IHHI_f     where IHHI_f = Σ_s(β_fs²)
#   Additive decomposition over investor groups G (a partition of all s):
#       κ_fg = Σ_G [ Σ_{s∈G}(β_fs · β_gs) / IHHI_f ] = Σ_G κ_fg^G
#   Every group's contribution divides by the SAME denominator IHHI_f
#   (never a group-restricted HHI) — this is what guarantees the group
#   contributions sum exactly to κ_fg, with zero residual.
#
# Run: python3 src/decompose_kappa_big3.py
# Requires data/processed/holdings_48firms.csv (from src/pull_data.py) and
# data/processed/shares_outstanding_48firms.csv.

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from itertools import permutations
from config import TICKERS, data_dir, plots_dir

HOLDINGS_CSV = data_dir / "holdings_48firms.csv"
SHARES_CSV   = data_dir / "shares_outstanding_48firms.csv"
CMAP_CSV     = data_dir / "entity_consolidation_map.csv"
CONTAM_CSV   = data_dir / "contaminated_quarters.csv"
OUT_CSV      = data_dir / "kappa_48firms_decomposed_big3_split.csv"

SS_CIK = "93751"          # State Street Corp
BLACKROCK_DUP_CIK = "2012383"


def classify(parent_id: str) -> str:
    """Classify a consolidated investor into one of seven categories.
    Evaluated in priority order — first match wins."""
    p = parent_id.upper()

    if parent_id == "VANGUARD" or "VANGUARD" in p:
        return "Vanguard"
    if parent_id == "BLACKROCK" or "BLACKROCK" in p or "BLACK ROCK" in p:
        return "BlackRock"
    if "STATE STREET" in p or "SSGA" in p:
        return "State Street"

    if any(kw in p for kw in [
        "GEODE", "DIMENSIONAL", "NORGES", "LEGAL & GENERAL", "APG",
        "SUMITOMO", "MUFG", "TEACHERS INSURANCE",
    ]):
        return "Passive"
    if parent_id in {"NORTHERN_TRUST", "CHARLES_SCHWAB",
                     "SUMITOMO_MITSUI", "MUFG_AM"}:
        return "Passive"

    if any(kw in p for kw in [
        "FMR", "FIDELITY", "WELLINGTON", "BERKSHIRE", "JPMORGAN",
        "MORGAN STANLEY", "GOLDMAN SACHS", "BANK OF AMERICA", "WELLS FARGO",
        "FRANKLIN", "AMERIPRISE", "MASSACHUSETTS FINANCIAL", "DEUTSCHE BANK",
        "ALLIANCEBERNSTEIN", "PRIMECAP", "DODGE & COX", "FISHER", "BARCLAYS",
        "ROYAL BANK", "BANK OF MONTREAL", "MANUFACTURERS LIFE",
        "HARRIS ASSOCIATES", "JENNISON", "NEW YORK STATE COMMON",
        "CALPERS", "CALSTRS", "BANK OF NEW YORK", "BNY MELLON",
        "PARNASSUS", "NEUBERGER", "ARTISAN",
    ]):
        return "Active"
    if parent_id in {"CAPITAL_GROUP", "T_ROWE_PRICE", "INVESCO", "NUVEEN",
                     "TIAA", "RAYMOND_JAMES", "BNP_PARIBAS", "NATIXIS",
                     "UBS", "BANK_OF_NS", "CI_FINANCIAL", "SWEDBANK", "NOMURA"}:
        return "Active"

    if any(kw in p for kw in [
        "RENAISSANCE", "TWO SIGMA", "CITADEL", "AQR", "MILLENNIUM",
        "POINT72", "BRIDGEWATER", "D.E. SHAW", "HIGHBRIDGE", "TUDOR",
        "BAUPOST", "VIKING", "COATUE", "TIGER",
    ]):
        return "Hedge Fund"
    if parent_id in {"SUSQUEHANNA", "LANSDOWNE"}:
        return "Hedge Fund"

    return "Other"


def load_and_fix():
    h = pd.read_csv(HOLDINGS_CSV, dtype={"filer_cik": str}, low_memory=False)
    h["filer_cik"] = h["filer_cik"].str.replace(r"\.0$", "", regex=True).str.strip()
    print(f"  holdings: {len(h):,} rows, {h['ticker'].nunique()} firms")

    # Fix 1 — BlackRock CIK 2012383, Q4 2025: QK captured both the original
    # 13(f) and its amendment and summed them (ratio ~2.0 vs Q3 2025 on
    # every ticker). Halve the affected rows.
    mask_bl = (h["filer_cik"] == BLACKROCK_DUP_CIK) & (h["year"] == 2025) & (h["quarter"] == 4)
    print(f"  Fix 1 — BlackRock {BLACKROCK_DUP_CIK} Q4 2025 rows halved: {mask_bl.sum()}")
    h.loc[mask_bl, "shares_held"] = (h.loc[mask_bl, "shares_held"] / 2).round().astype(int)

    # Fix 2 — State Street CIK 93751, 2015Q2-Q3: QK's ingestion pipeline
    # failed to capture a large subset of positions for these two quarters
    # (~28% understatement, 14 tickers missing entirely). State Street is a
    # passive index manager with no idiosyncratic 2015 event, so per-ticker
    # linear interpolation between the Q1 and Q4 2015 anchors is appropriate.
    ss_q1 = (h[(h["filer_cik"] == SS_CIK) & (h["year"] == 2015) & (h["quarter"] == 1)]
             .set_index("ticker")["shares_held"])
    ss_q4 = (h[(h["filer_cik"] == SS_CIK) & (h["year"] == 2015) & (h["quarter"] == 4)]
             .set_index("ticker")["shares_held"])
    ss_tickers = ss_q1.index.union(ss_q4.index)

    interp_rows = []
    for tkr in ss_tickers:
        q1_val = int(ss_q1.get(tkr, 0))
        q4_val = int(ss_q4.get(tkr, 0))
        q2_val = int(round(2 / 3 * q1_val + 1 / 3 * q4_val))
        q3_val = int(round(1 / 3 * q1_val + 2 / 3 * q4_val))

        template_rows = h[(h["filer_cik"] == SS_CIK) & (h["ticker"] == tkr)]
        if template_rows.empty:
            continue
        template = template_rows.iloc[0].to_dict()
        for qtr, val in [(2, q2_val), (3, q3_val)]:
            row = template.copy()
            row["year"], row["quarter"], row["shares_held"] = 2015, qtr, val
            interp_rows.append(row)

    n_before = ((h["filer_cik"] == SS_CIK) & (h["year"] == 2015) & (h["quarter"].isin([2, 3]))).sum()
    h = h[~((h["filer_cik"] == SS_CIK) & (h["year"] == 2015) & (h["quarter"].isin([2, 3])))].copy()
    h = pd.concat([h, pd.DataFrame(interp_rows)], ignore_index=True)
    print(f"  Fix 2 — State Street 2015Q2-Q3: dropped {n_before} rows, "
          f"inserted {len(interp_rows)} interpolated rows")

    return h


def main():
    print("Loading holdings + shares data...")
    h      = load_and_fix()
    shares = pd.read_csv(SHARES_CSV)[["ticker", "year", "quarter", "shares"]].drop_duplicates()
    cmap   = pd.read_csv(CMAP_CSV, dtype={"cik": str})
    contam = pd.read_csv(CONTAM_CSV)

    cik_to_parent = dict(zip(cmap["cik"], cmap["parent_id"]))
    contam_scale  = {(r.ticker, r.year, r.quarter): r.scale_factor for _, r in contam.iterrows()}

    quarters = sorted(h[["year", "quarter"]].drop_duplicates().values.tolist())
    pairs    = list(permutations(TICKERS, 2))
    print(f"\nFirms: {len(TICKERS)}  |  Quarters: {len(quarters)}  |  Ordered pairs: {len(pairs)}")

    GROUPS = ["Vanguard", "BlackRock", "State Street", "Passive", "Active", "Hedge Fund", "Other"]
    records = []

    print("Computing κ decomposition by investor type...")
    for year, quarter in quarters:
        h_q = h[(h.year == year) & (h.quarter == quarter)].copy()
        s_q = shares[(shares.year == year) & (shares.quarter == quarter)]

        h_q["parent"] = h_q["filer_cik"].map(cik_to_parent).fillna(h_q["filer_name"])
        h_q = h_q.groupby(["ticker", "parent"])["shares_held"].sum().reset_index()
        h_q["group"] = h_q["parent"].apply(classify)

        beta, beta_group, ihhi = {}, {}, {}
        for ticker in TICKERS:
            hf = h_q[h_q.ticker == ticker]
            sf = s_q[s_q.ticker == ticker]
            if hf.empty or sf.empty:
                continue
            total_shares = sf["shares"].iloc[0]
            if total_shares <= 0:
                continue

            scale = contam_scale.get((ticker, year, quarter), 1.0)
            holdings_s = hf.set_index("parent")["shares_held"] * scale
            b = (holdings_s / total_shares).clip(upper=1.0)
            if b.sum() < 0.05:   # implausibly low coverage — likely a resolution failure
                continue

            beta[ticker] = b
            ihhi[ticker] = float((b ** 2).sum())
            for grp in GROUPS:
                mask = hf["group"] == grp
                investors = hf.loc[mask, "parent"].values
                beta_group[(ticker, grp)] = b.reindex(investors, fill_value=0.0) if mask.any() else pd.Series(dtype=float)

        for f, g in pairs:
            if f not in beta or g not in beta:
                continue
            bf, bg = beta[f], beta[g]
            universe = bf.index.union(bg.index)
            bf_full = bf.reindex(universe, fill_value=0.0).values
            bg_full = bg.reindex(universe, fill_value=0.0).values

            denom_f = float(np.dot(bf_full, bf_full))
            if denom_f <= 0:
                continue
            kappa_total = float(np.dot(bf_full, bg_full)) / denom_f

            row = {"year": year, "quarter": quarter, "firm_f": f, "firm_g": g,
                   "kappa": round(kappa_total, 6)}
            contrib_sum = 0.0
            for grp in GROUPS[:-1]:
                bg_f = beta_group.get((f, grp), pd.Series(dtype=float))
                in_group_f = pd.Series(0.0, index=universe)
                in_group_f.update(bg_f)
                contrib = float(np.dot(in_group_f.values, bg_full)) / denom_f
                row[f"contrib_{grp}"] = round(contrib, 6)
                contrib_sum += contrib
            row["contrib_Other"] = round(kappa_total - contrib_sum, 6)  # exact residual
            records.append(row)

    kappa_df = pd.DataFrame(records)
    kappa_df["time"] = kappa_df["year"] + (kappa_df["quarter"] - 0.5) / 4
    kappa_df.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(kappa_df):,} rows -> {OUT_CSV}")

    contrib_cols = [f"contrib_{g}" for g in GROUPS]
    mean_q = kappa_df.groupby("time")[["kappa"] + contrib_cols].mean().reset_index().sort_values("time")
    mean_q = mean_q.rename(columns={f"contrib_{g}": g for g in GROUPS})

    COLORS = {"Vanguard": "#1f77b4", "BlackRock": "#aec7e8", "State Street": "#6baed6",
              "Passive": "#17becf", "Active": "#ff7f0e", "Hedge Fund": "#d62728", "Other": "#7f7f7f"}

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    fig.subplots_adjust(hspace=0.08)
    t = mean_q["time"].values
    data = [mean_q[g].values for g in GROUPS]

    ax1.stackplot(t, data, labels=GROUPS, colors=[COLORS[g] for g in GROUPS], alpha=0.88)
    ax1.set_ylabel("Mean κ (symmetric)", fontsize=11)
    ax1.set_title(
        "Common Ownership κ Decomposed by Institutional Investor Type (Big Three Split)\n"
        f"Backus-Conlon-Sinkinson (2019) - Extended Analysis ({len(TICKERS)} S&P 500 firms, 2013Q3-2025Q4)",
        fontsize=12)
    ax1.legend(loc="lower right", fontsize=9.5, framealpha=0.9)
    ax1.grid(axis="y", alpha=0.25)
    ax1.set_ylim(0, None)

    total = mean_q["kappa"].values
    pct_data = [(mean_q[g].values / total * 100) for g in GROUPS]
    ax2.stackplot(t, pct_data, labels=GROUPS, colors=[COLORS[g] for g in GROUPS], alpha=0.88)
    ax2.set_ylabel("Share of κ (%)", fontsize=11)
    ax2.set_xlabel("Year", fontsize=11)
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax2.set_ylim(0, 100)
    ax2.grid(axis="y", alpha=0.25)
    ax2.set_xticks(range(2014, 2027, 2))
    ax2.set_xlim(2013.5, 2026.1)

    plt.savefig(plots_dir / "kappa_breakdown_big3_split.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("Saved plot.")

    print("\n=== Mean κ share by group (full sample) ===")
    for grp in GROUPS:
        avg_share = (mean_q[grp] / mean_q["kappa"]).mean() * 100
        print(f"  {grp:<12}: {avg_share:5.1f}%")


if __name__ == "__main__":
    main()
