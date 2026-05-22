"""
Compute common ownership profit weights (κ) for all firm pairs and quarters.

The formula, following Backus, Conlon & Sinkinson (2019) under proportional
control (γ = β):

    κ_fg = Σ_s β_fs · β_gs  /  Σ_s β_fs²

where β_fs = shares held by institution s in firm f / total shares outstanding.

Three data quality corrections are applied before computing β:

    1. Shares outstanding fixes — corrects two known EDGAR XBRL errors:
       AAPL 2014Q1 (units reported in thousands instead of shares) and
       NVDA 2021Q2 (fiscal year boundary crosses a stock split date).

    2. Entity consolidation — maps subsidiary CIK numbers to parent institutions
       so that e.g. the seven separate BlackRock filing entities in 2013–2016
       are treated as a single investor.

    3. Contamination scaling — proportionally scales down holdings in quarters
       where aggregate reported institutional ownership exceeds shares outstanding,
       which occurs for NVDA (convertible notes, 2014–2017) and AAL (CARES Act
       warrants, 2020–2025).

Output:
    data/processed/kappa_9firms_corrected.csv   κ for all 72 ordered pairs × quarters
    data/processed/kappa_mean_by_quarter.csv    mean κ̄ per quarter (used in Figure 4)

Usage:
    python3 compute_kappa.py
"""

import numpy as np
import pandas as pd
from itertools import permutations
from config import TICKERS, SIC, DATA_DIR


def load_data():
    holdings = pd.read_csv(DATA_DIR / "holdings_9firms.csv", dtype={"filer_cik": str})
    holdings["filer_cik"] = holdings["filer_cik"].str.replace(r"\.0$", "", regex=True).str.strip()

    shares  = pd.read_csv(DATA_DIR / "shares_outstanding_9firms_fixed.csv")
    cmap    = pd.read_csv(DATA_DIR / "entity_consolidation_map.csv", dtype={"cik": str})
    contam  = pd.read_csv(DATA_DIR / "contaminated_quarters.csv")

    return holdings, shares, cmap, contam


def build_beta_vectors(holdings_q, shares_q, cik_to_parent, contam_scale):
    """
    For a single quarter's holdings, compute β_fs for every (firm, investor) pair.

    Returns a dict of {ticker: pd.Series(β values indexed by parent entity id)}.
    """
    # Apply entity consolidation: map each filing CIK to its economic parent
    holdings_q = holdings_q.copy()
    holdings_q["parent"] = holdings_q["filer_cik"].map(cik_to_parent).fillna(holdings_q["filer_cik"])
    holdings_q = holdings_q.groupby(["ticker", "parent"])["shares_held"].sum().reset_index()

    beta = {}
    for ticker in TICKERS:
        firm_holdings = holdings_q[holdings_q.ticker == ticker].set_index("parent")["shares_held"]
        total_shares  = shares_q.loc[shares_q.ticker == ticker, "shares"].values

        if len(total_shares) == 0 or total_shares[0] == 0 or firm_holdings.empty:
            beta[ticker] = pd.Series(dtype=float)
            continue

        raw_beta = firm_holdings / total_shares[0]

        # Apply contamination scaling if this firm-quarter is flagged.
        # The scale factor is shares_outstanding / sum(reported_holdings),
        # pulling aggregate institutional ownership back below 100%.
        key = (ticker,
               holdings_q["ticker"].iloc[0] if not holdings_q.empty else None,
               None)  # placeholder; real lookup below
        scale = contam_scale.get((ticker,), 1.0)
        raw_beta = raw_beta * scale

        # Cap at 1.0 as a final sanity guard — no single institution can own
        # more than 100% of outstanding shares
        beta[ticker] = raw_beta.clip(upper=1.0)

    return beta


