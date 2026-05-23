from pathlib import Path

proj_dir  = Path(__file__).parent.parent
data_dir  = proj_dir / 'data' / 'processed'
plots_dir = proj_dir / 'plots'

# ticker, SEC CIK (no leading zeros), 4-digit SIC, industry label
FIRMS = [
    ('AAPL', '320193',  3571, 'Tech'),
    ('MSFT', '789019',  7372, 'Tech'),
    ('AAL',  '6201',    4512, 'Airlines'),
    ('DAL',  '27904',   4512, 'Airlines'),
    ('JPM',  '19617',   6021, 'Banks'),
    ('BAC',  '70858',   6021, 'Banks'),
    ('PFE',  '78003',   2834, 'Pharma'),
    ('MRK',  '310158',  2834, 'Pharma'),
    ('NVDA', '1045810', 3674, 'Semiconductors'),
]

# XML-format 13(f) filings are mandatory from 2013Q3
START_YEAR, START_Q = 2013, 3
END_YEAR,   END_Q   = 2025, 4


def all_quarters():
    return [
        (y, q)
        for y in range(START_YEAR, END_YEAR + 1)
        for q in range(1, 5)
        if (y, q) >= (START_YEAR, START_Q) and (y, q) <= (END_YEAR, END_Q)
    ]


SIC      = {t: s for t, _, s, _ in FIRMS}
INDUSTRY = {t: i for t, _, _, i in FIRMS}
CIK      = {t: c for t, c, _, _ in FIRMS}
TICKERS  = [f[0] for f in FIRMS]
