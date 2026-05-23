import os, ssl, certifi, requests
import pandas as pd
import numpy as np

ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
INPUT_CSV  = os.path.join(DATA_DIR, "shares_outstanding_9firms.csv")
OUTPUT_CSV = os.path.join(DATA_DIR, "shares_outstanding_9firms_fixed.csv")
CONTAM_CSV = os.path.join(DATA_DIR, "contaminated_quarters.csv")

print("=" * 60)
print("SCRIPT 08b — Shares Outstanding Audit & Fix")
print("=" * 60)
print()

s = pd.read_csv(INPUT_CSV)
h = pd.read_csv(os.path.join(DATA_DIR, "holdings_9firms.csv"), dtype={"filer_cik": str})

fixes = []
contaminated = []

# FIX 1: AAPL 2014Q1 — multiply shares by 1000

mask_aapl = (s.ticker == "AAPL") & (s.year == 2014) & (s.quarter == 1)
original = s.loc[mask_aapl, "shares"].iloc[0]
corrected = original * 1000

s.loc[mask_aapl, "shares"] = corrected
s.loc[mask_aapl, "notes"] = "FIXED: EDGAR units error — multiplied by 1000"

fixes.append({
    "firm": "AAPL", "quarter": "2014Q1",
    "original": f"{original:,.0f}",
    "corrected": f"{corrected:,.0f}",
    "reason": "EDGAR XBRL filed in thousands, not shares"
})
print(f"FIX 1 — AAPL 2014Q1: {original:,.0f} → {corrected:,.0f}")

# FIX 2: NVDA 2021Q2 — replace post-split shares with pre-split value
# The 4:1 split happened July 19 2021 (calendar Q3).
# Our EDGAR scraper picked up NVDA's fiscal Q2 filing (ending Jul 25)
# which already reflects the post-split count (2,489M).
# The 13F for calendar Q2 (Jun 30) contains pre-split shares held (~429M).
# Pre-split shares outstanding from Q1 2021 = 621M. Use this.

mask_nvda_21q2 = (s.ticker == "NVDA") & (s.year == 2021) & (s.quarter == 2)
q1_shares = s.loc[(s.ticker == "NVDA") & (s.year == 2021) & (s.quarter == 1), "shares"].iloc[0]
post_split_reported = s.loc[mask_nvda_21q2, "shares"].iloc[0]

s.loc[mask_nvda_21q2, "shares"] = q1_shares
s.loc[mask_nvda_21q2, "notes"]  = f"FIXED: replaced post-split {post_split_reported/1e6:.0f}M with pre-split {q1_shares/1e6:.0f}M (split Jul 2021)"

fixes.append({
    "firm": "NVDA", "quarter": "2021Q2",
    "original": f"{post_split_reported:,.0f}",
    "corrected": f"{q1_shares:,.0f}",
    "reason": "Post-split shares (4:1, Jul 2021) matched to pre-split 13F holdings"
})
print(f"FIX 2 — NVDA 2021Q2: {post_split_reported/1e6:.0f}M → {q1_shares/1e6:.0f}M (pre-split)")

# FIX 3: NVDA 2014Q4–2016Q4 — detect convertible note contamination
# When inst_total > total_shares, holdings data is contaminated by
# convertible note reporting. We flag these quarters and compute a
# scaling factor (shares / inst_total) for use in κ computation.

print()
print("Checking NVDA quarters for convertible contamination...")

nvda_s = s[s.ticker == "NVDA"].set_index(["year", "quarter"])

for year in range(2013, 2026):
    for quarter in range(1, 5):
        if year == 2013 and quarter < 3:
            continue
        try:
            shares_out = nvda_s.loc[(year, quarter), "shares"]
        except KeyError:
            continue

        inst_rows = h[(h.ticker == "NVDA") & (h.year == year) & (h.quarter == quarter)]
        inst_total = inst_rows["shares_held"].sum()

        inst_pct = inst_total / shares_out if shares_out > 0 else 0

        if inst_pct > 1.05:   # more than 105% = contaminated
            scale_factor = shares_out / inst_total
            contaminated.append({
                "ticker":       "NVDA",
                "year":         year,
                "quarter":      quarter,
                "shares_out":   shares_out,
                "inst_total":   inst_total,
                "inst_pct":     round(inst_pct, 3),
                "scale_factor": round(scale_factor, 4),
                "reason":       "Convertible note 13F contamination — inst > 100% of shares"
            })
            print(f"  CONTAMINATED: NVDA {year}Q{quarter}  inst={inst_total/1e6:.0f}M "
                  f"shares={shares_out/1e6:.0f}M  "
                  f"ratio={inst_pct:.2f}x  scale={scale_factor:.4f}")

# VERIFY ALL OTHER FIRMS LOOK CLEAN

print()
print("Verifying remaining firms (AAL included — known COVID warrant contamination)...")
for ticker in ["AAPL", "MSFT", "AAL", "DAL", "JPM", "BAC", "PFE", "MRK"]:
    firm_s = s[s.ticker == ticker]
    inst_by_q = h[h.ticker == ticker].groupby(["year","quarter"])["shares_held"].sum().reset_index()
    merged = firm_s.merge(inst_by_q, on=["year","quarter"], how="left")
    merged["inst_pct"] = merged["shares_held"] / merged["shares"]
    bad = merged[merged["inst_pct"] > 1.05]
    if len(bad) > 0:
        for _, r in bad.iterrows():
            scale = r.shares / r.shares_held
            contaminated.append({
                "ticker":       ticker,
                "year":         int(r.year),
                "quarter":      int(r.quarter),
                "shares_out":   r.shares,
                "inst_total":   r.shares_held,
                "inst_pct":     round(r.inst_pct, 3),
                "scale_factor": round(scale, 4),
                "reason":       "COVID warrants/convertibles in 13F" if ticker == "AAL"
                                else "Convertible note contamination"
            })
        print(f"  {ticker}: {len(bad)} contaminated quarters (warrants/convertibles in 13F)")
    else:
        print(f"  {ticker}: OK")

# SAVE

if "notes" not in s.columns:
    s["notes"] = ""
s["notes"] = s["notes"].fillna("")

s.to_csv(OUTPUT_CSV, index=False)
pd.DataFrame(contaminated).to_csv(CONTAM_CSV, index=False)

print()
print("=" * 60)
print("SUMMARY OF FIXES")
print("=" * 60)
for f in fixes:
    print(f"  {f['firm']} {f['quarter']}: {f['original']} → {f['corrected']}")
    print(f"    Reason: {f['reason']}")

print()
print(f"Contaminated NVDA quarters: {len(contaminated)}")
print(f"  (Scale factors saved to {CONTAM_CSV})")
print()
print(f"Fixed shares file → {OUTPUT_CSV}")
