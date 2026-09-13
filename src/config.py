from pathlib import Path

proj_dir  = Path(__file__).parent.parent
data_dir  = proj_dir / 'data' / 'processed'
plots_dir = proj_dir / 'plots'

# ticker, SEC CIK (no leading zeros), 4-digit SIC, industry label
#
# Grown in four pulls, in order:
#   Pilot (9)     — the original case-study firms (airlines/banks/pharma pairs
#                    from the paper's own Section 3.5, plus AAPL/MSFT as
#                    large-cap anchors and NVDA for its ownership-formation story)
#   Batch 2 (10)  — energy, consumer staples, retail, telecom, banks
#   Batch 3 (9)   — Visa (V) was pulled but dropped: no XBRL shares-outstanding
#                    data exists for its multi-class share structure
#   Universe (20) — first 20 alphabetically of the 311 S&P 500 firms that were
#                    index constituents in every annual snapshot 2013-2025,
#                    pulled via a nightly 10-firms/night quota-limited job
#
# Total: 48 firms, 2,256 ordered pairs, 50 quarters = 112,800 κ computations.
FIRMS = [
    # --- Pilot (9) ---
    ('AAPL', '320193',  3571, 'Tech'),
    ('MSFT', '789019',  7372, 'Tech'),
    ('AAL',  '6201',    4512, 'Airlines'),
    ('DAL',  '27904',   4512, 'Airlines'),
    ('JPM',  '19617',   6021, 'Banks'),
    ('BAC',  '70858',   6021, 'Banks'),
    ('PFE',  '78003',   2834, 'Pharma'),
    ('MRK',  '310158',  2834, 'Pharma'),
    ('NVDA', '1045810', 3674, 'Semiconductors'),
    # --- Batch 2 (10) ---
    ('XOM',  '34088',   2911, 'Energy'),
    ('CVX',  '93410',   2911, 'Energy'),
    ('KO',   '21344',   2080, 'Beverages'),
    ('PEP',  '77476',   2080, 'Beverages'),
    ('WMT',  '104169',  5331, 'Retail'),
    ('TGT',  '27419',   5331, 'Retail'),
    ('T',    '732717',  4813, 'Telecom'),
    ('VZ',   '732712',  4813, 'Telecom'),
    ('WFC',  '72971',   6022, 'Banks'),
    ('INTC', '50863',   3674, 'Semiconductors'),
    # --- Batch 3 (9; V pulled but dropped — see note above) ---
    ('AMZN', '1018724', 5961, 'Ecommerce'),
    ('JNJ',  '200406',  2836, 'Pharma'),
    ('PG',   '80424',   2840, 'Consumer Staples'),
    ('MA',   '1141391', 6099, 'Payment Networks'),
    ('UNH',  '731766',  6324, 'Healthcare Insurance'),
    ('GS',   '886982',  6211, 'Investment Banks'),
    ('MS',   '895421',  6211, 'Investment Banks'),
    ('LMT',  '936468',  3812, 'Defense'),
    ('NOC',  '1133421', 3812, 'Defense'),
    # --- Universe, first 20 alphabetically (20) ---
    ('A',    '1090872', 3826, 'Life Science Instruments'),
    ('ABBV', '1551152', 2834, 'Pharma'),
    ('ABT',  '1800',    2834, 'Pharma'),
    ('ACN',  '1467373', 7389, 'Consulting'),
    ('ADBE', '796343',  7372, 'Tech'),
    ('ADI',  '6281',    3674, 'Semiconductors'),
    ('ADM',  '7084',    2070, 'Agribusiness'),
    ('ADP',  '8670',    7374, 'Business Services'),
    ('ADSK', '769397',  7372, 'Tech'),
    ('AEE',  '1002910', 4931, 'Utilities'),
    ('AEP',  '4904',    4911, 'Utilities'),
    ('AES',  '874761',  4991, 'Utilities'),
    ('AFL',  '4977',    6321, 'Insurance'),
    ('AIG',  '5272',    6331, 'Insurance'),
    ('AIZ',  '1267238', 6399, 'Insurance'),
    ('AKAM', '1086222', 7389, 'Internet/Cloud'),
    ('ALL',  '899051',  6331, 'Insurance'),
    ('ALLE', '1579241', 7381, 'Industrials'),
    ('AMAT', '6951',    3674, 'Semiconductors'),
    ('AME',  '1037868', 3823, 'Industrials'),
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
