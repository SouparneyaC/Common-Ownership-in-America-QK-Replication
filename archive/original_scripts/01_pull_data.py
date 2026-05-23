"""
SCRIPT 01: Pull 13(F) Holdings Data from QUANTkiosk
=====================================================
Applies all rules from kalshi_data_collection_rules.md to this pipeline.

RULES IN EFFECT:
  Rule 1 — Every API response is written to SQLite before the next call fires.
  Rule 2 — Deduplication is handled by the database schema (UNIQUE + INSERT OR IGNORE),
            not by application code. Safe to rerun — no duplicates ever created.
  Rule 3 — Script is designed to resume, not restart. Killing it at any point
            loses at most one in-flight request. Everything before it is in the DB.
  Rule 4 — API quota is tracked. A soft limit stops the script before the daily
            budget is exhausted, preserving calls for other uses.
  Rule 5 — Run with --test first to verify one firm writes correctly before
            committing the full run.

USAGE:
  # Step 1: Always test one firm first (costs 1 API call)
  python3 01_pull_data.py --test

  # Step 2: If step 1 shows a row in the DB, run for real
  python3 01_pull_data.py

  # Safe to kill and restart at any time. Already-downloaded firms are skipped.

OUTPUT:
  ../data/holdings.db  — SQLite database with all holdings and progress tracking
"""

import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(
    cafile=certifi.where()
)

import os
import io
import sys
import time
import json
import sqlite3
import requests
import pandas as pd
import qkiosk as qk
from datetime import datetime, timezone

SSL_CERT  = certifi.where()
API_KEY   = os.environ["QK_API_KEY"]

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Q4 of every year from 2013 to 2024 — one snapshot per year.
# Q4 is chosen because annual reports are filed around this time,
# so ownership data is the most complete and stable.
# 12 quarters × 500 firms = 6,000 instrument calls.
# ALL quarters from 2013Q3 through 2025Q4.
#
# WHY ALL QUARTERS — NOT JUST Q4:
#   The paper (Backus, Conlon, Sinkinson 2019) uses every quarter.
#   Pulling only Q4 (annual snapshots) would be a methodological shortcut
#   that undermines the academic integrity of the replication.
#   The paper's regression table has 36M observations — only possible with
#   all quarters. Figures show quarterly time series, not annual dots.
#
# WHY START AT 2013Q3:
#   The SEC made XML-format 13F filings mandatory from 2013Q3.
#   Before that, filings were plain text and harder to parse reliably.
#   QUANTkiosk's data quality is much better from 2013Q3 onwards.
#
# COST: ~50 quarters × 500 firms × 15 credits = ~375,000 credits total
#   At 10,000/day quota: approximately 38 days of daily pulls.
QUARTERS = [
    (year, q)
    for year in range(2013, 2026)   # 2013 through 2025
    for q    in range(1, 5)         # Q1, Q2, Q3, Q4
    if not (year == 2013 and q < 3) # skip 2013Q1 and 2013Q2 (pre-XML, unreliable)
]
# Result: 2013Q3, 2013Q4, 2014Q1, 2014Q2, ..., 2025Q3, 2025Q4 = 50 quarters

DATA_DIR         = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
DB_PATH          = os.path.join(DATA_DIR, "holdings.db")
SIC_DB_PATH      = os.path.join(DATA_DIR, "sic_codes.db")
SP500_DB_PATH    = os.path.join(DATA_DIR, "sp500_members.db")
UNIVERSE_CACHE   = os.path.join(DATA_DIR, "qk500_universe_cache.json")
os.makedirs(DATA_DIR, exist_ok=True)

# Seconds to sleep between API calls.
# 0.35s = ~170 calls/min. Do not lower this.
SLEEP_BETWEEN_CALLS = 0.35

