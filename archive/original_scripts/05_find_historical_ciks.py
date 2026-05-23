"""
SCRIPT 05: Find CIKs for Historical S&P 500 Firms
==================================================
Source : SEC EDGAR company tickers (active) + EDGAR full-text search (historical)
Cost   : FREE — no API key, no QUANTkiosk credits
Output : data/historical_firms.json

WHAT THIS SCRIPT DOES:
-----------------------
The QK500 reflects TODAY's S&P 500. For historical quarters (2013, 2014, etc.),
some slots were occupied by companies that have since been acquired, merged, or
gone private (e.g. Aetna, Celgene, Dell, Time Warner, RadioShack).

These companies still have historical 13F data in SEC EDGAR under their old CIK
numbers. This script finds those CIKs so we can pull their data in script 06.

The process:
  1. Identify all firms that appear in historical S&P 500 snapshots but are
     NOT in today's QK500
  2. For still-active firms: look up CIK from SEC's company_tickers.json (free)
  3. For acquired/merged firms: search SEC EDGAR full-text by company name
     to find the old CIK from historical filings

WHY THIS MATTERS (no shortcuts):
  If we skip historical firms, we have survivorship bias — we only study
  companies that survived to today. The actual S&P 500 at each point in time
  included ALL 500 firms, including ones that were later acquired.

HOW TO RUN:
-----------
  python3 05_find_historical_ciks.py
  Safe to rerun — builds on existing results, only searches for missing ones.
"""

import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import os, json, time, sqlite3, requests
from datetime import date

DATA_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUTPUT_FILE   = os.path.join(DATA_DIR, "historical_firms.json")
SP500_DB      = os.path.join(DATA_DIR, "sp500_members.db")
UNIVERSE_CACHE= os.path.join(DATA_DIR, "qk500_universe_cache.json")

SEC_HEADERS   = {"User-Agent": "research souparneya@gmail.com"}
SLEEP         = 0.4   # polite pause between SEC requests

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Build the complete list of historical S&P 500 firms we need
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("FINDING CIKs FOR HISTORICAL S&P 500 FIRMS")
print("Free — SEC EDGAR, no API key needed")
print("=" * 60)
print()

# Load today's QK500 tickers — we DON'T need CIKs for these
with open(UNIVERSE_CACHE) as f:
    cache = json.load(f)
qk500_tickers = set(r["ticker"] for r in cache["firms"])
print(f"Current QK500: {len(qk500_tickers)} firms")

# Load ALL historical S&P 500 members across all our snapshot dates
conn = sqlite3.connect(SP500_DB)
all_historical = conn.execute(
    "SELECT DISTINCT ticker, company_name FROM sp500_snapshots"
).fetchall()
all_historical_tickers = {t: n for t, n in all_historical if t}
print(f"Unique firms ever in S&P 500 (2013–2025): {len(all_historical_tickers)}")

# Firms that were in historical S&P 500 but are NOT in today's QK500
need_historical = {
    t: n for t, n in all_historical_tickers.items()
    if t not in qk500_tickers
}
print(f"Historical firms not in current QK500: {len(need_historical)}")

# Also get company names from the changes table (more complete names)
changes = conn.execute(
    "SELECT removed_ticker, removed_name FROM sp500_changes "
    "WHERE removed_ticker IS NOT NULL AND removed_name IS NOT NULL"
).fetchall()
changes_names = {t.strip(): n.strip() for t, n in changes if t and n}

# Merge name sources — prefer changes table (usually more complete)
for ticker in need_historical:
    if ticker in changes_names and changes_names[ticker]:
        need_historical[ticker] = changes_names[ticker]

conn.close()
print()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Load existing results (checkpoint — don't re-search what we found)
# ─────────────────────────────────────────────────────────────────────────────

if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE) as f:
        existing = json.load(f)
    already_found = {r["ticker"]: r["cik"] for r in existing if r.get("cik")}
    already_tried = {r["ticker"] for r in existing}
    print(f"Checkpoint: {len(already_found)} CIKs already found, "
          f"{len(already_tried)} firms already searched")
else:
    existing       = []
    already_found  = {}
    already_tried  = set()
    print("No checkpoint — starting fresh")

remaining = {
    t: n for t, n in need_historical.items()
    if t not in already_tried and t != "nan"
}
print(f"Remaining to search: {len(remaining)} firms")
print()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Source A — SEC company_tickers.json (active companies only)
# This covers firms that changed names or moved exchanges but are still active
# ─────────────────────────────────────────────────────────────────────────────

