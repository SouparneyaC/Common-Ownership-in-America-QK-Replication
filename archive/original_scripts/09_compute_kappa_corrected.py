import os, numpy as np, pandas as pd
from itertools import permutations

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

# ── Load all inputs ──────────────────────────────────────────────────────────
print("Loading data...")
h      = pd.read_csv(f"{DATA_DIR}/holdings_9firms.csv", dtype={"filer_cik": str})
shares = pd.read_csv(f"{DATA_DIR}/shares_outstanding_9firms_fixed.csv")
cmap   = pd.read_csv(f"{DATA_DIR}/entity_consolidation_map.csv", dtype={"cik": str})
contam = pd.read_csv(f"{DATA_DIR}/contaminated_quarters.csv")

h["filer_cik"] = h["filer_cik"].str.replace(r"\.0$","",regex=True).str.strip()

# Build lookup dicts
cik_to_parent   = dict(zip(cmap["cik"], cmap["parent_id"]))
contam_scale    = {(r.ticker, r.year, r.quarter): r.scale_factor
                   for _, r in contam.iterrows()}

tickers  = sorted(h["ticker"].unique())
quarters = sorted(h[["year","quarter"]].drop_duplicates().values.tolist())
pairs    = list(permutations(tickers, 2))   # 72 ordered pairs

print(f"  Firms: {tickers}")
print(f"  Pairs: {len(pairs)} ordered  |  Quarters: {len(quarters)}")
print()

# ── Compute κ ────────────────────────────────────────────────────────────────
SIC = {"AAPL":3571,"MSFT":7372,"AAL":4512,"DAL":4512,
       "JPM":6021,"BAC":6021,"PFE":2834,"MRK":2834,"NVDA":3674}

records = []

for year, quarter in quarters:
    h_q = h[(h.year==year) & (h.quarter==quarter)].copy()
    s_q = shares[(shares.year==year) & (shares.quarter==quarter)]

    # ── Step 1: Apply entity consolidation ────────────────────────────────
    h_q["parent"] = h_q["filer_cik"].map(cik_to_parent).fillna(h_q["filer_cik"])
    h_q = h_q.groupby(["ticker","parent"])["shares_held"].sum().reset_index()

    # ── Step 2: Apply contamination scaling ───────────────────────────────
    beta = {}
    retail = {}
    ihhi = {}

    for ticker in tickers:
        hf = h_q[h_q.ticker == ticker]
        sf = s_q[s_q.ticker == ticker]
        if hf.empty or sf.empty:
            continue

        total_shares = sf["shares"].iloc[0]
        if total_shares <= 0:
            continue

        # Apply contamination scale factor if this quarter is flagged
        scale = contam_scale.get((ticker, year, quarter), 1.0)

        holdings = hf.set_index("parent")["shares_held"] * scale
        b = holdings / total_shares
        b = b.clip(upper=1.0)

        beta[ticker]   = b
        retail[ticker] = max(0.0, 1.0 - b.sum())
        ihhi[ticker]   = float((b**2).sum())

    # ── Step 3: Compute κ for each ordered pair ────────────────────────────
    for f, g in pairs:
        if f not in beta or g not in beta:
            continue

        bf = beta[f]
        bg = beta[g]
        universe = bf.index.union(bg.index)
        bf = bf.reindex(universe, fill_value=0.0).values
        bg = bg.reindex(universe, fill_value=0.0).values

        denom_f = float(np.dot(bf, bf))
        denom_g = float(np.dot(bg, bg))
        numer   = float(np.dot(bf, bg))

        if denom_f <= 0 or denom_g <= 0:
            continue

        kappa_fg = numer / denom_f
        norm_f   = np.sqrt(denom_f)
        norm_g   = np.sqrt(denom_g)
        cosine   = numer / (norm_f * norm_g) if norm_f > 0 and norm_g > 0 else 0.0

        records.append({
            "year":     year, "quarter": quarter,
            "firm_f":   f,    "firm_g":  g,
            "kappa":    round(kappa_fg, 6),
            "ihhi_f":   round(ihhi.get(f,0), 8),
            "retail_f": round(retail.get(f,0), 4),
            "cosine":   round(cosine, 6),
            "same_sic": int(SIC.get(f,-1) == SIC.get(g,-2)),
        })

kappa = pd.DataFrame(records)
kappa["time"] = kappa["year"] + (kappa["quarter"] - 0.5) / 4

# ── Save full pair-level file ────────────────────────────────────────────────
kappa.to_csv(f"{DATA_DIR}/kappa_9firms_corrected.csv", index=False)
print(f"Saved kappa_9firms_corrected.csv  ({len(kappa):,} rows)")

# ── Build mean-by-quarter summary for R plotting ────────────────────────────
mean_q = (kappa.groupby(["year","quarter","time"])
               .agg(
                   kappa_all    = ("kappa","mean"),
                   kappa_within = ("kappa", lambda x: x[kappa.loc[x.index,"same_sic"]==1].mean()),
                   kappa_cross  = ("kappa", lambda x: x[kappa.loc[x.index,"same_sic"]==0].mean()),
                   n_pairs      = ("kappa","count"),
               )
               .reset_index())

mean_q.to_csv(f"{DATA_DIR}/kappa_mean_by_quarter.csv", index=False)
print(f"Saved kappa_mean_by_quarter.csv   ({len(mean_q)} quarters)")

# ── Quick sanity check ───────────────────────────────────────────────────────
print()
print("Mean κ by period (all pairs):")
kappa["period"] = pd.cut(kappa["year"],
    bins=[2012,2015,2018,2021,2025],
    labels=["2013-2015","2016-2018","2019-2021","2022-2025"])
print(kappa.groupby("period")["kappa"].mean().round(3).to_string())
print()
print("Sample — latest quarter top/bottom κ pairs:")
latest = kappa[kappa.time == kappa.time.max()].sort_values("kappa", ascending=False)
print(latest[["firm_f","firm_g","kappa","cosine","same_sic"]].head(5).to_string(index=False))
print("...")
print(latest[["firm_f","firm_g","kappa","cosine","same_sic"]].tail(5).to_string(index=False))
