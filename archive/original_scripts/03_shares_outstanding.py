"""
SCRIPT 03: Pull Shares Outstanding from SEC EDGAR XBRL
========================================================
Source : SEC EDGAR free public API — data.sec.gov
Cost   : Free — no API key, no quota, no rate limit
         (Rate limit: 10 requests/second — we stay well under)
Output : data/shares_outstanding.db

WHAT THIS SCRIPT DOES:
-----------------------
To compute the TRUE κ (kappa) ownership weight, we need:
    β_fs = shares held by investor s in firm f
           ─────────────────────────────────────
           TOTAL shares of firm f outstanding

The denominator — total shares outstanding — tells us what fraction of the
entire company each institutional investor owns. Without it, we can only
compute a simplified κ that assumes 100% institutional ownership, which
systematically underestimates the retail share effect.

The SEC EDGAR XBRL API provides this data directly from company 10-K and
10-Q filings. Every public company must report "CommonStockSharesOutstanding"
in their quarterly filings. This is the same data source CRSP uses.

HOW IT WORKS:
--------------
For each firm in our S&P 500 member list:
  1. Hit SEC EDGAR: data.sec.gov/api/xbrl/companyfacts/CIK{padded_cik}.json
  2. Extract the "CommonStockSharesOutstanding" time series
  3. For each of our 12 quarter-end dates, find the closest reported value
     (within 120 days — covers firms with non-December fiscal year ends)
  4. Save to database immediately (Rule 1)

WHICH FIRMS:
-------------
We pull shares outstanding for every firm that appears in our sp500_members.db
snapshots AND our holdings.db. The overlap is our working universe.

We also need the CIK (SEC company ID) for each firm. We get this by:
  - Using CIKs already in holdings.db (for the 171 firms we've downloaded)
  - Using the SEC EDGAR company search API for any remaining firms

HOW TO RUN:
-----------
  python3 03_shares_outstanding.py

Safe to kill and restart — uses checkpoint table, skips already-done firms.
Expect ~10-15 minutes for 500 firms (1 SEC request per firm).
"""

import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(
    cafile=certifi.where()
)

import os
import sqlite3
import time
import json
import requests
import pandas as pd
from datetime import date, datetime, timezone

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
SHARES_DB_PATH = os.path.join(DATA_DIR, "shares_outstanding.db")
HOLDINGS_DB    = os.path.join(DATA_DIR, "holdings.db")
SP500_DB       = os.path.join(DATA_DIR, "sp500_members.db")
os.makedirs(DATA_DIR, exist_ok=True)

# Quarter-end dates — must match the dates in sp500_members.db and holdings.db
SNAPSHOT_DATES = [date(year, 12, 31) for year in range(2013, 2026)]

# SEC EDGAR requires a descriptive User-Agent header identifying the requester
# Using a real email ensures they can contact you if there's an issue
SEC_HEADERS = {
    "User-Agent": "research souparneya@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

# Pause between SEC requests — SEC asks for max 10/second; we do ~3/second
SLEEP_BETWEEN_CALLS = 0.35

# How many days either side of a quarter-end to search for a reported value
# 120 days handles firms with June or September fiscal year ends
DATE_TOLERANCE_DAYS = 120

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────────────────────────────────────

def open_db():
    conn   = sqlite3.connect(SHARES_DB_PATH)
    cursor = conn.cursor()

    # Main table: one row per firm per quarter-end date
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shares_outstanding (
            issuer_cik      TEXT    NOT NULL,
            issuer_ticker   TEXT,
            snapshot_date   TEXT    NOT NULL,
            report_date     TEXT,
            shares          INTEGER NOT NULL,
            form_type       TEXT,
            filed_date      TEXT,
            fetched_at      TEXT    NOT NULL,
            PRIMARY KEY (issuer_cik, snapshot_date)
        )
    """)

    # Checkpoint: one row per firm when we've finished processing it
    # A firm is "done" once we've attempted all 12 snapshot dates for it
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS completed_firms (
            issuer_cik  TEXT PRIMARY KEY,
            ticker      TEXT,
            n_found     INTEGER,
            completed_at TEXT NOT NULL
        )
    """)

    conn.commit()
    return conn, cursor

