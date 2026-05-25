import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import os, io, sys, time, json, sqlite3, requests, pandas as pd
import qkiosk as qk
from datetime import datetime, timezone

API_KEY = os.environ["QK_API_KEY"]

# 13F XML filings mandatory from 2013Q3; pull all quarters through 2025Q4
QUARTERS = [
    (year, q)
    for year in range(2013, 2026)
    for q    in range(1, 5)
    if not (year == 2013 and q < 3)
]

DATA_DIR        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
DB_PATH         = os.path.join(DATA_DIR, "holdings.db")
SIC_DB_PATH     = os.path.join(DATA_DIR, "sic_codes.db")
SP500_DB_PATH   = os.path.join(DATA_DIR, "sp500_members.db")
UNIVERSE_CACHE  = os.path.join(DATA_DIR, "qk500_universe_cache.json")
PROGRESS_REPORT = os.path.join(DATA_DIR, "progress_report.txt")
os.makedirs(DATA_DIR, exist_ok=True)

SLEEP_BETWEEN_CALLS = 0.35
QUOTA_BUFFER        = 60
WARN_AT_FRACTION    = 0.80

CALL_BUDGET    = None
_session_calls = 0


def checked_get(url):
    global _session_calls
    _session_calls += 1
    if CALL_BUDGET is not None and _session_calls >= CALL_BUDGET:
        raise RuntimeError(
            f"Session budget reached ({_session_calls} calls). "
            f"Stopping to protect the {QUOTA_BUFFER}-call buffer. Resume tomorrow."
        )
    warn_at = int((CALL_BUDGET or 9999) * WARN_AT_FRACTION)
    if _session_calls == warn_at:
        print(f"  [quota] {_session_calls} calls used — 80% of today's budget")
    return requests.get(url, timeout=20, verify=certifi.where())


