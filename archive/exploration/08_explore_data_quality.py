"""
SCRIPT 08: Explore QK Data Quality — Filters and Multi-CIK Consolidation
=========================================================================

PURPOSE:
  The paper applies two data quality rules before computing κ:
    Rule A — 50% filter:  Drop any CUSIP-quarter where ANY investor reports
                           owning >50% of shares outstanding (flags bad data).
    Rule B — 120% filter: Drop any CUSIP-quarter where ALL investors combined
                           report owning >120% of shares outstanding
                           (impossible — means duplicate filings or bad data).
    Rule C — Multi-CIK:   Consolidate investors that file under multiple CIKs
                           (e.g., BlackRock has 10+ CIKs). The paper explicitly
                           merged BlackRock entities before computing κ.

  Our current pipeline does NOT do any of this. This script:
    1. Checks whether QK's API pre-applies these filters
    2. Looks for evidence of multi-CIK investors in our holdings data
    3. Checks if QK provides entity-level groupings (parent company → subsidiaries)
    4. Quantifies how much of our data would be affected by each filter

WHAT WE CHECK:
  For Rule A & B: We need shares outstanding. Without CRSP/EDGAR shrout,
  we cannot compute exact ownership fractions. But we CAN look for signals:
    - Are there any investors with suspiciously high share counts?
    - Does the QK response have a flag column indicating filtered records?

  For Rule C: We look at filer names in our holdings data to identify
  investors that appear to be subsidiaries of the same parent
  (e.g., "BLACKROCK FUND ADVISORS", "BLACKROCK ADVISORS LLC", etc.)

OUTPUT:
  ../outputs/explore/multi_cik_investors.csv    — filers with similar names
  ../outputs/explore/data_quality_flags.csv     — suspicious rows by quarter
  ../outputs/explore/blackrock_entities.csv     — all BlackRock CIKs found
  ../outputs/explore/large_investors_check.csv  — investors with very high shares

COST: 2-3 QK API calls + analysis of existing holdings DB (no extra quota)

USAGE:
  python3 08_explore_data_quality.py
"""

import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import os
import io
import re
import json
import time
import sqlite3
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from collections import Counter

# ─────────────────────────────────────────────────────────────────────────────
# PATHS & CONFIG
# ─────────────────────────────────────────────────────────────────────────────

API_KEY   = os.environ["QK_API_KEY"]
SSL_CERT  = certifi.where()

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "..", "outputs", "explore")
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "holdings.db")

# Known large asset managers that file under multiple CIKs.
# These are the firms the paper explicitly mentions consolidating.
# We'll search our holdings data for any filer whose name contains these strings.
MULTI_CIK_PARENTS = [
    "BLACKROCK",
    "VANGUARD",
    "STATE STREET",
    "FIDELITY",
    "INVESCO",
    "JPMORGAN",
    "GOLDMAN",
    "MORGAN STANLEY",
    "DIMENSIONAL",
    "T. ROWE",
    "WELLINGTON",
    "NORTHERN TRUST",
    "AMERICAN FUNDS",
    "CAPITAL RESEARCH",
    "PIMCO",
]

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: CHECK QUOTA
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("DATA QUALITY & MULTI-CIK EXPLORATION")
print("=" * 60)
print()

r = requests.get(
    f"https://api.qkiosk.io/account?apiKey={API_KEY}",
    verify=SSL_CERT, timeout=10
)
account    = r.json()
used_start = account.get("Usage", 0)
remaining  = account.get("Quota", 10000) - used_start
print(f"Quota: {used_start} used / {account.get('Quota',10000)} limit ({remaining} remaining)")
print()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: INSPECT A RAW QK RESPONSE FOR FILTER-RELATED COLUMNS
# Does QK return any flag columns, putCall handling, or ownership % fields?
# ─────────────────────────────────────────────────────────────────────────────

print("─" * 60)
print("STEP 2: Check raw QK response for filter-related fields...")
print("─" * 60)

# Use a firm we know has many holders — Apple
APPLE_CIK = "0000320193"
url = (f"https://api.qkiosk.io/data/instrument"
       f"?apiKey={API_KEY}&id={APPLE_CIK}"
       f"&yyyy=2020&qq=04")

