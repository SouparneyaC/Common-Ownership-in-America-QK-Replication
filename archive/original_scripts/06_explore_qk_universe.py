"""
SCRIPT 06: Explore QUANTkiosk Universe Options
===============================================

PURPOSE:
  The paper (Backus, Conlon, Sinkinson 2019) covers ALL public US firms with
  market cap >= $10M — roughly 3,000-5,000 firms per quarter, not just the S&P 500.

  Our current pipeline only pulls QK500 (~500 firms). This script answers:
    1. What universe options does QK offer beyond QK500?
    2. How many firms does QK cover in total?
    3. Can we get the full >=10M market cap universe through QK?
    4. What would the cost be in API calls to pull the full universe?

WHAT THIS SCRIPT DOES:
  - Tries several known QK universe names to see which exist
  - For each valid universe, counts the firms and samples a few tickers
  - Checks one firm's instrument response to see what fields are returned
    (specifically looking for market cap or shares outstanding)
  - Saves a summary CSV so we can review the options

OUTPUT:
  ../outputs/explore/qk_universe_options.csv   — one row per universe option
  ../outputs/explore/qk_universe_firms_*.csv   — firm list for each valid universe

COST: ~5-10 API calls (universe fetches only, not instrument pulls)

USAGE:
  python3 06_explore_qk_universe.py
"""

import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import os
import io
import json
import time
import requests
import pandas as pd
import qkiosk as qk
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────────────────────────
# PATHS & CONFIG
# ─────────────────────────────────────────────────────────────────────────────

API_KEY   = os.environ["QK_API_KEY"]
SSL_CERT  = certifi.where()

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "..", "outputs", "explore")
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Universe names to try.
# QK documents QK500 but may have broader options.
# We try common names used by financial data providers.
UNIVERSE_NAMES_TO_TRY = [
    "QK500",       # S&P 500 equivalent — we know this works
    "QK1500",      # S&P 1500 equivalent (large + mid + small cap)
    "QK3000",      # Russell 3000 equivalent
    "QKALL",       # all covered firms
    "QKR3000",     # Russell 3000 variant
    "RUSSELL3000",
    "SP500",
    "SP1500",
    "US",          # all US firms
    "USALL",
]

# For the instrument field exploration, use Apple (always in every universe)
APPLE_CIK = "0000320193"
SAMPLE_YEAR    = 2023
SAMPLE_QUARTER = 4

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: CHECK QUOTA
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("QK UNIVERSE EXPLORATION")
print("=" * 60)
print()

r = requests.get(
    f"https://api.qkiosk.io/account?apiKey={API_KEY}",
    verify=SSL_CERT, timeout=10
)
account = r.json()
remaining = account.get("Quota", 10000) - account.get("Usage", 0)
print(f"Quota: {account.get('Usage',0)} used / {account.get('Quota',10000)} limit "
      f"({remaining} remaining)")
print()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: TRY EACH UNIVERSE NAME
# ─────────────────────────────────────────────────────────────────────────────

print("─" * 60)
print("STEP 2: Testing universe names...")
print("─" * 60)

universe_results = []

for name in UNIVERSE_NAMES_TO_TRY:
    print(f"  Trying universe: {name} ... ", end="", flush=True)
    try:
        univ   = qk.univ(name, cache=False)
        qkids  = list(univ.qkid)
        n      = len(qkids)

        # Parse CIKs from QKIDs (free — no extra call needed)
        # QKID format: "0000320193.0000.001S5N8V8", first 10 chars = CIK
        ciks = [q[:10].lstrip("0") or "0" for q in qkids]

        print(f"FOUND — {n} firms")

        # Try to get tickers (costs ~821 units — only do it for the first valid universe
        # beyond QK500, to avoid burning quota)
        tickers = None
        try:
            tickers = list(univ.to_ticker())
        except Exception as e:
            print(f"    (could not fetch tickers: {e})")

        universe_results.append({
            "universe_name": name,
            "n_firms": n,
            "valid": True,
            "sample_qkids": "; ".join(qkids[:5]),
            "sample_ciks": "; ".join(ciks[:5]),
            "sample_tickers": "; ".join(tickers[:5]) if tickers else "N/A",
        })

        # Save the full firm list for this universe
        firm_df = pd.DataFrame({
            "qkid": qkids,
            "cik":  ciks,
            "ticker": tickers if tickers else [""] * n,
        })
        out_path = os.path.join(OUTPUT_DIR, f"qk_universe_firms_{name}.csv")
        firm_df.to_csv(out_path, index=False)
        print(f"    → Saved {n} firms to {out_path}")

    except Exception as e:
        err_str = str(e)[:80]
        print(f"NOT FOUND or error: {err_str}")
        universe_results.append({
            "universe_name": name,
            "n_firms": 0,
            "valid": False,
            "sample_qkids": "",
            "sample_ciks": "",
            "sample_tickers": "",
        })

    time.sleep(0.5)  # gentle rate limit

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: LOOK AT THE RAW INSTRUMENT API RESPONSE
# What fields does QK return? Is market cap or shares outstanding included?
# ─────────────────────────────────────────────────────────────────────────────

print()
print("─" * 60)
print("STEP 3: Inspect raw instrument response fields for Apple...")
print("─" * 60)