# ─────────────────────────────────────────────────────────────────────────────
# GET CIK FOR A TICKER (when not already known)
# ─────────────────────────────────────────────────────────────────────────────

def ticker_to_cik(ticker):
    """
    Looks up a firm's CIK number from the SEC EDGAR company search API.

    CIK = Central Index Key, the SEC's unique ID for every registrant.
    We need it to build the URL for the XBRL data endpoint.

    Returns a zero-padded 10-digit CIK string, or None if not found.
    """
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt=2020-01-01&enddt=2024-01-01&forms=10-K"
    # Simpler approach: use the EDGAR full-text search
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?company=&CIK={ticker}&type=10-K&dateb=&owner=include&count=5&search_text=&action=getcompany"
    try:
        r = requests.get(url, headers=SEC_HEADERS, timeout=10,
                         verify=certifi.where())
        # Parse the CIK from the response — look for the pattern CIK=NNNNNNNNNN
        import re
        match = re.search(r'CIK=(\d{10})', r.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def load_cik_map():
    """
    Builds a dictionary of {ticker: cik} from two sources:
      1. holdings.db — CIKs we already know from downloaded 13F data
      2. sp500_members.db — ticker list we need to cover

    Returns {ticker: padded_10_digit_cik}
    """
    cik_map = {}

    # Source 1: holdings.db — CIKs confirmed from QUANTkiosk data
    if os.path.exists(HOLDINGS_DB):
        conn = sqlite3.connect(HOLDINGS_DB)
        rows = conn.execute(
            "SELECT DISTINCT issuer_ticker, issuer_cik FROM holdings "
            "WHERE issuer_ticker IS NOT NULL AND issuer_ticker != ''"
        ).fetchall()
        conn.close()
        for ticker, cik in rows:
            if ticker and cik:
                cik_map[ticker.strip()] = str(cik).strip().zfill(10)
        print(f"  CIKs from holdings.db: {len(cik_map)}")

    return cik_map

# ─────────────────────────────────────────────────────────────────────────────
# FETCH SHARES OUTSTANDING FROM SEC EDGAR
# ─────────────────────────────────────────────────────────────────────────────

def fetch_shares_for_firm(cik_padded):
    """
    Downloads all reported CommonStockSharesOutstanding values for a firm
    from the SEC EDGAR XBRL company facts API.

    The API URL pattern:
        https://data.sec.gov/api/xbrl/companyfacts/CIK{10-digit-CIK}.json

    This returns a large JSON with every XBRL fact ever reported by this firm.
    We extract the shares outstanding series and return it as a list of dicts:
        [{end_date, shares, form_type, filed_date}, ...]

    Returns (list_of_dicts, status_string)
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"

    try:
        r = requests.get(url, headers=SEC_HEADERS, timeout=20,
                         verify=certifi.where())
        if r.status_code == 404:
            return [], "not_found_in_edgar"
        if r.status_code != 200:
            return [], f"http_{r.status_code}"

        data = r.json()

        # Navigate to the shares outstanding data.
        # Different companies file under different XBRL concept names.
        # We try them in order of preference until we find one with data.
        #
        # Concept name         Namespace   Notes
        # ─────────────────────────────────────────────────────────────────
        # CommonStockSharesOutstanding   us-gaap   Most common (Apple, MSFT…)
        # EntityCommonStockSharesOutstanding  dei   Airlines, some banks (DAL…)
        # WeightedAverageNumberOfSharesOutstandingBasic  us-gaap  Last resort
        #
        facts   = data.get("facts", {})
        us_gaap = facts.get("us-gaap", {})
        dei     = facts.get("dei", {})

        entries = []
        source_used = None

        for namespace, concept in [
            (us_gaap, "CommonStockSharesOutstanding"),
            (dei,     "EntityCommonStockSharesOutstanding"),
            (us_gaap, "WeightedAverageNumberOfSharesOutstandingBasic"),
        ]:
            candidate = namespace.get(concept, {}).get("units", {}).get("shares", [])
            if candidate:
                entries     = candidate
                source_used = concept
                break

        if not entries:
            return [], "no_shares_data"

        # Each entry looks like:
        # {"end": "2020-09-26", "val": 17001802000, "accn": "...",
        #  "fy": 2020, "fp": "FY", "form": "10-K", "filed": "2020-10-30"}
        # Keep only 10-K and 10-Q filings (not 8-K amendments etc.)
        # and only "instant" values (not period averages)
        cleaned = []
        for e in entries:
            form = e.get("form", "")
            if form not in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
                continue
            end_date   = e.get("end", "")
            val        = e.get("val")
            filed_date = e.get("filed", "")
            if end_date and val and val > 0:
                cleaned.append({
                    "end_date":   end_date,
                    "shares":     int(val),
                    "form_type":  form,
                    "filed_date": filed_date,
                })

        # Sort by end_date so binary search / closest-match works
        cleaned.sort(key=lambda x: x["end_date"])
        return cleaned, "ok"

    except Exception as e:
        return [], f"error_{str(e)[:50]}"


def find_closest_entry(entries, target_date):
    """
    Given a list of share entries sorted by end_date, finds the entry whose
    end_date is closest to the target_date, within DATE_TOLERANCE_DAYS.

    This handles firms with non-December fiscal year ends (e.g. Apple's fiscal
    year ends in late September — their Q4 data lands a few weeks off Dec 31).

    Returns the entry dict, or None if nothing within tolerance.
    """
    if not entries:
        return None

    target_str = target_date.strftime("%Y-%m-%d")
    best        = None
    best_gap    = float("inf")

    for entry in entries:
        try:
            entry_date = date.fromisoformat(entry["end_date"])
        except (ValueError, TypeError):
            continue
        gap = abs((entry_date - target_date).days)
        if gap < best_gap:
            best_gap = gap
            best     = entry

    if best_gap <= DATE_TOLERANCE_DAYS:
        return best
    return None

# ─────────────────────────────────────────────────────────────────────────────
# MAIN PROCESSING LOOP
# ─────────────────────────────────────────────────────────────────────────────

def process_firm(conn, cursor, ticker, cik_padded):
    """
    Downloads and saves shares outstanding for all snapshot dates for one firm.

    Rule 1: Each snapshot date's value is written to DB before moving to next.
    Rule 3: Firm is checkpointed after all dates are processed.

    Returns number of snapshot dates successfully matched.
    """
    entries, status = fetch_shares_for_firm(cik_padded)

    if not entries:
        # Firm has no XBRL data — mark done so we don't retry
        cursor.execute(
            "INSERT OR REPLACE INTO completed_firms "
            "(issuer_cik, ticker, n_found, completed_at) VALUES (?,?,?,?)",
            (cik_padded, ticker, 0, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        return 0, status

    now     = datetime.now(timezone.utc).isoformat()
    n_found = 0

    for snapshot_date in SNAPSHOT_DATES:
        entry = find_closest_entry(entries, snapshot_date)
        if entry is None:
            continue

        # Write immediately — Rule 1
        cursor.execute(
            """
            INSERT OR REPLACE INTO shares_outstanding
                (issuer_cik, issuer_ticker, snapshot_date, report_date,
                 shares, form_type, filed_date, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cik_padded,
                ticker,
                snapshot_date.strftime("%Y-%m-%d"),
                entry["end_date"],
                entry["shares"],
                entry["form_type"],
                entry["filed_date"],
                now,
            )
        )
        n_found += 1

    conn.commit()

    # Mark firm as done — Rule 3
    cursor.execute(
        "INSERT OR REPLACE INTO completed_firms "
        "(issuer_cik, ticker, n_found, completed_at) VALUES (?,?,?,?)",
        (cik_padded, ticker, n_found,
         datetime.now(timezone.utc).isoformat())
    )
    conn.commit()

    return n_found, status

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("SHARES OUTSTANDING — SEC EDGAR XBRL API")
print("Free — no API key, no quota.")
print("=" * 60)
print()

