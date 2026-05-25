import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
import urllib.request
_ctx = ssl.create_default_context(cafile=certifi.where())
urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx)))

import os, io, sys, time, csv, requests, pandas as pd
from datetime import datetime, timezone
import qkiosk as qk

# TARGET FIRMS

TARGET_FIRMS = [
    # ticker    CIK (stripped)   SIC    industry
    ("AAPL",   "320193",        3571,  "Tech hardware"),
    ("MSFT",   "789019",        7372,  "Tech software"),
    ("AAL",    "6201",          4512,  "Airlines"),
    ("DAL",    "27904",         4512,  "Airlines"),
    ("JPM",    "19617",         6021,  "Banks"),
    ("BAC",    "70858",         6021,  "Banks"),
    ("PFE",    "78003",         2834,  "Pharma"),
    ("MRK",    "310158",        2834,  "Pharma"),
    ("NVDA",   "1045810",       3674,  "Semiconductors"),
]

QUARTERS = [
    (year, q)
    for year in range(2013, 2026)
    for q    in range(1, 5)
    if not (year == 2013 and q < 3)
]  # 50 quarters: 2013Q3 → 2025Q4

SLEEP       = 0.35
SOFT_BUFFER = 100

DATA_DIR       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
HOLDINGS_CSV   = os.path.join(DATA_DIR, "holdings_9firms.csv")
CHECKPOINT_CSV = os.path.join(DATA_DIR, "completed_9firms.csv")

HOLDINGS_COLS   = ["ticker", "issuer_cik", "issuer_sic", "industry",
                   "year", "quarter", "filer_cik", "filer_name", "shares_held", "fetched_at"]
CHECKPOINT_COLS = ["ticker", "issuer_cik", "year", "quarter", "n_investors", "completed_at"]

# CHECKPOINT — load what's already done

