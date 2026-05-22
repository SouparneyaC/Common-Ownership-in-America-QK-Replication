# Data Guide

## Processed Data Files (included in repo)

All files live in `data/processed/`.

### kappa_9firms_corrected.csv
The main output of `src/compute_kappa.py`. One row per ordered firm pair per quarter.

| Column | Description |
|--------|-------------|
| year, quarter | Reporting period |
| time | year + (quarter - 0.5) / 4 — decimal year for plotting |
| firm_f, firm_g | The ordered pair (f places weight on g's profits) |
| sic_f, sic_g | 4-digit SIC codes |
| same_sic | True if both firms are in the same 4-digit SIC industry |
| kappa | Common ownership profit weight κ_fg |
| cosine | Cosine similarity of ownership vectors |
| ihhi_f, ihhi_g | Investor HHI for each firm |
| retail_f | Fraction of firm f not held by 13(f) filers (retail share) |

### kappa_mean_by_quarter.csv
Quarter-level mean of κ across all 72 ordered pairs. Used for Figure 1.

### shares_outstanding_9firms_fixed.csv
Quarterly shares outstanding for each firm, with data quality fixes applied.
Pulled from SEC EDGAR XBRL. Source field indicates which XBRL field was used.

### entity_consolidation_map.csv
Maps subsidiary CIK numbers to canonical parent entity IDs.

| Column | Description |
|--------|-------------|
| cik | Filing entity CIK (subsidiary) |
| parent_id | Canonical parent label (e.g. "BLACKROCK") |
| institution_name | Human-readable name |

### contaminated_quarters.csv
Firm-quarters where aggregate institutional holdings exceeded shares outstanding.
Contains the scale factor applied to correct the contamination.

### completed_9firms.csv
Checkpoint file created by `src/pull_data.py`. Records every firm-quarter that
has been successfully pulled from the QK API. The pull script reads this before
making any API call to avoid duplication.

---

## Reference Data (included in repo)

### data/reference/historical_firms.json
S&P 500 historical composition reconstructed from Wikipedia's changes log,
covering every addition and removal from 1976 onward.

---

## Large Files (excluded from repo)

### holdings_9firms.csv (~108 MB)
One row per institutional investor per firm per quarter. This is the raw output
of `src/pull_data.py`. Excluded from git due to size.

To regenerate: `QK_API_KEY=your_key python3 src/pull_data.py`

### scrape_parsed.csv (2.2 GB)
The parsed 13(f) holdings dataset released by the original paper's authors
(Backus, Conlon & Sinkinson 2019). Contains 48.7 million rows from 1999Q1 through
2017Q3, covering 17,811 CUSIPs and 8,170 filing institutions.

This is the pre-XML era dataset — the output of Sinkinson's Perl parsing pipeline
(see `archive/sinkinson_perl/`). It is the data source for any analysis that
extends the replication backward before 2013Q3.

Column structure:
- `cik` — filer CIK (the institution)
- `cusip` — 9-character CUSIP of the security held
- `shares` — shares held
- `rdate` — reporting date (YYYYMMDD)
- `fdate` — filing date (YYYYMMDD)
- `filetype` — 13F-HR (original), 13F-HR/A (amendment), 13F-NT (no holdings)

**Note on CUSIP:** CUSIP identifiers are proprietary (S&P Global). This file
can be read and analyzed locally, but the CUSIP-to-company crosswalk needed to
link CUSIPs to SEC CIKs requires either CRSP/Compustat access or the OpenFIGI API.
See `docs/extending.md` for the pre-XML extension roadmap.

---

## Data Sources Summary

| Data | Source | Cost | Coverage |
|------|--------|------|----------|
| 13(F) institutional holdings | QUANTkiosk API | ~20 credits/firm/quarter | 2013Q3–present |
| Shares outstanding | SEC EDGAR XBRL | Free | 2009–present |
| S&P 500 composition | Wikipedia | Free | 1976–present |
| Pre-XML 13(F) corpus | Paper authors' release | Free | 1999–2017Q3 |
| CUSIP crosswalk | CRSP (via WRDS) or OpenFIGI | Paid / Free (partial) | Historical |
