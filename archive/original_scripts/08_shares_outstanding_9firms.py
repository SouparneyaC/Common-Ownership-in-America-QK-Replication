import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
import urllib.request
_ctx = ssl.create_default_context(cafile=certifi.where())
urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx)))

import os, csv, time, requests
from datetime import date, datetime, timezone

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUTPUT_CSV = os.path.join(DATA_DIR, "shares_outstanding_9firms.csv")

SEC_HEADERS      = {"User-Agent": "research souparneya@gmail.com"}
DATE_TOLERANCE   = 90    # days — accept filings within this many days of quarter-end
SLEEP            = 0.15  # seconds between SEC requests (well under 10 req/s limit)

# TARGET FIRMS

TARGET_FIRMS = [
    ("AAPL",  "0000320193"),
    ("MSFT",  "0000789019"),
    ("AAL",   "0000006201"),
    ("DAL",   "0000027904"),
    ("JPM",   "0000019617"),
    ("BAC",   "0000070858"),
    ("PFE",   "0000078003"),
    ("MRK",   "0000310158"),
    ("NVDA",  "0001045810"),
]

# All 50 quarter-end dates: 2013Q3 through 2025Q4
QUARTER_ENDS = [
    date(year, month, day)
    for year in range(2013, 2026)
    for (q, month, day) in [(1,3,31),(2,6,30),(3,9,30),(4,12,31)]
    if not (year == 2013 and month < 9)  # skip 2013Q1, Q2
]

# XBRL field names to try in order — different companies use different ones
XBRL_FIELDS = [
    ("us-gaap", "CommonStockSharesOutstanding"),
    ("dei",     "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
]

VALID_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}
OUTPUT_COLS = ["ticker", "cik", "quarter_end", "year", "quarter",
               "shares", "report_date", "form_type", "xbrl_field"]

# HELPERS

def quarter_of(d):
    return (d.month - 1) // 3 + 1

def fetch_xbrl(cik_padded):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
    r = requests.get(url, headers=SEC_HEADERS, verify=certifi.where(), timeout=20)
    if r.status_code != 200:
        return None
    return r.json()

def find_shares(xbrl_data, target_date):
    """Find shares outstanding closest to target_date across all XBRL fields."""
    facts = xbrl_data.get("facts", {})
    best  = None   # (days_diff, shares, report_date, form_type, field_name)

    for namespace, field in XBRL_FIELDS:
        entries = (facts
                   .get(namespace, {})
                   .get(field, {})
                   .get("units", {})
                   .get("shares", []))

        for e in entries:
            if e.get("form", "") not in VALID_FORMS:
                continue
            if not e.get("val") or e["val"] <= 0:
                continue
            try:
                end_date = date.fromisoformat(e["end"])
            except Exception:
                continue

            diff = abs((end_date - target_date).days)
            if diff > DATE_TOLERANCE:
                continue

            if best is None or diff < best[0]:
                best = (diff, e["val"], e["end"], e.get("form",""), field)

    if best:
        return best[1], best[2], best[3], best[4]
    return None, None, None, None

# MAIN

def main():
    print("=" * 60)
    print("SCRIPT 08 — Shares Outstanding for 9 Firms (Quarterly)")
    print("Source: SEC EDGAR XBRL  |  Free, no quota")
    print("=" * 60)
    print(f"Firms:    {len(TARGET_FIRMS)}   Quarters: {len(QUARTER_ENDS)}")
    print(f"Output:   {OUTPUT_CSV}")
    print()

    rows_written = 0
    firms_missing = []

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        writer.writeheader()

        for ticker, cik in TARGET_FIRMS:
            print(f"  {ticker} ({cik})... ", end="", flush=True)

            xbrl = fetch_xbrl(cik)
            if xbrl is None:
                print("FAILED — no XBRL data")
                firms_missing.append(ticker)
                time.sleep(SLEEP)
                continue

            found = 0
            for qdate in QUARTER_ENDS:
                shares, report_date, form_type, field = find_shares(xbrl, qdate)
                if shares:
                    writer.writerow({
                        "ticker":      ticker,
                        "cik":         cik,
                        "quarter_end": qdate.isoformat(),
                        "year":        qdate.year,
                        "quarter":     quarter_of(qdate),
                        "shares":      shares,
                        "report_date": report_date,
                        "form_type":   form_type,
                        "xbrl_field":  field,
                    })
                    rows_written += 1
                    found += 1

            print(f"{found}/{len(QUARTER_ENDS)} quarters found")
            time.sleep(SLEEP)

    print()
    print("=" * 60)
    print(f"Done — {rows_written} rows written to {OUTPUT_CSV}")
    if firms_missing:
        print(f"Missing data: {firms_missing}")
    print()
    print("Next step: run 09_compute_kappa_9firms.py")

if __name__ == "__main__":
    main()