r2 = requests.get(url, verify=SSL_CERT, timeout=20)
print(f"  Apple 2020Q4 — HTTP {r2.status_code}")

filter_related_cols = []
qk_has_pct_col      = False
qk_has_putcall_col  = False
qk_has_flag_col     = False

if r2.status_code == 200:
    df_apple = pd.read_csv(io.StringIO(r2.content.decode("utf-8")))
    print(f"  Rows: {len(df_apple)} | Columns: {list(df_apple.columns)}")

    # Check for putCall column — does QK include derivatives?
    if "putCall" in df_apple.columns:
        qk_has_putcall_col = True
        pc_vals = df_apple["putCall"].value_counts(dropna=False)
        print(f"\n  putCall column found:")
        print(pc_vals.to_string())
        # If QK returns putCall = NaN for equity, we can filter derivatives ourselves.
        # If QK already strips them, we'll see no non-null putCall values.

    # Check for any ownership percentage column
    pct_cols = [c for c in df_apple.columns
                if any(kw in c.lower() for kw in ["pct", "percent", "fraction", "ratio", "own"])]
    if pct_cols:
        qk_has_pct_col = True
        print(f"\n  Ownership pct columns: {pct_cols}")
        for col in pct_cols:
            print(f"    {col}: {df_apple[col].describe()}")

    # Check for any filter flag column
    flag_cols = [c for c in df_apple.columns
                 if any(kw in c.lower() for kw in ["flag", "filter", "excl", "drop", "warn"])]
    if flag_cols:
        qk_has_flag_col = True
        print(f"\n  Flag columns: {flag_cols}")

    # Check the sole/shared/none voting discretion columns — paper mentions collecting these
    vote_cols = [c for c in df_apple.columns
                 if any(kw in c.lower() for kw in ["vote", "discret", "sole", "shared", "none"])]
    print(f"\n  Voting discretion columns: {vote_cols}")

    # Save for reference
    raw_out = os.path.join(OUTPUT_DIR, "qk_instrument_apple_2020Q4.csv")
    df_apple.to_csv(raw_out, index=False)
    print(f"\n  → Saved raw response to {raw_out}")

time.sleep(0.5)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: MULTI-CIK ANALYSIS — WHO IS FILING UNDER MULTIPLE CIKs?
# Look at all filer names in our holdings DB and find groups with similar names.
# ─────────────────────────────────────────────────────────────────────────────

print()
print("─" * 60)
print("STEP 3: Find multi-CIK investors in our holdings data...")
print("─" * 60)

if not os.path.exists(DB_PATH):
    print(f"  Holdings DB not found at {DB_PATH}. Skipping.")