print("Source A: SEC company_tickers.json (active/current registrants)...")
r = requests.get(
    "https://www.sec.gov/files/company_tickers.json",
    headers=SEC_HEADERS, verify=certifi.where(), timeout=15
)
active_ticker_to_cik = {
    v["ticker"]: str(v["cik_str"]).zfill(10)
    for v in r.json().values()
}
print(f"  {len(active_ticker_to_cik):,} active registrants in SEC file")

source_a_found = {}
for ticker, name in list(remaining.items()):
    if ticker in active_ticker_to_cik:
        cik = active_ticker_to_cik[ticker]
        source_a_found[ticker] = {"ticker": ticker, "name": name, "cik": cik, "source": "sec_active"}
        existing.append(source_a_found[ticker])
        already_found[ticker] = cik
        already_tried.add(ticker)
        del remaining[ticker]

print(f"  Found via Source A: {len(source_a_found)} firms")
print()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Source B — EDGAR full-text search (for acquired/merged companies)
# Searches historical 10-K filings to find the old CIK
# ─────────────────────────────────────────────────────────────────────────────

print(f"Source B: EDGAR full-text search for {len(remaining)} acquired/merged firms...")
print("  (Searching historical 10-K filings — free, ~0.4s per firm)")
print()

source_b_found = 0
source_b_missed = []

for i, (ticker, name) in enumerate(sorted(remaining.items())):
    # Skip special tickers with punctuation (BF.B, BRK.B, nan)
    if not name or name == "nan" or ticker == "nan":
        existing.append({"ticker": ticker, "name": name, "cik": None,
                         "source": "skipped_no_name"})
        already_tried.add(ticker)
        continue

    # Search EDGAR full-text for this company's historical 10-K filings
    # Use a date range that covers before the company was acquired
    search_url = (
        f"https://efts.sec.gov/LATEST/search-index"
        f"?q=%22{requests.utils.quote(name)}%22"
        f"&forms=10-K"
        f"&dateRange=custom&startdt=2010-01-01&enddt=2019-01-01"
    )

    try:
        resp = requests.get(search_url, headers=SEC_HEADERS,
                            verify=certifi.where(), timeout=10)
        hits = resp.json().get("hits", {}).get("hits", [])

        cik = None
        matched_name = None

        # The response contains a 'ciks' list in each hit's _source
        for hit in hits[:3]:   # check first 3 results for best match
            source      = hit.get("_source", {})
            ciks_list   = source.get("ciks", [])
            disp_names  = source.get("display_names", [])

            if ciks_list:
                # Verify this looks like the right company
                # (name should appear in display_names)
                name_lower = name.lower().split()[0]   # first word of company name
                for dn in disp_names:
                    if name_lower in dn.lower():
                        cik          = ciks_list[0].zfill(10)
                        matched_name = dn
                        break
                if cik:
                    break

        if cik:
            source_b_found += 1
            record = {"ticker": ticker, "name": name, "cik": cik,
                      "matched_name": matched_name, "source": "edgar_search"}
            print(f"  ✓ {ticker:<8} {name[:35]:<35} → {cik}  ({matched_name})")
        else:
            source_b_missed.append(ticker)
            record = {"ticker": ticker, "name": name, "cik": None,
                      "source": "not_found"}
            print(f"  ✗ {ticker:<8} {name[:35]:<35} → not found")

        existing.append(record)
        already_tried.add(ticker)

        # Save checkpoint after every 10 firms — rule 1: write immediately
        if (i + 1) % 10 == 0:
            with open(OUTPUT_FILE, "w") as f:
                json.dump(existing, f, indent=2)
            print(f"    [checkpoint saved — {i+1}/{len(remaining)} searched]")

    except Exception as e:
        print(f"  ! {ticker:<8} error: {e}")
        existing.append({"ticker": ticker, "name": name, "cik": None,
                         "source": f"error: {str(e)[:50]}"})
        already_tried.add(ticker)

    time.sleep(SLEEP)

# Final save
with open(OUTPUT_FILE, "w") as f:
    json.dump(existing, f, indent=2)

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

total_found  = sum(1 for r in existing if r.get("cik"))
total_missed = sum(1 for r in existing if not r.get("cik"))

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Historical firms needed   : {len(need_historical)}")
print(f"  CIKs found (Source A)     : {len(source_a_found)}")
print(f"  CIKs found (Source B)     : {source_b_found}")
print(f"  Total CIKs found          : {total_found}")
print(f"  Could not find CIK        : {total_missed}")
if source_b_missed:
    print(f"  Still missing tickers     : {' '.join(source_b_missed[:20])}")
print()
print(f"  Saved to: {OUTPUT_FILE}")
print()
print("Next step: run 06_pull_historical_holdings.py to download")
print("their 13F data for each quarter they were in the S&P 500.")
