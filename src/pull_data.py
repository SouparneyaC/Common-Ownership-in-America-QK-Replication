"""
Pull 13(f) institutional holdings from the QUANTkiosk API.

The script pulls issuer-perspective data for every firm in config.FIRMS across
every quarter in config.all_quarters(). "Issuer perspective" means: given a
firm CIK and quarter, return every institution that reported holding shares.

The API charges ~20 credits per call regardless of how many investors are
returned. At the default 10,000 credits/day quota, a full 9-firm × 50-quarter
pull (~450 calls) completes in a single session.

The script is safe to kill and restart at any point. Each completed firm-quarter
is recorded in a checkpoint CSV, and any restart skips work already done.

Usage:
    QK_API_KEY=your_key python3 pull_data.py

Output:
    data/processed/holdings_9firms.csv    one row per (investor × firm × quarter)
    data/processed/completed_9firms.csv   checkpoint tracking what has been pulled
"""

import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import os, io, time, csv, sys, requests, pandas as pd
from datetime import datetime, timezone
import qkiosk as qk
from config import FIRMS, all_quarters, DATA_DIR

# How long to wait between API calls. 0.35s keeps us well under any rate limit
# while still completing a full session in about 3 minutes.
CALL_INTERVAL = 0.35

HOLDINGS_CSV   = DATA_DIR / "holdings_9firms.csv"
CHECKPOINT_CSV = DATA_DIR / "completed_9firms.csv"

HOLDINGS_COLUMNS = [
    "ticker", "cik", "filer_cik", "filer_name",
    "shares_held", "year", "quarter", "pulled_at"
]
CHECKPOINT_COLUMNS = ["ticker", "year", "quarter", "n_investors", "completed_at"]


def already_done(ticker, year, quarter):
    """Check the checkpoint CSV to see if this firm-quarter has been pulled."""
    if not CHECKPOINT_CSV.exists():
        return False
    with open(CHECKPOINT_CSV) as f:
        return any(
            row["ticker"] == ticker
            and int(row["year"]) == year
            and int(row["quarter"]) == quarter
            for row in csv.DictReader(f)
        )


def fetch_holders(cik, year, quarter):
    """
    Fetch all institutional holders of a firm for one quarter.

    Filters out options (put/call positions) and zero-share rows, then
    aggregates across sub-manager CIKs so each economic entity appears once.

    Returns a DataFrame with columns: filer_cik, filer_name, shares_held.
    Returns None if the API returns no data or an error.
    """
    api_key = os.environ["QK_API_KEY"]
    cik_padded = str(cik).zfill(10)
    url = (
        f"https://api.qkiosk.io/data/instrument"
        f"?apiKey={api_key}&id={cik_padded}&yyyy={year:04d}&qq={quarter:02d}"
    )

    resp = requests.get(url, timeout=20, verify=certifi.where())
    if resp.status_code != 200:
        return None

    df = pd.read_csv(io.StringIO(resp.content.decode()))
    if df.empty:
        return None

    # Keep only long equity positions — not options, not zero-share entries
    df = df[df["putCall"].isna() & (df["shrsOrPrnAmt"] > 0)].copy()
    if df.empty:
        return None

    # Sum across sub-entities so e.g. "BlackRock Fund Advisors" and
    # "BlackRock Institutional Trust" collapse into two separate rows here
    # (full entity consolidation happens in compute_kappa.py using the map)
    return (
        df.groupby(["filerCik", "filerName"], as_index=False)["shrsOrPrnAmt"]
        .sum()
        .rename(columns={"filerCik": "filer_cik", "filerName": "filer_name",
                          "shrsOrPrnAmt": "shares_held"})
    )


def append_holdings(rows):
    """Write a batch of holding rows to the CSV, creating the file if needed."""
    write_header = not HOLDINGS_CSV.exists()
    with open(HOLDINGS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HOLDINGS_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def mark_complete(ticker, year, quarter, n_investors):
    """Record a completed firm-quarter in the checkpoint file."""
    write_header = not CHECKPOINT_CSV.exists()
    with open(CHECKPOINT_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CHECKPOINT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "ticker": ticker, "year": year, "quarter": quarter,
            "n_investors": n_investors,
            "completed_at": datetime.now(timezone.utc).isoformat()
        })


def main():
    if "QK_API_KEY" not in os.environ:
        sys.exit("Set QK_API_KEY before running this script.")

    quarters = all_quarters()
    total    = len(FIRMS) * len(quarters)
    done     = sum(
        1 for ticker, _, _, _ in FIRMS
        for y, q in quarters
        if already_done(ticker, y, q)
    )

    print(f"Target: {len(FIRMS)} firms × {len(quarters)} quarters = {total} calls")
    print(f"Already done: {done}  |  Remaining: {total - done}")

    for ticker, cik, _, _ in FIRMS:
        for year, quarter in quarters:
            if already_done(ticker, year, quarter):
                continue

            df = fetch_holders(cik, year, quarter)

            now = datetime.now(timezone.utc).isoformat()
            n   = 0

            if df is not None and not df.empty:
                rows = [
                    {
                        "ticker": ticker, "cik": cik,
                        "filer_cik": str(row.filer_cik),
                        "filer_name": row.filer_name,
                        "shares_held": int(row.shares_held),
                        "year": year, "quarter": quarter,
                        "pulled_at": now
                    }
                    for row in df.itertuples()
                ]
                append_holdings(rows)
                n = len(rows)

            mark_complete(ticker, year, quarter, n)
            print(f"  {ticker} {year}Q{quarter}: {n} investors")
            time.sleep(CALL_INTERVAL)

    print("Done.")


if __name__ == "__main__":
    main()