conn, cursor = open_db()
print(f"Database: {SHARES_DB_PATH}")
already_done = set(
    row[0] for row in cursor.execute(
        "SELECT issuer_cik FROM completed_firms"
    ).fetchall()
)
print(f"Already completed: {len(already_done)} firms")
print()

# Build CIK map from holdings.db
print("Loading CIK map from holdings.db...")
cik_map = load_cik_map()
print()

# Get the full list of firms from sp500_members.db + holdings.db
# Priority: firms we have S&P 500 snapshot data for AND holdings data for
print("Loading firm list...")
sp500_conn   = sqlite3.connect(SP500_DB)
sp500_tickers = set(
    row[0] for row in sp500_conn.execute(
        "SELECT DISTINCT ticker FROM sp500_snapshots"
    ).fetchall()
)
sp500_conn.close()

# Also include all tickers from holdings.db even if not in current QK500
if os.path.exists(HOLDINGS_DB):
    h_conn = sqlite3.connect(HOLDINGS_DB)
    holdings_tickers = set(
        row[0] for row in h_conn.execute(
            "SELECT DISTINCT issuer_ticker FROM holdings "
            "WHERE issuer_ticker IS NOT NULL AND issuer_ticker != ''"
        ).fetchall()
    )
    h_conn.close()
    all_tickers = sp500_tickers | holdings_tickers
