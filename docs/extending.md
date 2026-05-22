# Extending the Analysis

This document describes the natural next steps for scaling up the replication.

---

## Adding New Firms

Open `src/config.py` and add a row to the `FIRMS` list:

```python
FIRMS = [
    # existing entries ...
    ("GS",  "886982",  6211, "Banks"),   # Goldman Sachs
    ("UAL", "100517",  4512, "Airlines"), # United Airlines
]
```

Then re-run the pipeline:

```bash
python3 src/pull_data.py      # pulls the new firms; skips already-done ones
python3 src/compute_kappa.py  # recomputes κ for the expanded universe
python3 src/make_plots.py     # regenerates all figures
```

The checkpoint system in `pull_data.py` ensures only new calls are made.

---

## Extending to New Quarters

When a new quarter's 13(f) data becomes available on QUANTkiosk (typically
about 45–60 days after the quarter ends), update `END_YEAR` and `END_Q` in
`src/config.py` and run the pipeline again:

```python
END_YEAR, END_Q = 2026, 1   # or whatever the new endpoint is
```

---

## Scaling to the Full S&P 500

The 9-firm universe is a proof of concept. Scaling to the full ~500-firm index
requires addressing two things:

**1. API budget.** At ~20 credits per call and 500 firms × 50 quarters, the full
pull requires ~500,000 credits — about 50 days at the standard 10,000/day quota.
The pull script is already designed to run over multiple days and resume cleanly.
The practical path is either (a) a rate-limited daily run, or (b) requesting a
higher quota from QUANTkiosk directly.

**2. Historical S&P 500 membership.** The current universe uses the current QK500
list. For a proper replication, each quarter should use the S&P 500 composition
as it stood at that point in time. The file `data/reference/historical_firms.json`
contains the reconstruction from Wikipedia. The pull script would need to read that
file to determine which firms to pull for each quarter.

---

## Pre-XML Extension (1999–2013Q2)

The file `scrape_parsed.csv` (see `docs/data_guide.md`) contains parsed 13(f)
holdings from 1999 through 2017Q3, covering the pre-XML era. To use it for κ
computation, the main gap is company identification:

The pre-XML data identifies securities by **CUSIP**, not by SEC CIK. Bridging
this requires a CUSIP → CIK crosswalk, available through:
- **CRSP** (via WRDS academic license) — complete historical crosswalk
- **OpenFIGI API** (`https://api.openfigi.com/v3/mapping`) — free, ~85–90% coverage

The entity consolidation map in `data/processed/entity_consolidation_map.csv`
covers the post-2013 era. Extending it to pre-2013 requires adding historical
subsidiary-to-parent mappings, particularly for institutions that changed names
or were acquired during 1999–2013 (e.g., Barclays Global Investors → BlackRock
in December 2009).

This extension is the natural next phase of the project, pending data access.

---

## Connecting to the Pre-XML Perl Pipeline

Michael Sinkinson's original parsing script is in `archive/sinkinson_perl/`.
It takes raw SEC EDGAR full-text filings and a list of target CUSIPs per quarter,
and outputs the same structure as `scrape_parsed.csv`.

To run it on new quarters (e.g., 2013Q1–2013Q2 if you want to bridge the gap):
1. Download the full-text 13(f) filings from SEC EDGAR for those quarters
2. Obtain a CUSIP list for the target securities (from CRSP or another source)
3. Run `perl find_holdings_snp.pl` per the script's documentation header
4. The output can be appended to `scrape_parsed.csv` to create a seamless series
