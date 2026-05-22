# Methodology

## The Common Ownership Profit Weight κ

The core quantity is $\kappa_{fg}$, the weight that firm $f$ places on firm $g$'s
profits when making strategic decisions. Under the Rotemberg (1984) framework with
proportional control ($\gamma_{fs} = \beta_{fs}$, i.e. one share, one vote):

$$\kappa_{fg} = \frac{\sum_s \beta_{fs} \cdot \beta_{gs}}{\sum_s \beta_{fs}^2}$$

where $\beta_{fs}$ is the ownership fraction of institutional investor $s$ in firm $f$:

$$\beta_{fs} = \frac{\text{shares held by } s \text{ in } f}{\text{total shares of } f \text{ outstanding}}$$

The denominator $\sum_s \beta_{fs}^2$ is the investor Herfindahl-Hirschman index
($\text{IHHI}_f$) — how concentrated firm $f$'s ownership is. The numerator is the
dot product of two ownership vectors, capturing how much the same investors hold both
firms.

This decomposes geometrically (Equation 3' of the paper) as:

$$\kappa_{fg} = \cos(\beta_f, \beta_g) \cdot \sqrt{\frac{\text{IHHI}_g}{\text{IHHI}_f}}$$

Two forces drive $\kappa$:
- **Cosine similarity** rises as institutional investors adopt increasingly similar
  (indexed) portfolios — the dominant driver of the long-run trend
- **IHHI ratio**: if firm $f$ has high retail ownership, its $\text{IHHI}_f$ is low
  (retail investors are atomistic, contributing negligible $\beta^2$), which amplifies
  $\kappa_{fg}$ for all its rival pairs

## Data Quality Corrections

Three corrections are applied before computing $\beta$. Each is documented in
Section 3 of the analysis notebook.

### 1. EDGAR XBRL Units Error: Apple 2014Q1

Apple's 10-Q for Q1 2014 reported `CommonStockSharesOutstanding` as 861,745 (in
thousands) rather than 861,745,000. The denominator in $\beta_{fs}$ is therefore
1,000× too small, clipping most institutional ownership fractions to 1.0 and
collapsing $\kappa$ to near zero for that quarter.

**Fix:** multiply Apple's 2014Q1 shares outstanding by 1,000.

### 2. Stock Split Timing: NVIDIA 2021Q2

NVIDIA's 4:1 split occurred July 19, 2021. NVIDIA's fiscal Q2 ends July 25 — four
days post-split. Our EDGAR scraper selected the fiscal Q2 filing (post-split, 2,489M
shares) as the closest filing to calendar Q2 end (June 30). The 13(f) holdings for
that quarter were filed pre-split (~429M shares). The 4× mismatch suppresses all
NVDA $\beta$ values in 2021Q2 by a factor of 4.

**Fix:** use the pre-split shares outstanding from 2021Q1 (621M) for the 2021Q2 computation.

### 3. Convertible Security Contamination

Two firm-periods show aggregate reported institutional holdings exceeding 100% of
shares outstanding:
- **NVDA 2014Q4–2017Q1**: $1.5B convertible notes issued November 2013; convertible
  arbitrage funds report share equivalents in 13(f) filings. Peak: 3.59× shares
  outstanding in 2016Q1.
- **AAL 2020Q2–2025Q2**: CARES Act warrants issued to the government in exchange for
  COVID relief; institutions holding these warrants report share equivalents in 13(f).

**Fix:** scale all holdings proportionally so aggregate institutional ownership equals
shares outstanding: $\text{scale} = \text{shares outstanding} / \sum_s \text{shares held}$.

## Entity Consolidation

Large institutional investors file under multiple CIK numbers — one per legal
sub-entity. BlackRock used 7 distinct CIKs from 2013–2016. Without consolidation,
the formula treats these as 7 separate investors, each with a small $\beta^2$,
understating BlackRock's true IHHI contribution by approximately 300×.

We built a parent-entity map covering 66 subsidiary CIKs across 22 institutional
parents. The map is in `data/processed/entity_consolidation_map.csv`.

BlackRock self-consolidated its filings in 2017, so the correction is most critical
for 2013–2016.

## Mean Profit Weight

The economy-wide summary statistic reported in Figure 1 of the paper is:

$$\bar{\kappa}_t = \frac{1}{P(P-1)} \sum_f \sum_{g \neq f} \kappa_{fg,t}$$

For the paper (full S&P 500): $P \approx 500$, yielding ~249,500 ordered pairs.
For our 9-firm sample: $P = 9$, yielding 72 ordered pairs.
