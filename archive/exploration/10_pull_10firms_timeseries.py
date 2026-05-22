"""
SCRIPT 10: Pull Full Time Series for 10 New Firms (2013Q3–2025Q4)
==================================================================
Firms: XOM, CVX, VZ, T, KO, PEP, WFC, INTC, WMT, TGT

New within-industry pairs added:
  XOM–CVX  (Energy, SIC 2911)      Oil crash 2014-16; ESG divestment
  VZ–T     (Telecom, SIC 4813)     5G capex; wireless duopoly
  KO–PEP   (Beverages, SIC 2080)   Buffett asymmetry; century rivalry
  WMT–TGT  (Retail, SIC 5331)      Amazon disruption
  INTC–NVDA(Semicon, SIC 3674)     Incumbent displacement

All 10 firms confirmed present in S&P 500 for EVERY quarter 2013Q3-2025Q4.
3 quarters already done from earlier pulls → 47 remaining per firm.
Cost: 10 × 47 × 20 = 9,400 credits.

OUTPUT:
  data/holdings_10firms.csv     — appended to holdings_9firms.csv format
  data/completed_10firms.csv    — checkpoint

USAGE:
  QK_API_KEY=your_key python3.12 scripts/10_pull_10firms_timeseries.py
"""

import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
import urllib.request
_ctx = ssl.create_default_context(cafile=certifi.where())
urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx)))

import os, io, csv, time, requests, pandas as pd
from datetime import datetime, timezone
import qkiosk as qk

# ── Target firms ──────────────────────────────────────────────────────────────
TARGET_FIRMS = [
    # ticker    CIK (stripped)   SIC    industry
    ("XOM",   "34088",          2911,  "Energy"),
    ("CVX",   "93410",          2911,  "Energy"),
    ("VZ",    "732712",         4813,  "Telecom"),
    ("T",     "732717",         4813,  "Telecom"),
    ("KO",    "21344",          2080,  "Beverages"),
    ("PEP",   "77476",          2080,  "Beverages"),
    ("WFC",   "72971",          6022,  "Banks"),
    ("INTC",  "50863",          3674,  "Semiconductors"),
    ("WMT",   "104169",         5331,  "Retail"),
    ("TGT",   "27419",          5331,  "Retail"),
]

QUARTERS = [
    (year, q)
    for year in range(2013, 2026)
    for q    in range(1, 5)
    if not (year == 2013 and q < 3)
]

SLEEP        = 0.35
SOFT_BUFFER  = 200

DATA_DIR       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
HOLDINGS_CSV   = os.path.join(DATA_DIR, "holdings_10firms.csv")
CHECKPOINT_CSV = os.path.join(DATA_DIR, "completed_10firms.csv")

HOLDINGS_COLS   = ["ticker","issuer_cik","issuer_sic","industry",
                   "year","quarter","filer_cik","filer_name","shares_held","fetched_at"]
CHECKPOINT_COLS = ["ticker","issuer_cik","year","quarter","n_investors","completed_at"]

# ── Checkpoint ────────────────────────────────────────────────────────────────
def load_completed():
    done = set()
    if not os.path.exists(CHECKPOINT_CSV):
        return done
    with open(CHECKPOINT_CSV) as f:
        for row in csv.DictReader(f):
            done.add((row["issuer_cik"], int(row["year"]), int(row["quarter"])))
    return done

def write_checkpoint(ticker, cik, year, quarter, n):
    exists = os.path.exists(CHECKPOINT_CSV)
    with open(CHECKPOINT_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CHECKPOINT_COLS)
        if not exists: w.writeheader()
        w.writerow({"ticker":ticker,"issuer_cik":cik,"year":year,
                    "quarter":quarter,"n_investors":n,
                    "completed_at":datetime.now(timezone.utc).isoformat()})

def write_holdings(ticker, cik, sic, industry, df, year, quarter):
    if df.empty: return 0
    equity = (df.query("putCall.isna() and shrsOrPrnAmt > 0", engine="python")
                .groupby("filerCik", as_index=False)
                .agg(filer_name=("filerName","first"), shares_held=("shrsOrPrnAmt","sum")))
    if equity.empty: return 0
    now    = datetime.now(timezone.utc).isoformat()
    exists = os.path.exists(HOLDINGS_CSV)
    with open(HOLDINGS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HOLDINGS_COLS)
        if not exists: w.writeheader()
        for _, row in equity.iterrows():
            w.writerow({"ticker":ticker,"issuer_cik":cik,"issuer_sic":sic,
                        "industry":industry,"year":year,"quarter":quarter,
                        "filer_cik":str(row["filerCik"]),"filer_name":row["filer_name"],
                        "shares_held":int(row["shares_held"]),"fetched_at":now})
    return len(equity)