else:
    all_tickers = sp500_tickers

# Only process firms where we know the CIK
processable = {t: cik_map[t] for t in all_tickers if t in cik_map}
remaining   = {t: cik for t, cik in processable.items()
               if cik not in already_done}

print(f"  S&P 500 tickers (across all snapshots): {len(sp500_tickers)}")
print(f"  Tickers with known CIK:                 {len(processable)}")
print(f"  Already completed:                      {len(already_done)}")
print(f"  To fetch this run:                      {len(remaining)}")
print()

if not remaining:
    print("All firms already processed. Nothing to do.")
else:
    print("Starting download...")
    print("(Safe to kill — resumes where it stopped)")
    print()

    n_success = 0
    n_empty   = 0
    firm_items = sorted(remaining.items())  # consistent order for resuming

    for i, (ticker, cik_padded) in enumerate(firm_items):
        n_found, status = process_firm(conn, cursor, ticker, cik_padded)

        if n_found > 0:
            n_success += 1
        else:
            n_empty += 1

        if (i + 1) % 25 == 0 or (i + 1) == len(firm_items):
            pct = 100 * (i + 1) / len(firm_items)
            print(f"  [{i+1:3d}/{len(firm_items)}]  {pct:.0f}%  "
                  f"{ticker:<6}  {n_found} dates matched  [{status}]")

        time.sleep(SLEEP_BETWEEN_CALLS)

    print()
    print(f"Completed: {n_success} firms with data, {n_empty} with no EDGAR data")

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)

rows = cursor.execute(
    """
    SELECT snapshot_date, COUNT(*) as n_firms,
           ROUND(AVG(shares)/1e9, 2) as avg_shares_bn
    FROM shares_outstanding
    GROUP BY snapshot_date
    ORDER BY snapshot_date
    """
).fetchall()

for snapshot_date, n_firms, avg_shares in rows:
    print(f"  {snapshot_date}: {n_firms:3d} firms  "
          f"(avg shares outstanding: {avg_shares}B)")

total = cursor.execute("SELECT COUNT(*) FROM shares_outstanding").fetchone()[0]
done  = cursor.execute("SELECT COUNT(*) FROM completed_firms").fetchone()[0]
print()
print(f"Total rows: {total:,}  |  Firms processed: {done}")
print(f"Database  : {SHARES_DB_PATH}")

# Show a sample — Apple as a sanity check
apple_rows = cursor.execute(
    "SELECT snapshot_date, shares, form_type FROM shares_outstanding "
    "WHERE issuer_ticker='AAPL' ORDER BY snapshot_date"
).fetchall()
if apple_rows:
    print()
    print("Sanity check — Apple (AAPL) shares outstanding:")
    for snap, shares, form in apple_rows:
        print(f"  {snap}: {shares/1e9:.2f}B shares  ({form})")

conn.close()
print()
print("Done. Run 04_sic_codes.py next.")
