# Common Ownership Replication

Replication and extension of **Backus, Conlon & Sinkinson (2019), "Common Ownership in America: 1980–2017"** using QUANTkiosk 13(F) institutional holdings data.

The original paper measured how much competing S&P 500 firms are owned by the same investors — and found the effect tripled between 1980 and 2017. This project extends that analysis to **2013Q3 through 2025Q4** using API-accessible institutional holdings data, across **48 S&P 500 firms spanning 12+ industries** (tech, airlines, banks, pharma, energy, retail, insurance, utilities, semiconductors, defense, telecom, and more — see `src/config.py` for the full list) — **2,256 ordered firm pairs × 50 quarters = 112,800 κ computations**.

The 48-firm universe was built in four pulls: a 9-firm pilot matched to the paper's own case-study industries, two 10-firm batches (energy/consumer/retail/telecom/banks), and a 20-firm block pulled alphabetically from the 311 S&P 500 firms that were index constituents in every annual snapshot 2013–2025. `docs/methodology.md` documents the full build history and nine distinct data-quality corrections found and fixed along the way.

---

## Content

```
common-ownership-replication/
│
├── src/                    
├── data/processed/         
├── data/reference/         
├── notebooks/              
├── notebooks/pdf/          
├── plots/                  
├── docs/                   
└── archive/                
```
---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your QUANTkiosk API key
export QK_API_KEY=your_key_here

# 3. Pull holdings data from the QK API
#    Safe to kill and restart — checkpoints every call
cd src
python3 pull_data.py

# 4. Compute κ with all data quality corrections
python3 compute_kappa.py

# 5. Decompose κ by institutional investor type (Vanguard/BlackRock/State
#    Street split out individually — the headline Key Findings below)
python3 decompose_kappa_big3.py

# 6. Generate all figures
python3 make_plots.py
```

If you already have the processed data files in `data/processed/`, you can skip
step 3 and go straight to computing κ. `data/processed/kappa_48firms_decomposed_big3_split.csv`
(the verified 112,800-row result the Key Findings below are drawn from) is
already included, so step 5 is only needed if you want to reproduce it yourself.

---

## The Firm Universe

**48 firms** in four builds:

| Build | Count | Firms |
|-------|-------|-------|
| Pilot | 9 | AAPL, MSFT (tech anchors) · AAL, DAL (airlines) · JPM, BAC (banks) · PFE, MRK (pharma) · NVDA (semiconductors) — chosen to match the paper's own Section 3.5 case-study industries |
| Batch 2 | 10 | XOM, CVX (energy) · KO, PEP (beverages) · WMT, TGT (retail) · T, VZ (telecom) · WFC (banks) · INTC (semiconductors) |
| Batch 3 | 9 | AMZN, JNJ, PG, MA, UNH, GS, MS, LMT, NOC — Visa (V) was pulled but dropped: no XBRL shares-outstanding data exists for its multi-class share structure |
| Universe | 20 | A, ABBV, ABT, ACN, ADBE, ADI, ADM, ADP, ADSK, AEE, AEP, AES, AFL, AIG, AIZ, AKAM, ALL, ALLE, AMAT, AME — first 20 alphabetically of the 311 firms that were S&P 500 constituents in every annual snapshot 2013–2025, pulled via a nightly quota-limited job |

Full ticker/CIK/SIC table: `src/config.py`. To add more firms, edit that list — see `docs/extending.md`.

---

## Key Findings

- **Mean $\bar{\kappa}$ rises from ~0.71 (2013Q3) to ~0.92 (2025Q4), full-sample average ≈0.81**, consistent with the paper's cross-sectional prediction for large-cap firms (our 2017 value, ≈0.80, sits above the S&P 500 average of 0.70 the paper documents for that year). The original 9-firm pilot's narrower estimate ($\bar{\kappa}\approx 0.74$–$0.77$) is superseded by this 48-firm result — see `docs/methodology.md`.
- **The Big Three, split individually, account for ~78% of κ in our sample**: Vanguard 35.7%, BlackRock 27.3%, State Street 14.9% (full-sample mean, 48 firms, 2013Q3–2025Q4). Active managers contribute 16.9%, non-Big-Three passive funds 3.1%, everything else under 2%.
- **This is not a contradiction of the paper's finding that broad portfolio convergence — not just Big Three growth — drove κ's *rise* from 1980–2017.** The two results answer different questions: the paper explains four decades of *growth* using pre-2013 data we don't have; our result describes the *level* of κ in a 2013–2025 sample drawn largely after the Big Three's rise (per the paper's own Figure 7) was already complete. At Vanguard's ~9% average ownership stake, its $\beta^2$ contribution to the denominator is mechanically 25–30% of total IHHI before any covariance term is considered — see `docs/methodology.md` for the full reconciliation.
- **A COVID-19 airline divergence** (2020–2021): the AAL–DAL pair's $\kappa$ specifically collapsed from ~0.88 to ~0.43–0.47 as institutional ownership diverged between the two carriers — a real, sharp, pair-level effect. At 48-firm scale this doesn't move the economy-wide mean (only 2 of 48 firms are airlines), which is why the note above is scoped to the pair, not $\bar{\kappa}$ overall — the original 9-firm pilot, where airlines were 2 of 9 firms, is where an aggregate-level dip was visible.
- **An NVDA convergence**: NVIDIA's own average $\kappa$ with the rest of the sample rose from ~0.40 (2013) to over 1.0 by 2022–2025, as its ownership vector converged toward the existing mega-cap cluster while it grew from a $8B mid-cap to a $3T+ index-fund staple. Real and firm-specific; not framed as moving the 48-firm aggregate mean, which is driven by all 2,256 pairs together.
- **Data quality corrections are essential, not a footnote.** Nine distinct issues were found and fixed across the build — EDGAR XBRL units errors (AAPL, KO), stock-split timing mismatches (NVDA, MA, WMT), convertible-security contamination, a BlackRock duplicate-filing bug, and a State Street ingestion gap fixed via per-ticker interpolation. Uncorrected data produces an implausible $\bar{\kappa} \approx 1.20$ for 2013–2015. Full list in `docs/methodology.md`.

---

## Data Notes

1. Raw per-institution holdings (`holdings_48firms.csv`, several hundred MB across 48 firms × 50 quarters) are excluded from this repository. Run `src/pull_data.py` to regenerate — requires a QUANTkiosk API key, ~9,600 calls at ~20 credits each (~1 day at the standard 10,000 credit/day quota).

2. All processed outputs actually used for the Key Findings above — the 112,800-row κ decomposition, shares outstanding (all 48 firms, all 50 quarters), the entity consolidation map, and contamination flags — are included in `data/processed/` and do not require re-pulling from the API. `docs/data_guide.md` documents every file.

3. The pre-XML scraped SEC corpus (`scrape_parsed.csv`, 2.2GB, 1999–2017) is the dataset released by the original paper's authors. It is not hosted here due to size. See `docs/data_guide.md` for details.

---

## References

Backus, M., Conlon, C., & Sinkinson, M. (2019). *Common Ownership in America: 1980–2017*. NBER Working Paper 25454.

Azar, J., Schmalz, M. C., & Tecu, I. (2018). Anticompetitive effects of common ownership. *Journal of Finance*, 73(4), 1513–1565.

Rotemberg, J. J. (1984). Financial transaction costs and industrial performance. *MIT Sloan Working Paper*.
