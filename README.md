# Common Ownership Replication

Replication and extension of **Backus, Conlon & Sinkinson (2019), "Common Ownership in America: 1980–2017"** using QUANTkiosk 13(F) institutional holdings data.

The original paper measured how much competing S&P 500 firms are owned by the same investors — and found the effect tripled between 1980 and 2017. This project extends that analysis to **2013Q3 through 2025Q4** using API-accessible institutional holdings data, covering 9 firms across 5 industries.

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

# 5. Generate all figures
python3 make_plots.py
```

If you already have the processed data files in `data/processed/`, you can skip
step 3 and go straight to computing κ.

---

## The Firm Universe

Nine S&P 500 firms chosen to match the paper's own case study industries:

| Ticker | Name | Industry | SIC | Role |
|--------|------|----------|-----|------|
| AAPL | Apple | Tech (hardware) | 3571 | Large-cap anchor |
| MSFT | Microsoft | Tech (software) | 7372 | Large-cap anchor |
| AAL | American Airlines | Airlines | 4512 | Within-industry pair |
| DAL | Delta Air Lines | Airlines | 4512 | Within-industry pair |
| JPM | JPMorgan Chase | Banks | 6021 | Within-industry pair |
| BAC | Bank of America | Banks | 6021 | Within-industry pair |
| PFE | Pfizer | Pharma | 2834 | Within-industry pair |
| MRK | Merck | Pharma | 2834 | Within-industry pair |
| NVDA | NVIDIA | Semiconductors | 3674 | Structural growth story |

Airlines, banks, and the pharma pair are the paper's own case study industries (Figure 12). NVIDIA was added to document the formation of common ownership in real time as a firm enters the index fund universe.

**To add new firms:** edit `src/config.py` — that is the only file you need to touch.

---

## Key Findings

- Mean $\bar{\kappa} \approx 0.74$–$0.77$ throughout 2013–2025, consistent with the paper's cross-sectional prediction for large-cap firms (above the S&P 500 average of 0.70 documented by the paper in 2017).
- A **COVID-19 divergence** (2020–2021): institutional flight from airline stocks temporarily drove $\bar{\kappa}$ down by 0.05–0.08 units.
- An **NVDA convergence** (2023–2025): as NVIDIA entered every major index fund, its ownership vector converged toward the existing mega-cap cluster and pulled $\bar{\kappa}$ upward.
- **Data quality corrections are essential**: uncorrected data produces $\bar{\kappa} \approx 1.20$ for 2013–2015, an implausible result caused primarily by an EDGAR XBRL units error in Apple's 2014Q1 filing.

---

## Data Notes

1. The large holdings file (`holdings_9firms.csv`, ~108MB) is excluded from this repository. Run `src/pull_data.py` to regenerate it — the script requires a QUANTkiosk API key and completes in a single session (~450 calls at ~20 credits each).

2. All processed outputs (κ values, shares outstanding, entity map, contamination flags) are included and do not require re-pulling from the API.

3. The pre-XML scraped SEC corpus (`scrape_parsed.csv`, 2.2GB, 1999–2017) is the dataset released by the original paper's authors. It is not hosted here due to size. See `docs/data_guide.md` for details.

---

## References

Backus, M., Conlon, C., & Sinkinson, M. (2019). *Common Ownership in America: 1980–2017*. NBER Working Paper 25454.

Azar, J., Schmalz, M. C., & Tecu, I. (2018). Anticompetitive effects of common ownership. *Journal of Finance*, 73(4), 1513–1565.

Rotemberg, J. J. (1984). Financial transaction costs and industrial performance. *MIT Sloan Working Paper*.