url = (f"https://api.qkiosk.io/data/instrument"
       f"?apiKey={API_KEY}&id={APPLE_CIK}"
       f"&yyyy={SAMPLE_YEAR:04d}&qq={SAMPLE_QUARTER:02d}")

r2 = requests.get(url, verify=SSL_CERT, timeout=20)
print(f"  HTTP {r2.status_code}")

instrument_fields = []
if r2.status_code == 200:
    df_raw = pd.read_csv(io.StringIO(r2.content.decode("utf-8")))
    print(f"  Rows returned: {len(df_raw)}")
    print(f"  Columns ({len(df_raw.columns)}):")
    for col in df_raw.columns:
        sample_vals = df_raw[col].dropna().head(3).tolist()
        print(f"    {col:30s}  sample: {sample_vals}")
        instrument_fields.append({
            "column": col,
            "dtype": str(df_raw[col].dtype),
            "n_non_null": df_raw[col].notna().sum(),
            "sample_values": str(sample_vals),
        })

    # Save the raw response so we can inspect it
    raw_out = os.path.join(OUTPUT_DIR, "qk_instrument_raw_apple_2023Q4.csv")
    df_raw.to_csv(raw_out, index=False)
    print(f"\n  → Raw response saved to {raw_out}")

    # Also save field summary
    fields_df = pd.DataFrame(instrument_fields)
    fields_out = os.path.join(OUTPUT_DIR, "qk_instrument_fields.csv")
    fields_df.to_csv(fields_out, index=False)
    print(f"  → Field summary saved to {fields_out}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: CHECK IF QK HAS A SEPARATE "SHARES OUTSTANDING" OR "MARKET CAP" ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

print()
print("─" * 60)
print("STEP 4: Check for additional QK endpoints (market cap, shares outstanding)...")
print("─" * 60)

# Known QK endpoint patterns to try
# We check whether these exist by hitting them and seeing if we get data back
alt_endpoints = [
    f"https://api.qkiosk.io/data/shares?apiKey={API_KEY}&id={APPLE_CIK}&yyyy={SAMPLE_YEAR}&qq={SAMPLE_QUARTER}",
    f"https://api.qkiosk.io/data/marketcap?apiKey={API_KEY}&id={APPLE_CIK}&yyyy={SAMPLE_YEAR}&qq={SAMPLE_QUARTER}",
    f"https://api.qkiosk.io/data/fundamentals?apiKey={API_KEY}&id={APPLE_CIK}&yyyy={SAMPLE_YEAR}&qq={SAMPLE_QUARTER}",
    f"https://api.qkiosk.io/data/price?apiKey={API_KEY}&id={APPLE_CIK}&yyyy={SAMPLE_YEAR}&qq={SAMPLE_QUARTER}",
    f"https://api.qkiosk.io/data/equity?apiKey={API_KEY}&id={APPLE_CIK}&yyyy={SAMPLE_YEAR}&qq={SAMPLE_QUARTER}",
    f"https://api.qkiosk.io/data/filing?apiKey={API_KEY}&id={APPLE_CIK}&yyyy={SAMPLE_YEAR}&qq={SAMPLE_QUARTER}",
]

endpoint_results = []
for url in alt_endpoints:
    endpoint_name = url.split("/data/")[1].split("?")[0]
    r3 = requests.get(url, verify=SSL_CERT, timeout=10)
    status = r3.status_code
    content_preview = r3.text[:200] if status != 200 else f"OK — {len(r3.content)} bytes"
    print(f"  /data/{endpoint_name:20s}  HTTP {status}  {content_preview[:60]}")
    endpoint_results.append({
        "endpoint": f"/data/{endpoint_name}",
        "http_status": status,
        "response_preview": r3.text[:200],
    })
    time.sleep(0.3)

# Save endpoint probe results
ep_df = pd.DataFrame(endpoint_results)
ep_out = os.path.join(OUTPUT_DIR, "qk_endpoint_probe.csv")
ep_df.to_csv(ep_out, index=False)
print(f"\n  → Endpoint probe results saved to {ep_out}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: SAVE UNIVERSE SUMMARY AND PRINT CONCLUSIONS
# ─────────────────────────────────────────────────────────────────────────────

print()
print("─" * 60)
print("STEP 5: Saving universe summary...")
print("─" * 60)

univ_df = pd.DataFrame(universe_results)
univ_out = os.path.join(OUTPUT_DIR, "qk_universe_options.csv")
univ_df.to_csv(univ_out, index=False)
print(f"  → Saved to {univ_out}")

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
valid_univs = univ_df[univ_df["valid"] == True]
print(f"Valid universes found: {len(valid_univs)}")
for _, row in valid_univs.iterrows():
    print(f"  {row['universe_name']:15s}: {row['n_firms']:,} firms")

# Final quota check
r_end = requests.get(f"https://api.qkiosk.io/account?apiKey={API_KEY}",
                     verify=SSL_CERT, timeout=10)
used_end = r_end.json().get("Usage", 0)
print()
print(f"API calls used this run: {used_end - account.get('Usage', 0)}")
print(f"Remaining quota: {account.get('Quota', 10000) - used_end}")
print()
print("NEXT STEPS: Review the CSVs in outputs/explore/ to decide")
print("which universe covers the paper's >=10M market cap filter.")