# Rule 4: soft limit is set DYNAMICALLY at startup based on actual remaining quota.
# We keep 60 calls as a hard buffer (for account checks, retries, etc.)
# CALL_BUDGET is set after the quota check below — placeholder here.
QUOTA_BUFFER     = 60
CALL_BUDGET      = None   # set dynamically after quota check
WARN_AT_FRACTION = 0.80   # warn when 80% of today's budget is used

# Where to save the progress report (written at the end of every run)
PROGRESS_REPORT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "progress_report.txt"
)

# ─────────────────────────────────────────────────────────────────────────────
# QUOTA TRACKER
# Counts every API call made this session. Enforces the soft limit.
# ─────────────────────────────────────────────────────────────────────────────

_session_calls = 0

def checked_get(url):
    """
    Makes one HTTP GET request and enforces the session quota soft limit.

    Every API call goes through this function. It:
      - Counts the call
      - Warns when approaching the session budget
      - Raises a clean exception if the budget is reached

    Returns the requests.Response object.
    """
    global _session_calls
    _session_calls += 1

    if CALL_BUDGET is not None and _session_calls >= CALL_BUDGET:
        raise RuntimeError(
            f"\nSession budget reached ({_session_calls} calls used this run).\n"
            f"Stopping cleanly to protect the {QUOTA_BUFFER}-call buffer.\n"
            f"Progress is saved. Resume tomorrow after quota resets."
        )

    warn_at = int((CALL_BUDGET or 9999) * WARN_AT_FRACTION)
    if _session_calls == warn_at:
        print(f"\n  [quota] {_session_calls} calls used this session — "
              f"80% of today's budget. Continuing...")

    return requests.get(url, timeout=20, verify=SSL_CERT)

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE SETUP
# Rule 2: UNIQUE constraints on the natural key.
# The database deduplicates — the script never needs to check for existing rows.
# ─────────────────────────────────────────────────────────────────────────────

def open_sic_db():
    """
    Opens (or creates) the SIC codes database.

    SIC = Standard Industrial Classification.
    A 4-digit number that categorises every company by industry.
    Examples: 4512 = Air Transportation, 6020 = Commercial Banks, 7372 = Software.

    We store one row per firm. The SIC code almost never changes, so this
    table just needs to be populated once and stays valid indefinitely.

    Source: extracted live from the QUANTkiosk 13(F) instrument responses
    as 01_pull_data.py runs. Also backfilled via 04_sic_codes.py from the
    SEC EDGAR submissions API (completely free, no QK quota).
    """
    conn   = sqlite3.connect(SIC_DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sic_codes (
            issuer_cik    TEXT    PRIMARY KEY,
            issuer_ticker TEXT,
            issuer_name   TEXT,
            sic_code      INTEGER,
            updated_at    TEXT    NOT NULL
        )
    """)
    conn.commit()
    return conn, cursor


def upsert_sic(sic_conn, sic_cursor, cik, ticker, name, sic_code):
    """
    Saves or updates the SIC code for one firm.
    INSERT OR REPLACE means running this many times is safe — no duplicates.
    Only updates if we actually have a SIC value (don't overwrite with NULL).
    """
    if sic_code is None:
        return
    sic_cursor.execute(
        """
        INSERT OR REPLACE INTO sic_codes
            (issuer_cik, issuer_ticker, issuer_name, sic_code, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (cik, ticker, name, sic_code,
         datetime.now(timezone.utc).isoformat())
    )
    sic_conn.commit()


def open_db():
    """
    Opens (or creates) the holdings database and creates tables if they
    don't exist yet.

    Two tables:
      holdings       — one row per (investor × firm × quarter).
                       Natural key: (issuer_cik, filer_cik, year, quarter).
                       INSERT OR IGNORE means re-inserting the same row is safe.

      completed_firms — one row per (firm × quarter) that has been fully
                        downloaded. This is the resume checkpoint.
                        Querying this table tells us what to skip on restart.

    Returns a (conn, cursor) tuple.
    """
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Holdings table — the core data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            issuer_cik    TEXT    NOT NULL,
            issuer_name   TEXT,
            issuer_ticker TEXT,
            issuer_sic    INTEGER,
            filer_cik     TEXT    NOT NULL,
            filer_name    TEXT,
            shares_held   INTEGER NOT NULL,
            year          INTEGER NOT NULL,
            quarter       INTEGER NOT NULL,
            fetched_at    TEXT    NOT NULL
        )
    """)

    # Rule 2: Unique constraint — no duplicates even if the script reruns
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_holdings_unique
        ON holdings (issuer_cik, filer_cik, year, quarter)
    """)

    # Checkpoint table — tracks which firms are fully downloaded
    # Rule 3: This is how the script knows what to skip on resume
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS completed_firms (
            issuer_cik    TEXT    NOT NULL,
            year          INTEGER NOT NULL,
            quarter       INTEGER NOT NULL,
            n_investors   INTEGER,
            completed_at  TEXT    NOT NULL,
            PRIMARY KEY (issuer_cik, year, quarter)
        )
    """)

    conn.commit()
    return conn, cursor


def is_firm_done(cursor, cik, year, quarter):
    """Returns True if this firm+quarter is already fully in the database."""
    cursor.execute(
        "SELECT 1 FROM completed_firms WHERE issuer_cik=? AND year=? AND quarter=?",
        (cik, year, quarter)
    )
    return cursor.fetchone() is not None


def write_holdings(conn, cursor, rows, issuer_cik, issuer_name,
                   issuer_ticker, issuer_sic, year, quarter):
    """
    Rule 1: Writes all investor rows for one firm to the database immediately.
    Rule 2: INSERT OR IGNORE — if the row already exists, silently skip it.

    Called once per firm, before moving to the next API call.
    """
    now = datetime.now(timezone.utc).isoformat()
    cursor.executemany(
        """
        INSERT OR IGNORE INTO holdings
            (issuer_cik, issuer_name, issuer_ticker, issuer_sic,
             filer_cik, filer_name, shares_held, year, quarter, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (issuer_cik, issuer_name, issuer_ticker, issuer_sic,
             str(row["filer_cik"]), row["filer_name"], int(row["shares_held"]),
             year, quarter, now)
            for row in rows
        ]
    )
    conn.commit()


