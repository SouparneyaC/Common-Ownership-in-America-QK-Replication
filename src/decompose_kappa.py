# src/decompose_kappa.py
# Decompose κ by institutional investor type — who actually drives common ownership?
#
# For each pair (f, g) in each quarter:
#   κ_fg = Σ_s(β_fs × β_gs) / IHHI_f
# The numerator is additive over investors, so we partition each s into a type
# and compute each type's share of κ.
#
# NOTE: this is the earlier, 5-group version (Big Three combined into one
# bucket, symmetric unordered-pair κ). See decompose_kappa_big3.py for the
# current 48-firm, 7-group version (Vanguard/BlackRock/State Street split)
# that the README's Key Findings and docs/methodology.md report.
#
# Run: HOLDINGS_CSV=/path/to/holdings.csv python src/decompose_kappa.py
# Defaults to data/processed/holdings_48firms.csv if env var not set.

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from itertools import combinations
from pathlib import Path

DATA_DIR  = Path(__file__).parent.parent / "data" / "processed"
PLOTS_DIR = Path(__file__).parent.parent / "plots"
os.makedirs(PLOTS_DIR, exist_ok=True)

HOLDINGS_CSV = os.environ.get("HOLDINGS_CSV", DATA_DIR / "holdings_48firms.csv")
SHARES_CSV   = DATA_DIR / "shares_outstanding_48firms.csv"
CMAP_CSV     = DATA_DIR / "entity_consolidation_map.csv"
CONTAM_CSV   = DATA_DIR / "contaminated_quarters.csv"
OUT_CSV      = DATA_DIR / "kappa_decomposition.csv"

# --- Institution classification ---
# Two-level approach: explicit parent_id map first, keyword fallback second.
# First match wins in KEYWORD_RULES.

PARENT_TYPE = {
    "BLACKROCK":      "Big Three",
    "VANGUARD":       "Big Three",
    "CAPITAL_GROUP":  "Active",
    "T_ROWE_PRICE":   "Active",
    "NORTHERN_TRUST": "Passive",
    "INVESCO":        "Passive",
    "CHARLES_SCHWAB": "Passive",
    "NUVEEN":         "Active",
    "NATIXIS":        "Active",
    "CI_FINANCIAL":   "Active",
    "SUSQUEHANNA":    "Hedge Fund",
    "LANSDOWNE":      "Hedge Fund",
    "UBS":            "Other",
    "TIAA":           "Other",
    "RAYMOND_JAMES":  "Other",
    "BNP_PARIBAS":    "Other",
    "APG":            "Other",
    "SUMITOMO_MITSUI":"Other",
    "SWEDBANK":       "Other",
    "NOMURA":         "Other",
    "BANK_OF_NS":     "Other",
    "MUFG_AM":        "Other",
}

KEYWORD_RULES = [
    ("Big Three",  ["STATE STREET", "SSGA"]),
    ("Passive",    ["GEODE CAPITAL", "DIMENSIONAL", "NORGES BANK",
                    "LEGAL & GENERAL", "LGIM", "WISDOMTREE"]),
    ("Hedge Fund", ["TWO SIGMA", "CITADEL", "MILLENNIUM MANAGEMENT",
                    "D.E. SHAW", "DESHAW", "RENAISSANCE TECH",
                    "AQR CAPITAL", "BRIDGEWATER", "POINT72",
                    "BALYASNY", "MAN NUMERIC", "MAN AHL", "MAN GLG",
                    "MARSHALL WACE", "COATUE", "TIGER GLOBAL",
                    "GREENLIGHT", "GLENVIEW", "PERSHING SQUARE",
                    "THIRD POINT", "STARBOARD VALUE", "MAGNETAR"]),
    ("Active",     ["FMR LLC", "WELLINGTON MANAGEMENT",
                    "MASSACHUSETTS FINANCIAL", "FRANKLIN RESOURCES",
                    "PRIMECAP", "DODGE & COX", "ARTISAN PARTNERS",
                    "PUTNAM INVEST", "AMERIPRISE", "NEUBERGER BERMAN",
                    "ALLIANCEBERNSTEIN", "LAZARD ASSET",
                    "CAUSEWAY CAPITAL", "BROWN ADVISORY"]),
]

def classify(parent_id, name):
    if parent_id in PARENT_TYPE:
        return PARENT_TYPE[parent_id]
    n = str(name).upper()
    for label, keywords in KEYWORD_RULES:
        if any(k in n for k in keywords):
            return label
    return "Other"

# --- Load ---
print("Loading data...")
h      = pd.read_csv(HOLDINGS_CSV, dtype={"filer_cik": str})
shares = pd.read_csv(SHARES_CSV)
cmap   = pd.read_csv(CMAP_CSV, dtype={"cik": str})
contam = pd.read_csv(CONTAM_CSV)