def open_sic_db():
    conn   = sqlite3.connect(SIC_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sic_codes (
            issuer_cik    TEXT PRIMARY KEY,
            issuer_ticker TEXT,
            issuer_name   TEXT,
            sic_code      INTEGER,
            updated_at    TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn, cursor


def upsert_sic(sic_conn, sic_cursor, cik, ticker, name, sic_code):
    if sic_code is None:
        return
    sic_cursor.execute(
        """INSERT OR REPLACE INTO sic_codes
               (issuer_cik, issuer_ticker, issuer_name, sic_code, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (cik, ticker, name, sic_code, datetime.now(timezone.utc).isoformat())
    )
    sic_conn.commit()


def open_db():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    # UNIQUE constraint deduplicates on re-run without application-level checks
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_holdings_unique
        ON holdings (issuer_cik, filer_cik, year, quarter)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS completed_firms (
            issuer_cik   TEXT    NOT NULL,
            year         INTEGER NOT NULL,
            quarter      INTEGER NOT NULL,
            n_investors  INTEGER,
            completed_at TEXT    NOT NULL,
            PRIMARY KEY (issuer_cik, year, quarter)
        )
    """)
    conn.commit()
    return conn, cursor


def is_firm_done(cursor, cik, year, quarter):
    cursor.execute(
        "SELECT 1 FROM completed_firms WHERE issuer_cik=? AND year=? AND quarter=?",
        (cik, year, quarter)
    )
    return cursor.fetchone() is not None


def write_holdings(conn, cursor, rows, issuer_cik, issuer_name,
                   issuer_ticker, issuer_sic, year, quarter):
    now = datetime.now(timezone.utc).isoformat()
    cursor.executemany(
        """INSERT OR IGNORE INTO holdings
               (issuer_cik, issuer_name, issuer_ticker, issuer_sic,
                filer_cik, filer_name, shares_held, year, quarter, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(issuer_cik, issuer_name, issuer_ticker, issuer_sic,
          str(row["filer_cik"]), row["filer_name"], int(row["shares_held"]),
          year, quarter, now)
         for row in rows]
    )
    conn.commit()


def mark_firm_complete(conn, cursor, cik, year, quarter, n_investors):
    cursor.execute(
        """INSERT OR REPLACE INTO completed_firms
               (issuer_cik, year, quarter, n_investors, completed_at)
           VALUES (?, ?, ?, ?, ?)""",
        (cik, year, quarter, n_investors, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()


def fetch_holders(cik, year, quarter):
    # Returns (list_of_dicts, sic_code, status)
    cik_padded = str(cik).lstrip("0").zfill(10)
    url = (f"https://api.qkiosk.io/data/instrument"
           f"?apiKey={API_KEY}&id={cik_padded}&yyyy={year:04d}&qq={quarter:02d}")
    try:
        r = checked_get(url)
    except RuntimeError:
        raise
    except Exception as e:
        return [], None, f"connection_error: {str(e)[:60]}"

    if r.status_code in (401, 403):
        return [], None, f"blocked_{r.status_code}"
    if r.status_code == 404:
        return [], None, "not_found"
    if r.status_code != 200:
        return [], None, f"http_{r.status_code}"

    try:
        df = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
    except Exception as e:
        return [], None, f"parse_error: {str(e)[:60]}"

    if len(df) == 0:
        return [], None, "empty_response"

    sic_code = None
    if "issuerSIC" in df.columns:
        sic_vals = df["issuerSIC"].dropna()
        if len(sic_vals) > 0:
            try:
                sic_code = int(float(sic_vals.iloc[0]))
            except (ValueError, TypeError):
                pass

    df = df[df["putCall"].isna() & (df["shrsOrPrnAmt"] > 0)].copy()
    if len(df) == 0:
        return [], sic_code, "no_equity_holdings"

    df   = df.groupby(["filerCik", "filerName"], as_index=False)["shrsOrPrnAmt"].sum()
    rows = [{"filer_cik": str(r["filerCik"]), "filer_name": str(r["filerName"]),
             "shares_held": int(r["shrsOrPrnAmt"])} for _, r in df.iterrows()]
    return rows, sic_code, "ok"


def process_quarter(conn, cursor, sic_conn, sic_cursor, year, quarter, firm_list):
    label      = f"{year}Q{quarter}"
    total      = len(firm_list)
    done_count = cursor.execute(
        "SELECT COUNT(*) FROM completed_firms WHERE year=? AND quarter=?",
        (year, quarter)
    ).fetchone()[0]

    remaining = [(cik, name, ticker) for cik, name, ticker in firm_list
                 if not is_firm_done(cursor, cik, year, quarter)]

    if not remaining:
        print(f"  {label}: all {total} firms done, skipping")
        return True

    print(f"\n  {label}: {done_count}/{total} done, {len(remaining)} to fetch")
    consecutive_blocks = 0

    for i, (cik, name, ticker) in enumerate(remaining):
        rows, sic_code, status = fetch_holders(cik, year, quarter)

        if "blocked" in status:
            consecutive_blocks += 1
            print(f"\n  API blocked ({status}) on {ticker} — block #{consecutive_blocks}")
            if consecutive_blocks >= 3:
                print("  Stopping. Resume by rerunning this script.")
                return False
            time.sleep(3)
            continue
        else:
            consecutive_blocks = 0

        if rows:
            write_holdings(conn, cursor, rows, cik, name, ticker, sic_code, year, quarter)
        upsert_sic(sic_conn, sic_cursor, cik, ticker, name, sic_code)
        mark_firm_complete(conn, cursor, cik, year, quarter, len(rows))

        done_total = done_count + i + 1
        if (i + 1) % 50 == 0 or (i + 1) == len(remaining):
            pct     = 100 * done_total / total
            sic_str = str(sic_code) if sic_code else "—"
            print(f"    [{done_total:3d}/{total}]  {pct:.0f}%  "
                  f"{ticker:<6}  {len(rows):4d} investors  SIC:{sic_str}  [{status}]")
        time.sleep(SLEEP_BETWEEN_CALLS)

    print(f"  {label} complete")
    return True


def check_quota():
    r = requests.get(
        f"https://api.qkiosk.io/account?apiKey={API_KEY}",
        verify=certifi.where(), timeout=10
    )
    if r.status_code != 200:
        print(f"Could not check quota (HTTP {r.status_code}), proceeding")
        return 0, 10000, 10000
    d         = r.json()
    used      = d.get("Usage", 0)
    total     = d.get("Quota", 10000)
    remaining = total - used
    print(f"Quota: {used}/{total}  ({remaining} remaining)")
    if remaining < 600:
        print(f"  Warning: only {remaining} calls left today")
    return used, total, remaining


def write_progress_report(cursor, used_start, used_end, total_quota, stopped_reason):
    lines = [
        f"Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Stopped: {stopped_reason}",
        f"Calls this session: {used_end - used_start}  (remaining: {total_quota - used_end})",
        "",
        "Quarter status:",
    ]
    for year, quarter in QUARTERS:
        done = cursor.execute(
            "SELECT COUNT(*) FROM completed_firms WHERE year=? AND quarter=?",
            (year, quarter)
        ).fetchone()[0]
        rows = cursor.execute(
            "SELECT COUNT(*) FROM holdings WHERE year=? AND quarter=?",
            (year, quarter)
        ).fetchone()[0]
        tag = ("COMPLETE" if done == 500
               else (f"partial — {done}/500" if done > 0 else "not started"))
        lines.append(f"  {year}Q{quarter}: {tag}  ({rows:,} rows)")
    total_rows  = cursor.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
    total_firms = cursor.execute("SELECT COUNT(*) FROM completed_firms").fetchone()[0]
    lines.append(f"\nDatabase: {total_rows:,} rows, {total_firms} firm-quarters")
    report = "\n".join(lines)
    with open(PROGRESS_REPORT, "w") as f:
        f.write(report)
    return report


def load_universe():
    # Cache universe after first fetch — avoids ~1,300 credits per subsequent run
    # QKID format "0000320193.0000.001S5N8V8": first 10 chars are the zero-padded CIK
    if os.path.exists(UNIVERSE_CACHE):
        with open(UNIVERSE_CACHE) as f:
            cached = json.load(f)
        firms = [(row["cik"], row["name"], row["ticker"]) for row in cached["firms"]]
        print(f"Universe loaded from cache: {len(firms)} firms  (0 API calls)")
        return firms

    print("Fetching QK500 universe from QUANTkiosk (paid once, cached after)...")
    univ    = qk.univ("QK500", cache=False)
    tickers = univ.to_ticker()
    ciks    = [q[:10].lstrip("0") or "0" for q in univ.qkid]

    ticker_to_name = {}
    if os.path.exists(SP500_DB_PATH):
        sp_conn = sqlite3.connect(SP500_DB_PATH)
        ticker_to_name = dict(sp_conn.execute(
            "SELECT ticker, company_name FROM sp500_current"
        ).fetchall())
        sp_conn.close()

    firms_data = [
        {"qkid": qkid, "cik": cik, "ticker": ticker or "",
         "name": ticker_to_name.get(ticker or "", "")}
        for qkid, cik, ticker in zip(univ.qkid, ciks, tickers)
    ]
    with open(UNIVERSE_CACHE, "w") as f:
        json.dump({"fetched_at": datetime.now(timezone.utc).isoformat(),
                   "n_firms": len(firms_data), "firms": firms_data}, f, indent=2)
    print(f"Fetched {len(firms_data)} firms, cached to {UNIVERSE_CACHE}")
    return [(row["cik"], row["name"], row["ticker"]) for row in firms_data]


TEST_MODE = "--test" in sys.argv

print("Common Ownership Data Pull" + (" [TEST MODE]" if TEST_MODE else ""))
print()

print("Checking quota...")
used_start, total_quota, remaining = check_quota()
CALL_BUDGET = max(0, remaining - QUOTA_BUFFER)
print(f"Session budget: {CALL_BUDGET} calls  ({remaining} remaining − {QUOTA_BUFFER} buffer)")
print()

conn, cursor = open_db()
row_count  = cursor.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
firm_count = cursor.execute("SELECT COUNT(*) FROM completed_firms").fetchone()[0]
print(f"Database: {row_count:,} holdings rows, {firm_count:,} completed firm-quarters")

sic_conn, sic_cursor = open_sic_db()
print()

print("Loading QK500 universe...")
firm_list = load_universe()
print()

if TEST_MODE:
    print("Test mode: 3 firms for 2023Q4")
    for cik, name, ticker in firm_list[:3]:
        rows, sic_code, status = fetch_holders(cik, 2023, 4)
        print(f"  {ticker:<6} ({cik}): {len(rows)} investors  SIC:{sic_code}  [{status}]")
        if rows:
            write_holdings(conn, cursor, rows, cik, name, ticker, sic_code, 2023, 4)
        upsert_sic(sic_conn, sic_cursor, cik, ticker, name, sic_code)
        mark_firm_complete(conn, cursor, cik, 2023, 4, len(rows))
        time.sleep(SLEEP_BETWEEN_CALLS)
    count      = cursor.execute("SELECT COUNT(*) FROM holdings WHERE year=2023 AND quarter=4").fetchone()[0]
    firms_done = cursor.execute("SELECT COUNT(*) FROM completed_firms WHERE year=2023 AND quarter=4").fetchone()[0]
    conn.close()
    sic_conn.close()
    print(f"\nVerification: {count} rows written, {firms_done} firms marked complete")
    print("OK — safe to run without --test" if count > 0 else "FAILED — check API key")
    sys.exit(0)

print("Starting download (safe to kill — resumes where it stopped)")
print()

stopped_reason = "Completed normally"

try:
    for year, quarter in QUARTERS:
        ok = process_quarter(conn, cursor, sic_conn, sic_cursor, year, quarter, firm_list)
        if not ok:
            stopped_reason = "API blocked (3 consecutive)"
            break
except RuntimeError as e:
    stopped_reason = f"Session budget reached ({_session_calls} calls)"
    print(e)
except KeyboardInterrupt:
    stopped_reason = f"Interrupted after {_session_calls} calls"
    print("\nInterrupted — progress saved")
finally:
    conn.close()
    sic_conn.close()

summary_conn, summary_cursor = open_db()
r_end    = requests.get(f"https://api.qkiosk.io/account?apiKey={API_KEY}",
                        verify=certifi.where(), timeout=10)
used_end = r_end.json().get("Usage", used_start) if r_end.status_code == 200 else used_start
print(f"\nSession: {used_end - used_start} calls  |  {total_quota - used_end} remaining")

report = write_progress_report(summary_cursor, used_start, used_end, total_quota, stopped_reason)
summary_conn.close()
print(f"Progress report saved to {PROGRESS_REPORT}")
