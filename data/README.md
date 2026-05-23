# Data

Processed outputs are in `data/processed/`. Reference data is in `data/reference/`.

Large raw files (108MB holdings CSV and 2.2GB pre-XML corpus) are excluded
from this repository. See `docs/data_guide.md` for the full inventory and
instructions on regenerating or obtaining each file.

## Present

- `processed/kappa_9firms_corrected.csv` — κ for all 72 ordered pairs × 50 quarters
- `processed/kappa_mean_by_quarter.csv` — mean κ̄ per quarter for Figure 1
- `processed/shares_outstanding_9firms_fixed.csv` — shares outstanding with fixes applied
- `processed/entity_consolidation_map.csv` — maps subsidiary CIKs to parent entities
- `processed/contaminated_quarters.csv` — flags and scale factors for NVDA/AAL
- `processed/completed_9firms.csv` — pull checkpoint (which firm-quarters are done)
- `reference/historical_firms.json` — S&P 500 historical composition

## What's not here

- `holdings_9firms.csv` (~108MB) — regenerate with `python3 src/pull_data.py`
- `scrape_parsed.csv` (2.2GB) — original paper authors' pre-XML dataset, too large