h["filer_cik"] = h["filer_cik"].str.replace(r"\.0$", "", regex=True).str.strip()

# Entity consolidation
cik_to_parent = dict(zip(cmap["cik"], cmap["parent_id"]))
cik_to_pname  = dict(zip(cmap["cik"], cmap["parent_name"]))
h["parent"]   = h["filer_cik"].map(cik_to_parent).fillna(h["filer_cik"])
h["pname"]    = h["filer_cik"].map(cik_to_pname).fillna(h["filer_name"])

h["inst_type"] = h.apply(lambda r: classify(r["parent"], r["pname"]), axis=1)

print(f"  {h['ticker'].nunique()} firms  |  type breakdown:")
print(h["inst_type"].value_counts().to_string())

contam_scale   = {(r.ticker, r.year, r.quarter): r.scale_factor for _, r in contam.iterrows()}
parent_to_name = h.groupby("parent")["pname"].first().to_dict()

# Aggregate to (ticker, year, quarter, parent, inst_type)
h_agg = (h
    .groupby(["ticker", "year", "quarter", "parent", "inst_type"])["shares_held"]
    .sum()
    .reset_index())

h_agg = h_agg.merge(shares[["ticker", "year", "quarter", "shares"]],
                    on=["ticker", "year", "quarter"], how="left")

h_agg["scale"] = h_agg.apply(
    lambda r: contam_scale.get((r.ticker, r.year, r.quarter), 1.0), axis=1)
h_agg["beta"]  = (h_agg["shares_held"] * h_agg["scale"] / h_agg["shares"]).clip(upper=1.0)
h_agg = h_agg.dropna(subset=["beta"])

# --- Compute κ decomposition ---
# For each unordered pair (f, g), compute each type's contribution to κ_sym_fg.
# κ_sym_fg_type = cross_type × (1/IHHI_f + 1/IHHI_g) / 2
# These sum to κ_sym_fg = (κ_fg + κ_gf) / 2 exactly.

tickers  = sorted(h_agg["ticker"].unique())
pairs    = list(combinations(tickers, 2))
quarters = sorted(h_agg[["year", "quarter"]].drop_duplicates().values.tolist())
TYPES    = ["Big Three", "Passive", "Active", "Hedge Fund", "Other"]
TYPE_COLS = [f"k_{t.replace(' ', '_').lower()}" for t in TYPES]

print(f"\nComputing decomposition: {len(pairs)} pairs × {len(quarters)} quarters...")

records = []
for year, quarter in quarters:
    h_q = h_agg[(h_agg.year == year) & (h_agg.quarter == quarter)]

    for f, g in pairs:
        hf = h_q[h_q.ticker == f].set_index("parent")
        hg = h_q[h_q.ticker == g].set_index("parent")

        if hf.empty or hg.empty:
            continue

        universe  = hf.index.union(hg.index)
        bf        = hf["beta"].reindex(universe, fill_value=0.0)
        bg        = hg["beta"].reindex(universe, fill_value=0.0)
        type_map  = hf["inst_type"].reindex(universe, fill_value="Other")

        cross  = bf * bg
        ihhi_f = float((bf ** 2).sum())
        ihhi_g = float((bg ** 2).sum())

        if ihhi_f <= 0 or ihhi_g <= 0:
            continue

        # Symmetric normalisation: average of 1/IHHI_f and 1/IHHI_g
        norm = (1.0 / ihhi_f + 1.0 / ihhi_g) / 2.0

        rec = {
            "year": year, "quarter": quarter,
            "firm_f": f, "firm_g": g,
            "kappa_sym": float(cross.sum()) * norm,
            "ihhi_f": ihhi_f, "ihhi_g": ihhi_g,
        }
        for t, col in zip(TYPES, TYPE_COLS):
            mask    = type_map == t
            rec[col] = float(cross[mask].sum()) * norm if mask.any() else 0.0

        records.append(rec)

decomp = pd.DataFrame(records)
decomp["time"] = decomp["year"] + (decomp["quarter"] - 0.5) / 4

# Sanity check: type columns should sum to kappa_sym
decomp["_check"] = decomp[TYPE_COLS].sum(axis=1)
max_err = (decomp["_check"] - decomp["kappa_sym"]).abs().max()
print(f"  Decomposition error (max): {max_err:.2e}  (should be ~0)")
decomp.drop(columns=["_check"], inplace=True)

decomp.to_csv(OUT_CSV, index=False)
print(f"  Saved {len(decomp):,} rows → {OUT_CSV}")

# --- Aggregate by quarter ---
by_q = decomp.groupby("time")[TYPE_COLS + ["kappa_sym"]].mean().reset_index()