def fetch(cik, year, quarter):
    api_key    = qk.get_apikey()
    cik_padded = cik.zfill(10)
    url = (f"https://api.qkiosk.io/data/instrument"
           f"?apiKey={api_key}&id={cik_padded}&yyyy={year:04d}&qq={quarter:02d}")
    try:
        r = requests.get(url, verify=certifi.where(), timeout=20)
        if r.status_code == 403: return pd.DataFrame(), "blocked_403"
        if r.status_code == 401: return pd.DataFrame(), "auth_401"
        if r.status_code != 200: return pd.DataFrame(), f"http_{r.status_code}"
        if len(r.content) < 10:  return pd.DataFrame(), "empty"
        return pd.read_csv(io.StringIO(r.content.decode("utf-8"))), "ok"
    except Exception as e:
        return pd.DataFrame(), f"error:{str(e)[:50]}"

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("SCRIPT 10 — 10 New Firms Full Time Series")
    print("=" * 60)

    acct      = qk.account()
    remaining = acct.quota - acct.usage
    print(f"Quota: {acct.usage}/{acct.quota} used | {remaining} remaining")
    print()

    completed = load_completed()

    work = [
        (ticker, cik, sic, industry, year, quarter)
        for (ticker, cik, sic, industry) in TARGET_FIRMS
        for (year, quarter)              in QUARTERS
        if  (cik, year, quarter)         not in completed
    ]

    print(f"Already done:  {len(completed)} firm-quarters")
    print(f"To pull:       {len(work)} firm-quarters")
    print(f"Est. credits:  {len(work) * 20:,}")
    print(f"Budget:        {remaining} available — "
          f"{'OK' if remaining >= len(work)*20 + SOFT_BUFFER else 'TIGHT'}")
    print()

    if not work:
        print("Nothing to do — all firm-quarters already collected.")
        return
    if remaining < SOFT_BUFFER + 20:
        print("Quota too low. Come back tomorrow.")
        return

    calls = 0
    start = time.time()

    for i, (ticker, cik, sic, industry, year, quarter) in enumerate(work):
        if calls > 0 and calls % 50 == 0:
            remaining = qk.account().quota - qk.account().usage
            if remaining <= SOFT_BUFFER:
                print(f"\n  Soft limit reached ({remaining} left). Stopping safely.")
                break

        df, status = fetch(cik, year, quarter)

        if status == "blocked_403":
            print(f"\n  403 block — stopping."); break
        if status == "auth_401":
            print(f"\n  401 Unauthorized — check API key."); break

        n = write_holdings(ticker, cik, sic, industry, df, year, quarter)
        write_checkpoint(ticker, cik, year, quarter, n)
        calls += 1

        elapsed = time.time() - start
        rate    = calls / elapsed if elapsed > 0 else 1
        eta_m   = (len(work) - i - 1) / rate / 60
        flag    = "✓" if n > 0 else ("·" if status == "ok" else "✗")

        print(f"  {flag} [{i+1:>3}/{len(work)}] {ticker:<5} {year}Q{quarter}"
              f"  {n:>4} investors  ETA {eta_m:.0f}m", end="\r")

        if (i + 1) % 50 == 0: print()
        time.sleep(SLEEP)

    print("\n")
    elapsed_total = time.time() - start
    final_rem     = qk.account().quota - qk.account().usage
    completed_f   = load_completed()

    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  Calls made:       {calls}")
    print(f"  Credits used:     ~{calls * 20:,}")
    print(f"  Quota remaining:  {final_rem}")
    print(f"  Time elapsed:     {elapsed_total/60:.1f} minutes")
    print(f"  Holdings CSV:     {HOLDINGS_CSV}")
    print()
    print("Coverage per firm:")
    for (ticker, cik, sic, industry) in TARGET_FIRMS:
        n_done = sum(1 for (c,y,q) in completed_f if c == cik)
        print(f"  {ticker:<5}  {n_done:>3}/50 quarters")

if __name__ == "__main__":
    main()