def mark_firm_complete(conn, cursor, cik, year, quarter, n_investors):
    """
    Rule 3: Records this firm as done in the checkpoint table.
    Called immediately after write_holdings() succeeds.

    INSERT OR REPLACE means rerunning is safe — it just updates the timestamp.
    """
    cursor.execute(
        """
        INSERT OR REPLACE INTO completed_firms
            (issuer_cik, year, quarter, n_investors, completed_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (cik, year, quarter, n_investors,
         datetime.now(timezone.utc).isoformat())
    )
    conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
# API FETCH — one firm, one quarter
# ─────────────────────────────────────────────────────────────────────────────

def fetch_holders(cik, year, quarter):
    """
    Fetches institutional holders for one firm in one quarter.

    Returns: (list_of_dicts, sic_code, status_string)
      - list_of_dicts: [{filer_cik, filer_name, shares_held}, ...]
      - sic_code: integer SIC industry code, or None
      - status: "ok", "not_found", "blocked_403", "error_..."

    The CIK must be zero-padded to 10 digits for the API.
    Example: "320193" → "0000320193"
    """
    cik_padded = str(cik).lstrip("0").zfill(10)
    url = (f"https://api.qkiosk.io/data/instrument"
           f"?apiKey={API_KEY}&id={cik_padded}"
           f"&yyyy={year:04d}&qq={quarter:02d}")

    try:
        r = checked_get(url)
    except RuntimeError:
        raise  # propagate quota-limit errors upward — do not swallow
    except Exception as e:
        return [], None, f"connection_error: {str(e)[:60]}"

    if r.status_code in (401, 403):
        return [], None, f"blocked_{r.status_code}"

    if r.status_code == 404:
        return [], None, "not_found"  # no 13F for this firm this quarter — normal

    if r.status_code != 200:
        return [], None, f"http_{r.status_code}"

    try:
        df = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
    except Exception as e:
        return [], None, f"parse_error: {str(e)[:60]}"

    if len(df) == 0:
        return [], None, "empty_response"

    # Extract SIC code BEFORE aggregating — it's on every row but we only need it once
    # SIC = Standard Industrial Classification, the industry code for the firm
    sic_code = None
    if "issuerSIC" in df.columns:
        sic_vals = df["issuerSIC"].dropna()
        if len(sic_vals) > 0:
            try:
                sic_code = int(float(sic_vals.iloc[0]))
            except (ValueError, TypeError):
                sic_code = None

    # Keep only equity holdings (not options)
    df = df[df["putCall"].isna()].copy()
    df = df[df["shrsOrPrnAmt"] > 0].copy()

    if len(df) == 0:
        return [], sic_code, "no_equity_holdings"

    # Aggregate sub-manager filings into one row per investor
    df = (df.groupby(["filerCik", "filerName"], as_index=False)
            ["shrsOrPrnAmt"].sum())

    rows = [
        {
            "filer_cik":  str(row["filerCik"]),
            "filer_name": str(row["filerName"]),
            "shares_held": int(row["shrsOrPrnAmt"]),
        }
        for _, row in df.iterrows()
    ]
    return rows, sic_code, "ok"


def get_sic(cik, year, quarter):
    """
    Attempts to extract the SIC code from one API call.
    SIC = Standard Industrial Classification, the industry code.
    Returns an integer or None.
    """
    cik_padded = str(cik).lstrip("0").zfill(10)
    url = (f"https://api.qkiosk.io/data/instrument"
           f"?apiKey={API_KEY}&id={cik_padded}"
           f"&yyyy={year:04d}&qq={quarter:02d}")
    try:
        r = checked_get(url)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
            if "issuerSIC" in df.columns:
                vals = df["issuerSIC"].dropna()
                if len(vals) > 0:
                    return int(float(vals.iloc[0]))
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────────────────────────────────────
# PROCESS ONE QUARTER
# ─────────────────────────────────────────────────────────────────────────────

def process_quarter(conn, cursor, sic_conn, sic_cursor, year, quarter, firm_list):
    """
    Downloads and saves holdings for every firm in one quarter.

    Rule 1: Each firm is written to the DB before moving to the next firm.
    Rule 3: Firms already in completed_firms are skipped entirely.

    Returns True if the quarter completed normally, False if stopped early
    (quota limit or persistent API blocks).
    """
    label      = f"{year}Q{quarter}"
    total      = len(firm_list)
    done_count = cursor.execute(
        "SELECT COUNT(*) FROM completed_firms WHERE year=? AND quarter=?",
        (year, quarter)
    ).fetchone()[0]

    remaining = [(cik, name, ticker) for cik, name, ticker in firm_list
                 if not is_firm_done(cursor, cik, year, quarter)]

    if not remaining:
        print(f"  {label}: all {total} firms already in database. Skipping.")
        return True

    print(f"\n  {label}: {done_count}/{total} done, {len(remaining)} to fetch.")

    consecutive_blocks = 0

    for i, (cik, name, ticker) in enumerate(remaining):

        # ── Fetch ─────────────────────────────────────────────────────────
        # fetch_holders now returns 3 values: investor rows, SIC code, status
        rows, sic_code, status = fetch_holders(cik, year, quarter)

        # Hard block from API — stop before wasting more calls
        if "blocked" in status:
            consecutive_blocks += 1
            print(f"\n  ⚠  API blocked ({status}) on {ticker}. "
                  f"Block #{consecutive_blocks}.")
            if consecutive_blocks >= 3:
                print(f"  Stopping. All progress is in the database.")
                print(f"  Resume by rerunning this script.")
                return False
            time.sleep(3)
            continue
        else:
            consecutive_blocks = 0

        # ── Rule 1: Write holdings to DB immediately ───────────────────────
        if rows:
            write_holdings(
                conn, cursor, rows,
                issuer_cik    = cik,
                issuer_name   = name,
                issuer_ticker = ticker,
                issuer_sic    = sic_code,
                year          = year,
                quarter       = quarter,
            )

        # ── Write SIC code to sic_codes.db immediately ────────────────────
        # SIC comes free from the same API response — no extra call.
        # upsert_sic() is a no-op if sic_code is None.
        upsert_sic(sic_conn, sic_cursor, cik, ticker, name, sic_code)

        # ── Rule 3: Mark firm complete in checkpoint ───────────────────────
        mark_firm_complete(conn, cursor, cik, year, quarter, len(rows))

        # ── Progress ──────────────────────────────────────────────────────
        done_total = done_count + i + 1
        if (i + 1) % 50 == 0 or (i + 1) == len(remaining):
            pct = 100 * done_total / total
            sic_str = str(sic_code) if sic_code else "no SIC"
            print(f"    [{done_total:3d}/{total}]  {pct:.0f}%  "
                  f"{ticker:<6}  {len(rows):4d} investors  "
                  f"SIC:{sic_str:<5}  [{status}]")

        time.sleep(SLEEP_BETWEEN_CALLS)

    print(f"  ✓  {label} complete.")
    return True

# ─────────────────────────────────────────────────────────────────────────────
# PRE-FLIGHT QUOTA CHECK
# ─────────────────────────────────────────────────────────────────────────────

def check_quota():
    """
    Hits the account endpoint to get current quota usage.
    Prints remaining calls and warns if low.
    Returns (used, total, remaining).
    """
    r = requests.get(
        f"https://api.qkiosk.io/account?apiKey={API_KEY}",
        verify=SSL_CERT, timeout=10
    )
    if r.status_code != 200:
        print(f"⚠  Could not check quota (HTTP {r.status_code}). Proceeding.")
        return 0, 10000, 10000

    d         = r.json()
    used      = d.get("Usage",    0)
    total     = d.get("Quota", 10000)
    remaining = total - used

    print(f"  Quota: {used} used / {total} daily limit  ({remaining} remaining)")

    if remaining < 600:
        print(f"\n  ⚠  Only {remaining} calls left today — not enough for a full quarter.")
        print(f"  Consider waiting for the quota to reset.")

    return used, total, remaining


def write_progress_report(cursor2, used_start, used_end, total_quota,
                          stopped_reason):
    """
    Writes a plain-text progress report to data/progress_report.txt.

    This file answers the question: "Where did we stop, and what do we need
    to do tomorrow?" It is overwritten each run so it always reflects the
    most recent state.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("COMMON OWNERSHIP DATA COLLECTION — PROGRESS REPORT")
    lines.append(f"Written: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Stopped because: {stopped_reason}")
    lines.append("")
    lines.append("QUOTA USED THIS SESSION:")
    lines.append(f"  Start of session : {used_start} / {total_quota}")
    lines.append(f"  End of session   : {used_end} / {total_quota}")
    lines.append(f"  Calls this run   : {used_end - used_start}")
    lines.append(f"  Remaining today  : {total_quota - used_end}")
    lines.append(f"  Resets at        : midnight UTC")
    lines.append("")
    lines.append("QUARTERS STATUS:")

    all_complete = True
    for year, quarter in QUARTERS:
        label    = f"{year}Q{quarter}"
        done     = cursor2.execute(
            "SELECT COUNT(*) FROM completed_firms WHERE year=? AND quarter=?",
            (year, quarter)
        ).fetchone()[0]
        rows     = cursor2.execute(
            "SELECT COUNT(*) FROM holdings WHERE year=? AND quarter=?",
            (year, quarter)
        ).fetchone()[0]
        if done == 500:
            status = "COMPLETE"
        elif done > 0:
            status = f"PARTIAL — {done}/500 firms done, resume from firm #{done+1}"
            all_complete = False
        else:
            status = "NOT STARTED"
            all_complete = False
        lines.append(f"  {label}: {status}  ({rows:,} investor rows)")

    lines.append("")
    if all_complete:
        lines.append("ALL QUARTERS COMPLETE. Run 02_compute_kappa.py next.")
    else:
        lines.append("TO RESUME TOMORROW:")
        lines.append("  python3 01_pull_data.py")
        lines.append("  (Script reads the checkpoint DB and skips already-done firms.)")
        lines.append("  No other action needed — it picks up exactly where it stopped.")

    lines.append("")
    total_rows  = cursor2.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
    total_firms = cursor2.execute("SELECT COUNT(*) FROM completed_firms").fetchone()[0]
    lines.append(f"DATABASE TOTALS:")
    lines.append(f"  Holdings rows    : {total_rows:,}")
    lines.append(f"  Firm-quarters    : {total_firms}")
    lines.append(f"  DB file          : {DB_PATH}")
    lines.append("=" * 60)

    report = "\n".join(lines)
    with open(PROGRESS_REPORT, "w") as f:
        f.write(report)

    return report

# ─────────────────────────────────────────────────────────────────────────────
# UNIVERSE LOADER — with disk cache to eliminate repeated overhead
# ─────────────────────────────────────────────────────────────────────────────

def load_universe():
    """
    Returns a list of (cik, name, ticker) for all 500 QK500 firms.

    WHY THIS EXISTS — THE OVERHEAD PROBLEM:
    ----------------------------------------
    The naive approach calls four QUANTkiosk library functions:
        qk.univ("QK500")   → ~500 quota units   (downloads QKID list)
        univ.to_cik()      → ~821 quota units    (downloads master CIK table)
        univ.to_name()     → ~821 quota units    (downloads master name table)
        univ.to_ticker()   → ~821 quota units    (downloads master ticker table)
        Total              : ~2,963 units just to start the script

    These three lookup tables are downloaded from QUANTkiosk's master database
    for ALL their firms, not just QK500. The quota system charges per record
    returned, so you pay for thousands of records you don't need.

    THE FIX — two-part:
    1. Parse CIKs directly from QKIDs (free — no API call needed).
       Every QKID is formatted as: "0000320193.0000.001S5N8V8"
       The first 10 characters ARE the CIK with leading zeros.
       So to_cik() is completely unnecessary.

    2. Cache the universe to disk after the first fetch.
       - First call: qk.univ() (~500 units) + to_ticker() (~821 units) = ~1,321 units
       - Every subsequent call: reads from data/qk500_universe_cache.json = 0 units

    RESULT:
        First run ever   : ~1,321 units overhead (paid once, never again)
        All future runs  : 0 units overhead from universe loading
        Full script cost : 2 account checks = 2 units overhead per run
    """

    # ── If cache exists on disk, use it — zero API calls ──────────────────────
    if os.path.exists(UNIVERSE_CACHE):
        with open(UNIVERSE_CACHE, "r") as f:
            cached = json.load(f)
        firms = [(row["cik"], row["name"], row["ticker"])
                 for row in cached["firms"]]
        print(f"  Loaded from local cache: {len(firms)} firms  (0 API calls used)")
        print(f"  Cache written: {cached['fetched_at'][:10]}")
        return firms

    # ── First time only: fetch from QUANTkiosk ────────────────────────────────
    print("  First run — fetching from QUANTkiosk (paid once, cached forever after)...")

    # Step 1: get the list of 500 QKIDs — unavoidable, costs ~500 units
    univ    = qk.univ("QK500", cache=False)
    qkids   = univ.qkid

    # Step 2: get tickers — costs ~821 units, but we only pay this ONCE EVER
    tickers = univ.to_ticker()

    # Step 3: parse CIK from each QKID — FREE, no API call
    # QKID format: "0000320193.0000.001S5N8V8"
    # First 10 chars = zero-padded CIK → strip leading zeros
    ciks = [q[:10].lstrip("0") or "0" for q in qkids]

    # Step 4: look up company names from sp500_members.db — FREE, local SQLite
    # This avoids the expensive to_name() call entirely
    ticker_to_name = {}
    if os.path.exists(SP500_DB_PATH):
        sp_conn = sqlite3.connect(SP500_DB_PATH)
        rows = sp_conn.execute(
            "SELECT ticker, company_name FROM sp500_current"
        ).fetchall()
        sp_conn.close()
        ticker_to_name = {t: n for t, n in rows}

    # Build the firm list
    firms_data = []
    for qkid, cik, ticker in zip(qkids, ciks, tickers):
        name = ticker_to_name.get(ticker or "", "") or ""
        firms_data.append({
            "qkid":   qkid,
            "cik":    cik,
            "ticker": ticker or "",
            "name":   name,
        })

    # Step 5: save to disk — subsequent runs pay zero for universe loading
    with open(UNIVERSE_CACHE, "w") as f:
        json.dump({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "n_firms":    len(firms_data),
            "firms":      firms_data,
        }, f, indent=2)

    print(f"  Fetched {len(firms_data)} firms, saved to {UNIVERSE_CACHE}")
    print(f"  All future runs will load from cache (0 API calls)")

    return [(row["cik"], row["name"], row["ticker"]) for row in firms_data]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

TEST_MODE = "--test" in sys.argv

print("=" * 60)
if TEST_MODE:
    print("COMMON OWNERSHIP DATA PULL  [TEST MODE — 3 firms only]")
else:
    print("COMMON OWNERSHIP DATA PULL")
print("All rules from kalshi_data_collection_rules.md in effect.")
print("=" * 60)
print()

# ── Pre-flight quota check ───────────────────────────────────────────────────
print("Checking quota...")
used_start, total_quota, remaining = check_quota()

# Rule 4: set the session call budget dynamically based on what's actually left.
# Reserve QUOTA_BUFFER calls for account checks and unexpected retries.
CALL_BUDGET = max(0, remaining - QUOTA_BUFFER)
print(f"  Session budget set to: {CALL_BUDGET} calls "
      f"({remaining} remaining − {QUOTA_BUFFER} buffer)")
print()

# ── Open database ────────────────────────────────────────────────────────────
print(f"Opening holdings database:  {DB_PATH}")
conn, cursor = open_db()
row_count  = cursor.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
firm_count = cursor.execute("SELECT COUNT(*) FROM completed_firms").fetchone()[0]
print(f"  Existing data: {row_count:,} holdings rows, "
      f"{firm_count:,} completed firm-quarters")

print(f"Opening SIC codes database: {SIC_DB_PATH}")
sic_conn, sic_cursor = open_sic_db()
sic_count = sic_cursor.execute("SELECT COUNT(*) FROM sic_codes").fetchone()[0]
print(f"  Existing SIC codes: {sic_count} firms")
print()

# ── Load QK500 universe ──────────────────────────────────────────────────────
print("Loading QK500 universe...")
firm_list = load_universe()
print(f"  {len(firm_list)} firms loaded.")
print()

# ── Rule 5: Test mode — 3 firms, verify DB, then exit ───────────────────────
if TEST_MODE:
    print("TEST MODE: downloading 3 firms for 2023Q4 and verifying DB write.")
    print()
    test_year, test_quarter = 2023, 4

    for cik, name, ticker in firm_list[:3]:
        rows, sic_code, status = fetch_holders(cik, test_year, test_quarter)
        print(f"  {ticker:<6} ({cik}):  {len(rows)} investors  "
              f"SIC:{sic_code}  [{status}]")
        if rows:
            write_holdings(conn, cursor, rows, cik, name, ticker,
                           sic_code, test_year, test_quarter)
        upsert_sic(sic_conn, sic_cursor, cik, ticker, name, sic_code)
        mark_firm_complete(conn, cursor, cik, test_year, test_quarter, len(rows))
        time.sleep(SLEEP_BETWEEN_CALLS)

    count      = cursor.execute(
        "SELECT COUNT(*) FROM holdings WHERE year=2023 AND quarter=4"
    ).fetchone()[0]
    firms_done = cursor.execute(
        "SELECT COUNT(*) FROM completed_firms WHERE year=2023 AND quarter=4"
    ).fetchone()[0]
    sic_saved  = sic_cursor.execute("SELECT COUNT(*) FROM sic_codes").fetchone()[0]
    conn.close()
    sic_conn.close()

    print()
    print("─" * 40)
    print(f"DB verification:")
    print(f"  Holdings rows written : {count}")
    print(f"  Firms marked complete : {firms_done}")
    print(f"  SIC codes saved       : {sic_saved}")
    print()
    if count > 0:
        print("✓ Data confirmed in database. Safe to run without --test.")
        print("  Command: python3 01_pull_data.py")
    else:
        print("✗ NO DATA written. Do NOT run at full scale.")
        print("  Check API key and network, then debug before proceeding.")
    sys.exit(0)

# ── Full run ─────────────────────────────────────────────────────────────────
print("Starting download. Safe to kill at any time — resumes where it stopped.")
print()

stopped_reason = "Completed normally"

try:
    for year, quarter in QUARTERS:
        ok = process_quarter(conn, cursor, sic_conn, sic_cursor,
                             year, quarter, firm_list)
        if not ok:
            stopped_reason = "API blocked (3 consecutive 403s)"
            break

except RuntimeError as e:
    stopped_reason = f"Session budget reached ({_session_calls} calls)"
    print(e)

except KeyboardInterrupt:
    stopped_reason = f"Killed by user after {_session_calls} calls"
    print("\n\nInterrupted. All progress is saved in the database.")

finally:
    conn.close()
    sic_conn.close()

# ── Final summary + progress report ─────────────────────────────────────────
# Re-open DB (previous connection was closed in finally block above)
summary_conn, summary_cursor = open_db()

print()
print("=" * 60)
print("WHAT IS IN THE DATABASE RIGHT NOW:")
print("=" * 60)

for year, quarter in QUARTERS:
    label       = f"{year}Q{quarter}"
    done        = summary_cursor.execute(
        "SELECT COUNT(*) FROM completed_firms WHERE year=? AND quarter=?",
        (year, quarter)
    ).fetchone()[0]
    rows        = summary_cursor.execute(
        "SELECT COUNT(*) FROM holdings WHERE year=? AND quarter=?",
        (year, quarter)
    ).fetchone()[0]
    status_icon = "✓" if done == 500 else ("…" if done > 0 else " ")
    print(f"  {status_icon} {label}: {done:3d}/500 firms, {rows:,} investor rows")

total_rows  = summary_cursor.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
total_firms = summary_cursor.execute("SELECT COUNT(*) FROM completed_firms").fetchone()[0]
db_kb       = os.path.getsize(DB_PATH) / 1024
print()
print(f"  Total : {total_rows:,} rows across {total_firms} firm-quarters")
print(f"  DB    : {db_kb:.0f} KB  →  {DB_PATH}")

# Final quota check
r_end    = requests.get(f"https://api.qkiosk.io/account?apiKey={API_KEY}",
                        verify=SSL_CERT, timeout=10)
used_end = r_end.json().get("Usage", used_start) if r_end.status_code == 200 else used_start

print()
print(f"  API calls this session : {used_end - used_start}")
print(f"  Total used today       : {used_end} / {total_quota}")
print(f"  Remaining              : {total_quota - used_end}")

# Write progress report — always, regardless of how we stopped
report = write_progress_report(
    summary_cursor,
    used_start, used_end, total_quota,
    stopped_reason
)
summary_conn.close()

print()
print("=" * 60)
print("PROGRESS REPORT (also saved to data/progress_report.txt):")
print("=" * 60)
print(report)
