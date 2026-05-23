"""
SCRIPT 02: Build S&P 500 Historical Composition
=================================================
Source : Wikipedia "List of S&P 500 companies"
Cost   : Free — no API key, no quota, no rate limit
Output : data/sp500_members.db

WHAT THIS SCRIPT DOES:
-----------------------
The paper uses whichever firms were actually IN the S&P 500 index at each
point in time. The index changes: companies get added and removed roughly
20-30 times per year.

This script:
  1. Downloads the current S&P 500 member list from Wikipedia (503 firms)
  2. Downloads the full history of additions and removals (back to 1976)
  3. Reconstructs exactly which firms were in the index on each of our
     quarter-end dates (Dec 31 of 2013 through 2024)
  4. Saves everything to data/sp500_members.db

HOW THE RECONSTRUCTION WORKS:
-------------------------------
Think of it like a timeline:
  - Start with TODAY's list (the current 503 members)
  - Walk backwards through every change event
  - If a firm was ADDED on date D, it was NOT in the index before D
  - If a firm was REMOVED on date D, it WAS in the index before D

By reversing all changes, we can recover the composition at any past date.

IMPORTANT LIMITATION:
----------------------
Wikipedia only records changes going back to around 2000 reliably, and
fully back to 1976 for major events. For our 2013-2024 range, coverage
is complete — there are 19-30 recorded changes per year for that period.

HOW TO RUN:
-----------
  python3 02_sp500_history.py

Safe to rerun — uses INSERT OR REPLACE so no duplicates are created.
"""

import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(
    cafile=certifi.where()
)

import os
import sqlite3
import requests
import pandas as pd
from io import StringIO
from datetime import date, datetime, timezone

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
DB_PATH  = os.path.join(DATA_DIR, "sp500_members.db")
os.makedirs(DATA_DIR, exist_ok=True)

# These are the quarter-end dates we want snapshots for.
# One per year Q4 (Dec 31), matching our QUANTkiosk holdings data.
SNAPSHOT_DATES = [date(year, 12, 31) for year in range(2013, 2026)]

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────────────────────────────────────

def open_db():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Raw changes log from Wikipedia — every addition/removal ever recorded
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sp500_changes (
            change_date    TEXT NOT NULL,
            added_ticker   TEXT,
            added_name     TEXT,
            removed_ticker TEXT,
            removed_name   TEXT,
            reason         TEXT,
            recorded_at    TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_changes_unique
        ON sp500_changes (change_date, added_ticker, removed_ticker)
    """)

    # Current members as of today (the starting point for reconstruction)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sp500_current (
            ticker         TEXT PRIMARY KEY,
            company_name   TEXT,
            gics_sector    TEXT,
            gics_industry  TEXT,
            cik            TEXT,
            recorded_at    TEXT NOT NULL
        )
    """)

    # Reconstructed snapshots — which firms were IN the index at each date
    # This is the table that 05_compute_kappa.py will use to filter firms
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sp500_snapshots (
            snapshot_date  TEXT NOT NULL,
            ticker         TEXT NOT NULL,
            company_name   TEXT,
            PRIMARY KEY (snapshot_date, ticker)
        )
    """)

    conn.commit()
    return conn, cursor

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: FETCH FROM WIKIPEDIA
# ─────────────────────────────────────────────────────────────────────────────

def fetch_wikipedia_tables():
    """
    Downloads the S&P 500 page from Wikipedia and parses its two key tables.

    Wikipedia blocks the default Python user-agent, so we send a browser-like
    header. This is standard practice for research scraping.

    Returns:
        current_df  : DataFrame of current S&P 500 members (~503 rows)
        changes_df  : DataFrame of historical additions/removals
    """
    print("  Fetching Wikipedia S&P 500 page...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (academic research project)"},
        verify=certifi.where(),
        timeout=20
    )
    r.raise_for_status()

    tables = pd.read_html(StringIO(r.text))
    print(f"  Found {len(tables)} tables on the page")

    # Table 0 = current members
    # Table 1 = historical changes (multi-level column header)
    current_df = tables[0]
    changes_raw = tables[1]

    # Flatten the multi-level column header on the changes table
    # Wikipedia uses a header like: ["Effective Date", ("Added","Ticker"), ...]
    changes_raw.columns = [
        "date", "added_ticker", "added_name",
        "removed_ticker", "removed_name", "reason"
    ]

    # Remove the header row that got pulled in as a data row
    changes_df = changes_raw[changes_raw["date"] != "Effective Date"].copy()

    print(f"  Current members   : {len(current_df)} firms")
    print(f"  Historical changes: {len(changes_df)} events")

    return current_df, changes_df

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: SAVE RAW DATA TO DB
# ─────────────────────────────────────────────────────────────────────────────

def save_current_members(conn, cursor, current_df):
    """Saves the current S&P 500 member list to sp500_current."""
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for _, row in current_df.iterrows():
        ticker = str(row.get("Symbol", "") or "").strip()
        if not ticker:
            continue
        cursor.execute(
            """
            INSERT OR REPLACE INTO sp500_current
                (ticker, company_name, gics_sector, gics_industry, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ticker,
                str(row.get("Security", "") or ""),
                str(row.get("GICS Sector", "") or ""),
                str(row.get("GICS Sub-Industry", "") or ""),
                now,
            )
        )
        count += 1
    conn.commit()
    print(f"  Saved {count} current members to sp500_current")