# --- Figure: two-panel stacked area ---
COLORS = {
    "Big Three":  "#1f77b4",
    "Passive":    "#17becf",
    "Active":     "#ff7f0e",
    "Hedge Fund": "#d62728",
    "Other":      "#7f7f7f",
}
colors = [COLORS[t] for t in TYPES]

fig, axes = plt.subplots(2, 1, figsize=(13, 10), sharex=True)
fig.subplots_adjust(hspace=0.08, bottom=0.10)

# Panel A — absolute κ
ax = axes[0]
bottom = np.zeros(len(by_q))
for t, col, color in zip(TYPES, TYPE_COLS, colors):
    vals = by_q[col].values
    ax.fill_between(by_q["time"], bottom, bottom + vals, alpha=0.85,
                    color=color, label=t)
    bottom += vals
ax.set_ylabel("Mean κ (symmetric)", fontsize=11)
ax.set_title(
    "Common Ownership κ Decomposed by Institutional Investor Type\n"
    "Backus–Conlon–Sinkinson (2019) — Extended Analysis",
    fontsize=12, fontweight="bold"
)
ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
ax.grid(axis="y", alpha=0.3)
ax.set_xlim(by_q["time"].min() - 0.1, by_q["time"].max() + 0.1)

# Panel B — percentage share
ax2 = axes[1]
bottom = np.zeros(len(by_q))
total  = by_q[TYPE_COLS].sum(axis=1).values
for t, col, color in zip(TYPES, TYPE_COLS, colors):
    pct = (by_q[col].values / np.where(total > 0, total, 1)) * 100
    ax2.fill_between(by_q["time"], bottom, bottom + pct, alpha=0.85,
                     color=color, label=t)
    bottom += pct
ax2.set_ylabel("Share of κ (%)", fontsize=11)
ax2.set_xlabel("Year", fontsize=11)
ax2.set_ylim(0, 100)
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax2.grid(axis="y", alpha=0.3)

plt.savefig(PLOTS_DIR / "fig_kappa_decomposition.png", dpi=150, bbox_inches="tight")
plt.show()
print(f"\nSaved → {PLOTS_DIR}/fig_kappa_decomposition.png")

# --- Summary table ---
print("\nFull-sample mean κ contribution by type:")
mean_kappa = by_q["kappa_sym"].mean()
for t, col in zip(TYPES, TYPE_COLS):
    share = by_q[col].mean() / mean_kappa * 100
    print(f"  {t:<15}  {by_q[col].mean():.4f}  ({share:.1f}%)")
print(f"  {'Total':<15}  {mean_kappa:.4f}  (100.0%)")

# --- Top institutions by κ contribution (latest quarter) ---
latest_t = decomp["time"].max()
latest   = decomp[decomp["time"] == latest_t]

# Recompute institution-level contributions for the latest quarter
year_l, quarter_l = int(latest["year"].iloc[0]), int(latest["quarter"].iloc[0])
h_latest = h_agg[(h_agg.year == year_l) & (h_agg.quarter == quarter_l)]
shares_l = shares[(shares.year == year_l) & (shares.quarter == quarter_l)]

inst_records = []
for f, g in pairs:
    hf = h_latest[h_latest.ticker == f].set_index("parent")
    hg = h_latest[h_latest.ticker == g].set_index("parent")
    if hf.empty or hg.empty:
        continue

    universe = hf.index.union(hg.index)
    bf       = hf["beta"].reindex(universe, fill_value=0.0)
    bg       = hg["beta"].reindex(universe, fill_value=0.0)
    type_map = hf["inst_type"].reindex(universe, fill_value="Other")
    pname    = pd.Series({p: parent_to_name.get(p, str(p)) for p in universe})
    ihhi_f   = float((bf ** 2).sum())
    ihhi_g   = float((bg ** 2).sum())

    if ihhi_f <= 0 or ihhi_g <= 0:
        continue

    norm       = (1.0 / ihhi_f + 1.0 / ihhi_g) / 2.0
    cross      = bf * bg
    cross_d    = cross.to_dict()
    type_d     = type_map.to_dict()
    pname_d    = pname.to_dict()

    for parent_id in universe:
        c = float(cross_d.get(parent_id, 0.0))
        if c == 0:
            continue
        inst_records.append({
            "parent":  parent_id,
            "name":    pname_d.get(parent_id, str(parent_id)),
            "type":    type_d.get(parent_id, "Other"),
            "contrib": c * norm,
            "pair":    f"{f}-{g}",
        })

inst_df = pd.DataFrame(inst_records)
top20   = inst_df.groupby(["parent", "name", "type"])["contrib"].mean().reset_index()
top20   = top20.sort_values("contrib", ascending=False).head(20)

print(f"\nTop 20 institutions by mean κ contribution ({year_l}Q{quarter_l}):")
print(top20[["name", "type", "contrib"]].to_string(index=False))
