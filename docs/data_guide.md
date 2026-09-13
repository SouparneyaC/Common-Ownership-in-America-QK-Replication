# Data Guide

## Processed Data Files (included in repo)

All files live in `data/processed/`.

### kappa_48firms_decomposed_big3_split.csv
**The headline result.** Output of `src/decompose_kappa_big3.py` — 112,332
rows (48 firms, 2,256 ordered pairs, 50 quarters, minus pairs with
insufficient institutional coverage in a given quarter). The Key Findings in
the README and the Big Three split numbers in `docs/methodology.md` are drawn
directly from this file.

| Column | Description |
|--------|-------------|
| year, quarter, time | Reporting period (time = decimal year for plotting) |
| firm_f, firm_g | The ordered pair (f places weight on g's profits) |
| kappa | Common ownership profit weight κ_fg |
| contrib_Vanguard, contrib_BlackRock, contrib_State Street | Each Big Three member's individual contribution to κ_fg |
| contrib_Passive, contrib_Active, contrib_Hedge Fund, contrib_Other | Remaining investor-type contributions |

All seven `contrib_*` columns sum exactly to `kappa` for every row (additive
by construction — see `docs/methodology.md`).

### kappa_48firms_corrected.csv
Output of `src/compute_kappa.py` — the non-decomposed κ series with SIC/cosine/IHHI
columns (one row per ordered firm pair per quarter). Not shipped pre-built in
this repo (it requires a live re-pull via `pull_data.py`); regenerate with
`compute_kappa.py` once you have `holdings_48firms.csv`.

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

### kappa_48firms_mean_by_quarter.csv
Quarter-level mean of κ across all 2,256 ordered pairs, derived from the
decomposed dataset above. Used for Figure 1.

### shares_outstanding_48firms.csv
Quarterly shares outstanding for all 48 firms (2,400 rows = 48 firms × 50
quarters), with all data quality fixes applied. Pulled from SEC EDGAR XBRL
across three batches (pilot, batches 2–3, universe) and merged. Source field
indicates which XBRL field was used.

### entity_consolidation_map.csv
Maps subsidiary CIK numbers to canonical parent entity IDs. Firm-universe
agnostic — built from institutional filer structure, not from the specific
48 firms analyzed, so it doesn't need to grow as the firm universe does.

| Column | Description |
|--------|-------------|
| cik | Filing entity CIK (subsidiary) |
| parent_id | Canonical parent label (e.g. "BLACKROCK") |
| institution_name | Human-readable name |

### contaminated_quarters.csv
Firm-quarters where aggregate institutional holdings exceeded shares outstanding.
Contains the scale factor applied to correct the contamination.

### completed_48firms.csv
Checkpoint file created by `src/pull_data.py`. Records every firm-quarter that
has been successfully pulled from the QK API. The pull script reads this before
making any API call to avoid duplication.

### Superseded pilot-scale files (kept for reference)
`kappa_9firms_corrected.csv`, `shares_outstanding_9firms_fixed.csv`, and
`completed_9firms.csv` are the original 9-firm pilot's outputs, from before
the universe was expanded to 48 firms. They're kept for provenance but are no
longer what the pipeline scripts read by default.

---

## Reference Data (included in repo)

### data/reference/historical_firms.json
S&P 500 historical composition reconstructed from Wikipedia's changes log,
covering every addition and removal from 1976 onward.

---

## Large Files (excluded from repo)

### holdings_48firms.csv (~450 MB)
One row per institutional investor per firm per quarter, across all 48 firms.
This is the raw output of `src/pull_data.py`. Excluded from git due to size
(the original 9-firm pilot's version was ~108 MB; the file grew roughly
proportionally as the universe expanded to 48 firms).

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