else:
    conn = sqlite3.connect(DB_PATH)

    # Get all unique (filer_cik, filer_name) pairs
    all_filers = pd.read_sql_query(
        "SELECT DISTINCT filer_cik, filer_name FROM holdings",
        conn
    )
    print(f"  Total distinct filer CIKs: {len(all_filers)}")
    print(f"  (Multiple rows with same name but different CIK = multi-CIK investor)")

    multi_cik_rows = []
    blackrock_rows = []

    for parent in MULTI_CIK_PARENTS:
        # Find all filers whose name contains the parent company's string
        mask = all_filers["filer_name"].str.upper().str.contains(parent, na=False)
        matches = all_filers[mask].copy()

        if len(matches) > 0:
            n_ciks = matches["filer_cik"].nunique()
            print(f"\n  {parent}: {n_ciks} distinct CIKs, {len(matches)} name variants")
            print(matches[["filer_cik", "filer_name"]].head(10).to_string(index=False))

            # Count how many holdings rows each entity contributes
            cik_list = matches["filer_cik"].tolist()
            placeholders = ",".join("?" * len(cik_list))
            holdings_counts = pd.read_sql_query(
                f"""SELECT filer_cik, filer_name, COUNT(*) as n_holdings
                    FROM holdings
                    WHERE filer_cik IN ({placeholders})
                    GROUP BY filer_cik, filer_name
                    ORDER BY n_holdings DESC""",
                conn, params=cik_list
            )
            print(f"  Holdings rows by entity:")
            print(holdings_counts.to_string(index=False))

            for _, row in matches.iterrows():
                multi_cik_rows.append({
                    "parent": parent,
                    "filer_cik": row["filer_cik"],
                    "filer_name": row["filer_name"],
                })

            if "BLACKROCK" in parent:
                blackrock_rows = matches.to_dict("records")

    conn.close()

    # Save results
    multi_df = pd.DataFrame(multi_cik_rows)
    if len(multi_df) > 0:
        multi_out = os.path.join(OUTPUT_DIR, "multi_cik_investors.csv")
        multi_df.to_csv(multi_out, index=False)
        print(f"\n  → Multi-CIK investor list saved to {multi_out}")

    if blackrock_rows:
        br_df = pd.DataFrame(blackrock_rows)
        br_out = os.path.join(OUTPUT_DIR, "blackrock_entities.csv")
        br_df.to_csv(br_out, index=False)
        print(f"  → BlackRock entity list saved to {br_out}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: CHECK WHAT QK'S DOCUMENTATION SAYS ABOUT MULTI-CIK CONSOLIDATION
# Try to pull the same firm in the same quarter using different CIK lookup
# methods to see if QK aggregates sub-entities.
# We do this by looking at filer_ciks returned for Apple and checking if
# names suggest parent-child relationships.
# ─────────────────────────────────────────────────────────────────────────────

print()
print("─" * 60)
print("STEP 4: Does QK consolidate sub-advisor CIKs?")
print("        (checking Apple holders vs known BlackRock CIKs)")
print("─" * 60)

# From our holdings data, pull all BlackRock filer entries for Apple in 2020Q4
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    apple_holders_2020q4 = pd.read_sql_query(
        """SELECT filer_cik, filer_name, shares_held
           FROM holdings
           WHERE issuer_cik IN ('320193', '0000320193')
             AND year = 2020 AND quarter = 4
           ORDER BY shares_held DESC""",
        conn
    )
    conn.close()

    if len(apple_holders_2020q4) > 0:
        print(f"  Apple holders in 2020Q4 from our DB: {len(apple_holders_2020q4)} entries")

        # Flag BlackRock entries
        br_mask = apple_holders_2020q4["filer_name"].str.upper().str.contains("BLACKROCK", na=False)
        br_entries = apple_holders_2020q4[br_mask]
        print(f"\n  BlackRock entries for Apple 2020Q4:")
        print(br_entries.to_string(index=False))

        # Total BlackRock shares if NOT consolidated
        br_total_unconsolidated = br_entries["shares_held"].sum()
        print(f"\n  Total BlackRock shares (unconsolidated): {br_total_unconsolidated:,}")
        print(f"  (Paper would consolidate these into ONE row before computing κ)")

        top20 = apple_holders_2020q4.head(20)
        top20_out = os.path.join(OUTPUT_DIR, "apple_2020q4_top_holders.csv")
        top20.to_csv(top20_out, index=False)
        print(f"\n  → Top 20 Apple holders saved to {top20_out}")
    else:
        print("  No Apple 2020Q4 data in DB (that quarter hasn't been downloaded yet).")
        print("  We'll check using 2013Q3 data instead.")

        conn = sqlite3.connect(DB_PATH)
        apple_2013q3 = pd.read_sql_query(
            """SELECT filer_cik, filer_name, shares_held
               FROM holdings
               WHERE issuer_cik IN ('320193', '0000320193')
                 AND year = 2013 AND quarter = 3
               ORDER BY shares_held DESC""",
            conn
        )
        conn.close()

        if len(apple_2013q3) > 0:
            print(f"  Apple holders in 2013Q3: {len(apple_2013q3)} entries")
            br_mask = apple_2013q3["filer_name"].str.upper().str.contains("BLACKROCK", na=False)
            br_entries = apple_2013q3[br_mask]
            print(f"\n  BlackRock entries for Apple 2013Q3:")
            print(br_entries.to_string(index=False))
            apple_2013q3.head(30).to_csv(
                os.path.join(OUTPUT_DIR, "apple_2013q3_top_holders.csv"), index=False)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: INSPECT DATA QUALITY FLAGS IN OUR HOLDINGS DB
# Look for suspicious patterns: zero shares, very large shares, etc.
# ─────────────────────────────────────────────────────────────────────────────

print()
print("─" * 60)
print("STEP 5: Data quality signals in our holdings DB...")
print("─" * 60)

if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)

    # Zero-share rows (the paper keeps these but notes them as bad data)
    zeros = conn.execute(
        "SELECT year, quarter, COUNT(*) FROM holdings WHERE shares_held = 0 GROUP BY year, quarter"
    ).fetchall()
    print(f"  Zero-share rows: {zeros}")

    # Very large investors (might be >50% ownership flags)
    # Without shrout we can't compute %, but we can flag the biggest holders
    big_holders = pd.read_sql_query(
        """SELECT filer_cik, filer_name, issuer_ticker, year, quarter, shares_held
           FROM holdings
           ORDER BY shares_held DESC
           LIMIT 20""",
        conn
    )
    print(f"\n  Top 20 largest holdings in DB:")
    print(big_holders.to_string(index=False))
    big_holders.to_csv(os.path.join(OUTPUT_DIR, "large_investors_check.csv"), index=False)

    conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: CHECK IF QK HAS A "CONSOLIDATED" MODE OR PARENT-SUBSIDIARY API
