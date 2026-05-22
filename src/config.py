"""
Central configuration for the common ownership replication project.

Editing this file is how you extend the analysis — add firms here and every
downstream script picks them up automatically without touching any other file.
"""

from pathlib import Path

# ── Project paths ─────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data" / "processed"
PLOTS_DIR  = ROOT / "plots"

# ── Firm universe ─────────────────────────────────────────────────────────────
#
# To add a new firm: append a row. The CIK is the SEC identifier — search at
# https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F
#
# Columns: ticker, SEC CIK (no leading zeros), 4-digit SIC code, industry label
#
# SIC codes relevant here:
#   3571 Electronic Computers (Apple hardware)
#   3674 Semiconductors (NVDA)
#   4512 Scheduled Air Transportation
#   6021 National Commercial Banks
#   7372 Prepackaged Software (Microsoft)
#   2834 Pharmaceutical Preparations

FIRMS = [
    # ticker    CIK        SIC    industry
    ("AAPL",  "320193",   3571,  "Tech"),
    ("MSFT",  "789019",   7372,  "Tech"),
    ("AAL",   "6201",     4512,  "Airlines"),
    ("DAL",   "27904",    4512,  "Airlines"),
    ("JPM",   "19617",    6021,  "Banks"),
    ("BAC",   "70858",    6021,  "Banks"),
    ("PFE",   "78003",    2834,  "Pharma"),
    ("MRK",   "310158",   2834,  "Pharma"),
    ("NVDA",  "1045810",  3674,  "Semiconductors"),
]

# ── Quarter range ─────────────────────────────────────────────────────────────
#
# The SEC mandated XML-format 13(f) filings beginning 2013Q3, so that is our
# earliest reliable start date. Extend END_YEAR as new quarters become available.

START_YEAR, START_Q = 2013, 3
END_YEAR,   END_Q   = 2025, 4

def all_quarters():
    """Return a sorted list of (year, quarter) tuples covering the sample range."""
    return [
        (y, q)
        for y in range(START_YEAR, END_YEAR + 1)
        for q in range(1, 5)
        if (y, q) >= (START_YEAR, START_Q) and (y, q) <= (END_YEAR, END_Q)
    ]

# ── SIC lookup ────────────────────────────────────────────────────────────────

SIC = {ticker: sic for ticker, _, sic, _ in FIRMS}
INDUSTRY = {ticker: ind for ticker, _, _, ind in FIRMS}
CIK = {ticker: cik for ticker, cik, _, _ in FIRMS}

TICKERS = [f[0] for f in FIRMS]