def load_completed():
    """Returns set of (cik, year, quarter) already done."""
    done = set()
    if not os.path.exists(CHECKPOINT_CSV):
        return done
    with open(CHECKPOINT_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            done.add((row["issuer_cik"], int(row["year"]), int(row["quarter"])))
    return done

def write_checkpoint(ticker, cik, year, quarter, n_investors):
    """Append one row to checkpoint CSV immediately."""
    exists = os.path.exists(CHECKPOINT_CSV)
    with open(CHECKPOINT_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CHECKPOINT_COLS)
        if not exists:
            writer.writeheader()
        writer.writerow({
            "ticker":       ticker,
            "issuer_cik":   cik,
            "year":         year,
            "quarter":      quarter,
            "n_investors":  n_investors,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

def write_holdings(ticker, cik, sic, industry, df, year, quarter):
    """Append investor rows to holdings CSV immediately. Returns n rows written."""
    if df.empty:
        return 0

    equity = (df
        .query("putCall.isna() and shrsOrPrnAmt > 0", engine="python")
        .groupby("filerCik", as_index=False)
        .agg(filer_name=("filerName", "first"),
             shares_held=("shrsOrPrnAmt", "sum"))
    )

    if equity.empty:
        return 0

    now    = datetime.now(timezone.utc).isoformat()
    exists = os.path.exists(HOLDINGS_CSV)

    with open(HOLDINGS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HOLDINGS_COLS)
        if not exists:
            writer.writeheader()
        for _, row in equity.iterrows():
            writer.writerow({
                "ticker":      ticker,
                "issuer_cik":  cik,
                "issuer_sic":  sic,
                "industry":    industry,
                "year":        year,
                "quarter":     quarter,
                "filer_cik":   str(row["filerCik"]),
                "filer_name":  row["filer_name"],
                "shares_held": int(row["shares_held"]),
                "fetched_at":  now,
            })

    return len(equity)

# FETCH

def fetch_holders(cik_stripped, year, quarter):
    api_key    = qk.get_apikey()
    cik_padded = cik_stripped.zfill(10)
    url = (f"https://api.qkiosk.io/data/instrument"
           f"?apiKey={api_key}&id={cik_padded}"
           f"&yyyy={year:04d}&qq={quarter:02d}")
    try:
        r = requests.get(url, verify=certifi.where(), timeout=20)
        if r.status_code == 403:  return pd.DataFrame(), "blocked_403"
        if r.status_code == 401:  return pd.DataFrame(), "auth_401"
        if r.status_code != 200:  return pd.DataFrame(), f"http_{r.status_code}"
        if len(r.content) < 10:   return pd.DataFrame(), "empty"
        df = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
        return df, "ok"
    except Exception as e:
        return pd.DataFrame(), f"error:{str(e)[:50]}"

# MAIN

def main():
    print("9-Firm Full Time Series Pull")
    print()

    acct      = qk.account()
    remaining = acct.quota - acct.usage
    print(f"Quota: {acct.usage}/{acct.quota} used  ({remaining} remaining)")
    print()

    # Load checkpoint
    completed = load_completed()
    print(f"Checkpoint: {len(completed)} firm-quarters already done")

    # Build work list
    work = [
        (ticker, cik, sic, industry, year, quarter)
        for (ticker, cik, sic, industry) in TARGET_FIRMS
        for (year, quarter)              in QUARTERS
        if  (cik, year, quarter)         not in completed
    ]

    print(f"To pull:    {len(work)} firm-quarters")
    print(f"Est. cost:  {len(work) * 20:,} credits")
    print(f"Budget:     {remaining} available → "
          f"{'OK' if remaining >= len(work)*20 + SOFT_BUFFER else 'OVER BUDGET'}")
    print()

    if not work:
        print("All done — nothing to pull.")
        return

    if remaining < SOFT_BUFFER + 20:
        print("Quota too low. Come back tomorrow.")
        return

    # Pull loop
    calls_made = 0
    start_time = time.time()

    for i, (ticker, cik, sic, industry, year, quarter) in enumerate(work):

        # Recheck quota every 50 calls
        if calls_made > 0 and calls_made % 50 == 0:
            remaining = qk.account().quota - qk.account().usage
            if remaining <= SOFT_BUFFER:
                print(f"\n  Soft limit reached ({remaining} left). Stopping.")
                break

        df, status = fetch_holders(cik, year, quarter)

        if status == "blocked_403":
            print(f"\n  403 block — sleeping 30s then stopping.")
            time.sleep(30)
            break
        if status == "auth_401":
            print(f"\n  401 Unauthorized — check API key.")
            break

        # Write holdings first, then checkpoint
        n = write_holdings(ticker, cik, sic, industry, df, year, quarter)
        write_checkpoint(ticker, cik, year, quarter, n)
        calls_made += 1

        # Progress
        elapsed = time.time() - start_time
        rate    = calls_made / elapsed if elapsed > 0 else 1
        eta_m   = (len(work) - i - 1) / rate / 60
        flag    = "✓" if n > 0 else ("·" if status == "ok" else "✗")

        print(f"  {flag} [{i+1:>3}/{len(work)}] {ticker:<5} {year}Q{quarter}"
              f"  {n:>4} investors  ETA {eta_m:.0f}m", end="\r")

        if (i + 1) % 50 == 0:
            print()  # newline every 50 so progress is visible

        time.sleep(SLEEP)

    print()

    elapsed_total   = time.time() - start_time
    final_remaining = qk.account().quota - qk.account().usage
    completed_final = load_completed()

    print(f"Done — {calls_made} calls, ~{calls_made * 20:,} credits, "
          f"{elapsed_total/60:.1f} min, {final_remaining} quota remaining")
    print()
    print("Coverage per firm:")
    for (ticker, cik, sic, industry) in TARGET_FIRMS:
        n_done = sum(1 for (c, y, q) in completed_final if c == cik)
        print(f"  {ticker:<5}  {n_done:>3}/50 quarters")

if __name__ == "__main__":
    main()