# Some financial data providers have a "consolidated entity" endpoint.
# We probe the QK API for this.
# ─────────────────────────────────────────────────────────────────────────────

print()
print("─" * 60)
print("STEP 6: Probe QK for parent/consolidation endpoints...")
print("─" * 60)

consolidation_endpoints = [
    f"https://api.qkiosk.io/data/entity?apiKey={API_KEY}&id=0000876437",   # BlackRock Inc CIK
    f"https://api.qkiosk.io/data/parent?apiKey={API_KEY}&id=0000876437",
    f"https://api.qkiosk.io/data/subsidiaries?apiKey={API_KEY}&id=0000876437",
    f"https://api.qkiosk.io/data/group?apiKey={API_KEY}&id=0000876437",
]

consol_results = []
for url in consolidation_endpoints:
    ep = url.split("/data/")[1].split("?")[0]
    r_ep = requests.get(url, verify=SSL_CERT, timeout=10)
    print(f"  /data/{ep:20s}  HTTP {r_ep.status_code}  {r_ep.text[:80]}")
    consol_results.append({
        "endpoint": f"/data/{ep}",
        "http_status": r_ep.status_code,
        "response": r_ep.text[:200],
    })
    time.sleep(0.3)

pd.DataFrame(consol_results).to_csv(
    os.path.join(OUTPUT_DIR, "qk_consolidation_endpoints.csv"), index=False)

# ─────────────────────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print()
r_end    = requests.get(f"https://api.qkiosk.io/account?apiKey={API_KEY}",
                        verify=SSL_CERT, timeout=10)
used_end = r_end.json().get("Usage", 0)

print("=" * 60)
print("SUMMARY")
print("=" * 60)
print()
print(f"QK returns putCall column (can filter derivatives ourselves): {qk_has_putcall_col}")
print(f"QK returns ownership pct column (has 50%/120% filter):       {qk_has_pct_col}")
print(f"QK returns any filter flag column:                            {qk_has_flag_col}")
print()
print("IMPLICATIONS FOR OUR REPLICATION:")
if not qk_has_pct_col:
    print("  → QK does NOT pre-apply the 50%/120% filter by pct.")
    print("  → We need shares outstanding (from EDGAR) to apply this ourselves.")
if not qk_has_flag_col:
    print("  → QK does NOT flag bad records. Manual filtering required.")
print()
print("  → Multi-CIK consolidation: must be done by us, not QK.")
print("     Check multi_cik_investors.csv for the full list of entities to merge.")
print()
print(f"API calls used this run: {used_end - used_start}")
