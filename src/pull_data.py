import ssl, certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import os, io, sys, time, csv, requests, pandas as pd
from datetime import datetime, timezone
from config import FIRMS, all_quarters, data_dir

CALL_INTERVAL = 0.35

holdings_csv   = data_dir / 'holdings_9firms.csv'
checkpoint_csv = data_dir / 'completed_9firms.csv'

holdings_cols   = ['ticker', 'cik', 'filer_cik', 'filer_name',
                   'shares_held', 'year', 'quarter', 'pulled_at']
checkpoint_cols = ['ticker', 'year', 'quarter', 'n_investors', 'completed_at']


def already_done(ticker, year, quarter):
    if not checkpoint_csv.exists():
        return False
    with open(checkpoint_csv) as f:
        return any(
            r['ticker'] == ticker
            and int(r['year']) == year
            and int(r['quarter']) == quarter
            for r in csv.DictReader(f)
        )


def fetch_holders(cik, year, quarter):
    # Returns equity-only holdings aggregated to manager level, or None
    url = (f"https://api.qkiosk.io/data/instrument"
           f"?apiKey={os.environ['QK_API_KEY']}"
           f"&id={str(cik).zfill(10)}&yyyy={year:04d}&qq={quarter:02d}")

    resp = requests.get(url, timeout=20, verify=certifi.where())
    if resp.status_code != 200:
        return None

    df = pd.read_csv(io.StringIO(resp.content.decode()))
    if df.empty:
        return None

    df = df[df['putCall'].isna() & (df['shrsOrPrnAmt'] > 0)].copy()
    if df.empty:
        return None

    return (df.groupby(['filerCik', 'filerName'], as_index=False)['shrsOrPrnAmt']
              .sum()
              .rename(columns={'filerCik': 'filer_cik',
                               'filerName': 'filer_name',
                               'shrsOrPrnAmt': 'shares_held'}))


def append_holdings(rows):
    write_header = not holdings_csv.exists()
    with open(holdings_csv, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=holdings_cols)
        if write_header:
            w.writeheader()
        w.writerows(rows)


def mark_complete(ticker, year, quarter, n):
    write_header = not checkpoint_csv.exists()
    with open(checkpoint_csv, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=checkpoint_cols)
        if write_header:
            w.writeheader()
        w.writerow({'ticker': ticker, 'year': year, 'quarter': quarter,
                    'n_investors': n,
                    'completed_at': datetime.now(timezone.utc).isoformat()})


def main():
    if 'QK_API_KEY' not in os.environ:
        sys.exit('Set QK_API_KEY before running.')

    quarters = all_quarters()
    remaining = sum(
        1 for t, _, _, _ in FIRMS for y, q in quarters
        if not already_done(t, y, q)
    )
    print(f'{len(FIRMS) * len(quarters)} total calls, {remaining} remaining')

    for ticker, cik, _, _ in FIRMS:
        for year, quarter in quarters:
            if already_done(ticker, year, quarter):
                continue

            df  = fetch_holders(cik, year, quarter)
            now = datetime.now(timezone.utc).isoformat()
            n   = 0

            if df is not None and not df.empty:
                append_holdings([
                    {'ticker': ticker, 'cik': cik,
                     'filer_cik': str(r.filer_cik),
                     'filer_name': r.filer_name,
                     'shares_held': int(r.shares_held),
                     'year': year, 'quarter': quarter,
                     'pulled_at': now}
                    for r in df.itertuples()
                ])
                n = len(df)

            mark_complete(ticker, year, quarter, n)
            print(f'  {ticker} {year}Q{quarter}: {n}')
            time.sleep(CALL_INTERVAL)


if __name__ == '__main__':
    main()