def save_changes(conn, cursor, changes_df):
    """Saves all historical change events to sp500_changes."""
    now = datetime.now(timezone.utc).isoformat()

    # Parse dates — Wikipedia uses formats like "March 23, 2026" or "2020-01-15"
    changes_df = changes_df.copy()
    changes_df["date_parsed"] = pd.to_datetime(
        changes_df["date"], errors="coerce"
    )
    changes_df = changes_df.dropna(subset=["date_parsed"])
    changes_df = changes_df.sort_values("date_parsed")

    count = 0
    for _, row in changes_df.iterrows():
        date_str        = row["date_parsed"].strftime("%Y-%m-%d")
        added_ticker    = str(row["added_ticker"] or "").strip()
        added_name      = str(row["added_name"] or "").strip()
        removed_ticker  = str(row["removed_ticker"] or "").strip()
        removed_name    = str(row["removed_name"] or "").strip()
        reason          = str(row["reason"] or "").strip()

        # INSERT OR IGNORE — safe to rerun
        cursor.execute(
            """
            INSERT OR IGNORE INTO sp500_changes
                (change_date, added_ticker, added_name,
                 removed_ticker, removed_name, reason, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (date_str, added_ticker, added_name,
             removed_ticker, removed_name, reason, now)
        )
        count += 1
    conn.commit()
    print(f"  Saved {count} historical change events to sp500_changes")

    earliest = changes_df["date_parsed"].min().date()
    latest   = changes_df["date_parsed"].max().date()
    print(f"  Coverage: {earliest} → {latest}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: RECONSTRUCT COMPOSITION AT EACH SNAPSHOT DATE
# ─────────────────────────────────────────────────────────────────────────────

def reconstruct_snapshots(conn, cursor):
    """
    Builds the sp500_snapshots table — which firms were IN the index at each
    of our target quarter-end dates.

    HOW IT WORKS:
    We start with the current member list (today's S&P 500). Then we walk
    backwards through every recorded change event. At each event:
      - If a firm was ADDED: before that date it was NOT in the index.
        So if our snapshot date is before the add date, remove it.
      - If a firm was REMOVED: before that date it WAS in the index.
        So if our snapshot date is before the remove date, add it back.

    Example:
      NVDA was added 2001-11-30. For snapshot 2013-12-31 (after that date),
      NVDA IS included. For a hypothetical 2000-12-31 snapshot, it would NOT be.

      TWTR was removed 2022-11-04. For snapshot 2021-12-31 (before removal),
      TWTR IS included. For snapshot 2022-12-31 (after removal), it is NOT.
    """
    # Load current members as our starting set
    current_rows = cursor.execute(
        "SELECT ticker, company_name FROM sp500_current"
    ).fetchall()
    current_set = {row[0]: row[1] for row in current_rows}

    # Load all changes, sorted newest to oldest
    changes = cursor.execute(
        """
        SELECT change_date, added_ticker, added_name, removed_ticker, removed_name
        FROM sp500_changes
        ORDER BY change_date DESC
        """
    ).fetchall()

    today = date.today()
    now   = datetime.now(timezone.utc).isoformat()

    for snapshot_date in SNAPSHOT_DATES:
        # Start from a fresh copy of current members for each snapshot
        composition = dict(current_set)

        # Walk backwards through changes that happened AFTER our snapshot date
        for change_date_str, added_t, added_n, removed_t, removed_n in changes:
            try:
                change_date = date.fromisoformat(change_date_str)
            except (ValueError, TypeError):
                continue

            # Only consider changes that happened AFTER the snapshot date
            # (changes before the snapshot already happened, so they apply)
            if change_date <= snapshot_date:
                break  # we're now looking at changes before snapshot — stop

            # This change happened AFTER our snapshot date, so reverse it:
            # If someone was ADDED after snapshot → they weren't there yet
            if added_t and added_t.strip():
                composition.pop(added_t.strip(), None)

            # If someone was REMOVED after snapshot → they were still there
            if removed_t and removed_t.strip():
                composition[removed_t.strip()] = removed_n or ""

        # Save this snapshot to the database
        snapshot_str = snapshot_date.strftime("%Y-%m-%d")
        cursor.executemany(
            """
            INSERT OR REPLACE INTO sp500_snapshots
                (snapshot_date, ticker, company_name)
            VALUES (?, ?, ?)
            """,
            [(snapshot_str, ticker, name) for ticker, name in composition.items()]
        )
        conn.commit()

        print(f"  {snapshot_str}: {len(composition)} firms in index")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("S&P 500 HISTORICAL COMPOSITION — Wikipedia")
print("Free — no API key, no quota.")
print("=" * 60)
print()

print("Opening database...")
conn, cursor = open_db()
print(f"  {DB_PATH}")
print()

print("STEP 1: Fetching data from Wikipedia...")
current_df, changes_df = fetch_wikipedia_tables()
print()

print("STEP 2: Saving raw data to database...")
save_current_members(conn, cursor, current_df)
save_changes(conn, cursor, changes_df)
print()

print("STEP 3: Reconstructing index composition at each snapshot date...")
print(f"  Target dates: {[str(d) for d in SNAPSHOT_DATES]}")
print()
reconstruct_snapshots(conn, cursor)
print()

# Verification
print("=" * 60)
print("VERIFICATION — firms per snapshot:")
print("=" * 60)
rows = cursor.execute(
    """
    SELECT snapshot_date, COUNT(*) as n_firms
    FROM sp500_snapshots
    GROUP BY snapshot_date
    ORDER BY snapshot_date
    """
).fetchall()
for snapshot_date, n_firms in rows:
    note = "← paper's era ends" if snapshot_date == "2017-12-31" else ""
    print(f"  {snapshot_date}: {n_firms} firms  {note}")

print()
total = cursor.execute("SELECT COUNT(*) FROM sp500_snapshots").fetchone()[0]
changes_total = cursor.execute("SELECT COUNT(*) FROM sp500_changes").fetchone()[0]
print(f"Total rows in sp500_snapshots: {total:,}")
print(f"Total change events recorded : {changes_total}")
print(f"Database: {DB_PATH}")

conn.close()
print()
print("Done. Run 03_shares_outstanding.py next.")