def kappa(beta_f, beta_g):
    """
    Compute κ_fg given ownership vectors β_f and β_g over a shared investor universe.

    Both Series must share the same index (union of investors). Investors
    appearing in only one firm contribute zero to the numerator (no shared
    ownership) but positively to the IHHI denominator for the firm they hold.
    """
    universe = beta_f.index.union(beta_g.index)
    b_f = beta_f.reindex(universe, fill_value=0.0).values
    b_g = beta_g.reindex(universe, fill_value=0.0).values

    ihhi_f = np.dot(b_f, b_f)
    if ihhi_f == 0:
        return np.nan

    return np.dot(b_f, b_g) / ihhi_f


def main():
    holdings, shares, cmap, contam = load_data()

    cik_to_parent = dict(zip(cmap["cik"], cmap["parent_id"]))

    # Build a lookup of contamination scale factors keyed by (ticker, year, quarter)
    contam_scale = {
        (r.ticker, r.year, r.quarter): r.scale_factor
        for _, r in contam.iterrows()
    }

    quarters = sorted(holdings[["year", "quarter"]].drop_duplicates().values.tolist())
    pairs    = list(permutations(TICKERS, 2))

    records = []

    for year, quarter in quarters:
        h_q = holdings[(holdings.year == year) & (holdings.quarter == quarter)]
        s_q = shares[(shares.year == year) & (shares.quarter == quarter)]

        # Compute β for each firm this quarter, with all corrections applied
        beta = {}
        for ticker in TICKERS:
            firm_h = h_q[h_q.ticker == ticker].copy()
            firm_h["parent"] = firm_h["filer_cik"].map(cik_to_parent).fillna(firm_h["filer_cik"])
            firm_h = firm_h.groupby("parent")["shares_held"].sum()

            total = s_q.loc[s_q.ticker == ticker, "shares"].values
            if len(total) == 0 or total[0] == 0 or firm_h.empty:
                beta[ticker] = pd.Series(dtype=float)
                continue

            b = firm_h / total[0]

            scale = contam_scale.get((ticker, year, quarter), 1.0)
            b = b * scale
            beta[ticker] = b.clip(upper=1.0)

        # Compute κ for every ordered pair
        for f, g in pairs:
            if beta[f].empty or beta[g].empty:
                continue

            k_fg = kappa(beta[f], beta[g])
            if np.isnan(k_fg):
                continue

            universe = beta[f].index.union(beta[g].index)
            b_f = beta[f].reindex(universe, fill_value=0.0).values
            b_g = beta[g].reindex(universe, fill_value=0.0).values

            cos_sim  = np.dot(b_f, b_g) / (np.linalg.norm(b_f) * np.linalg.norm(b_g) + 1e-12)
            ihhi_f   = np.dot(b_f, b_f)
            ihhi_g   = np.dot(b_g, b_g)
            retail_f = max(0.0, 1.0 - b_f.sum())

            records.append({
                "year": year, "quarter": quarter,
                "time": year + (quarter - 0.5) / 4,
                "firm_f": f, "firm_g": g,
                "sic_f": SIC[f], "sic_g": SIC[g],
                "same_sic": SIC[f] == SIC[g],
                "kappa": round(k_fg, 6),
                "cosine": round(cos_sim, 6),
                "ihhi_f": round(ihhi_f, 8),
                "ihhi_g": round(ihhi_g, 8),
                "retail_f": round(retail_f, 4),
            })

    kappa_df = pd.DataFrame(records)
    kappa_df.to_csv(DATA_DIR / "kappa_9firms_corrected.csv", index=False)

    # Quarter-level mean used for the main time-series figure
    mean_q = (
        kappa_df.groupby(["year", "quarter", "time"])["kappa"]
        .mean()
        .reset_index()
        .rename(columns={"kappa": "kappa_all"})
    )
    mean_q.to_csv(DATA_DIR / "kappa_mean_by_quarter.csv", index=False)

    print(f"Wrote {len(kappa_df):,} pair-quarter rows to kappa_9firms_corrected.csv")
    print(f"Wrote {len(mean_q)} quarterly means to kappa_mean_by_quarter.csv")


if __name__ == "__main__":
    main()
