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

## Build History

The 48-firm universe was assembled in four pulls, in order:

1. **Pilot (9 firms)** — AAPL, MSFT, AAL, DAL, JPM, BAC, PFE, MRK, NVDA. Chosen
   to match the paper's own Section 3.5 case-study industries (banks, airlines)
   plus two large-cap tech anchors and NVDA for its ownership-formation story.
2. **Batch 2 (10 firms)** — XOM, CVX, KO, PEP, WMT, TGT, T, VZ, WFC, INTC.
3. **Batch 3 (10 firms, 9 kept)** — AMZN, JNJ, PG, MA, UNH, GS, MS, LMT, NOC,
   and Visa (V). Visa was dropped: it never tagged `CommonStockSharesOutstanding`
   or any weighted-average-share XBRL concept after 2010 (multi-class share
   structure), so 0 of 50 quarters could be resolved.
4. **Universe (20 firms)** — the first 20 alphabetically of the 311 S&P 500
   firms that were index constituents in every one of the 13 annual snapshots
   2013–2025 ("persistent" firms), pulled via a nightly job rate-limited to
   10 firms/night against the QK quota (A, ABBV, ABT, ACN, ADBE, ADI, ADM,
   ADP, ADSK, AEE, AEP, AES, AFL, AIG, AIZ, AKAM, ALL, ALLE, AMAT, AME).

Total scope: **48 firms, 2,256 ordered pairs, 50 quarters = 112,800 κ
computations** (`data/processed/kappa_48firms_decomposed_big3_split.csv`,
112,332 rows after dropping pairs with insufficient institutional coverage
in a given quarter).

## Data Quality Corrections

Nine distinct issues were found and fixed across the build.

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

### 4. Stock Split Restatement: Mastercard 2013Q4 (÷10)

Mastercard's 10:1 split (January 21, 2014) meant its FY2013 10-K, filed after the
split, restated shares outstanding on a post-split basis (1,211M) — but the 13(f)
holdings for Q4 2013 (December 31, 2013) are pre-split (~121M total). Every
$\beta_{MA,s}$ was 10× too small, inflating $\kappa_{MA\to g}$ roughly 10×
(detected via an adjacent-quarter ratio of 10.008).

**Fix:** divide MA's 2013Q4 shares outstanding by 10.

### 5. Stock Split Restatement: Walmart 2023Q4 (÷3)

Same mechanism as #4: Walmart's 3:1 split (February 26, 2024) caused its FY2023
10-K to restate shares post-split (8,077M) against pre-split Q4 2023 holdings
(~913M) — detected via an adjacent-quarter ratio of 3.001.

**Fix:** divide WMT's 2023Q4 shares outstanding by 3.

### 6. EDGAR XBRL Units Error: Coca-Cola, four quarters (×1,000,000)

Coca-Cola's 10-Q filings for 2018Q1, 2018Q2, 2018Q3, and 2019Q1 tagged
`CommonStockSharesOutstanding` as ~4,265 instead of ~4,265,000,000 — the same
class of error as Apple's, but 1,000× more severe. Every institutional
investor's $\beta$ clipped to 1.0, spiking mean $\kappa$ for pairs involving
KO above 2.0 in those quarters.

**Fix:** multiply KO's shares outstanding by 1,000,000 for those four quarters.

### 7. Entity Consolidation

Large institutional investors file under multiple CIK numbers — one per legal
sub-entity. BlackRock used 8 distinct CIKs from 2013–2016. Without
consolidation, the formula treats these as 8 separate investors, each with a
small $\beta^2$, understating BlackRock's true IHHI contribution by two
orders of magnitude.

**Fix:** a parent-entity map covering 66 subsidiary CIKs across 22
institutional parents (`data/processed/entity_consolidation_map.csv`).
BlackRock self-consolidated its own filings in 2017, so this correction is
most critical for 2013–2016. State Street (CIK 93751) is not in this map —
it's caught separately by name in the classification function (see below).

### 8. BlackRock Duplicate Filing: CIK 2012383, 2025Q4

QK's ingestion captured both BlackRock's original 13(f) for Q4 2025 and its
amendment, and summed them. Every one of 27 tickers showed a Q4/Q3 ratio of
almost exactly 2.0 (mean 2.03, std 0.04) — a single manager cannot double its
position in every stock in one quarter.

**Fix:** halve all `shares_held` for CIK 2012383 in 2025Q4.

### 9. State Street Ingestion Gap: 2015Q2–Q3

State Street's (CIK 93751) reported total equity holdings across our 48 firms
dropped ~28% in 2015Q2 and 2015Q3 relative to the surrounding quarters, and 14
tickers show zero rows entirely for those two quarters — implausible for a
~$3T passive index manager running SPY with no corresponding market event.
Likely cause: a corrective 13(f)/A amendment that the data vendor's snapshot
pipeline failed to capture at pull time (the same general failure mode
Backus, Conlon & Sinkinson's own Appendix B and footnote 11 document for the
Thomson Reuters S34 database around 2010).

**Fix:** drop the understated/missing 2015Q2–Q3 rows for CIK 93751 and rebuild
them per-ticker via linear interpolation between the Q1 and Q4 2015 anchors —
appropriate since State Street's holdings, as a passive manager, drift
smoothly with index composition rather than moving in discrete jumps.

## Big Three Split — Vanguard vs. BlackRock vs. State Street

`src/decompose_kappa_big3.py` decomposes $\kappa_{fg}$ into seven additive
investor-group contributions, splitting the "Big Three" bucket into its three
individual constituents rather than combining them (`decompose_kappa.py` is
the earlier, 5-group version with Big Three combined).

**Full-sample mean, 2013Q3–2025Q4, 48 firms:**

| Group | Mean κ share |
|---|---|
| Vanguard | 35.7% |
| BlackRock | 27.3% |
| State Street | 14.9% |
| Active managers | 16.9% |
| Passive (non-Big-Three) | 3.1% |
| Other | 1.9% |
| Hedge Funds | 0.1% |

(Reproduced by running `src/decompose_kappa_big3.py` end-to-end against the
committed 48-firm data — see the script for the exact methodology.)

The within-Big-Three split is roughly 3:2:1 (Vanguard : BlackRock : State
Street). This is driven almost entirely by relative ownership stakes, not any
behavioral difference: contribution to $\kappa$ scales quadratically in
ownership share ($\text{contrib}_s \approx \beta_s^2 / IHHI_f$ when both firms
sit in the same index), and Vanguard's average stake in our sample grew from
~5% (2013, roughly tied with BlackRock) to ~10% (2025), while BlackRock grew
to ~8.5% — because Vanguard is 100% equity-index/ETF-focused and recycles all
revenue into fee cuts and AUM growth, while BlackRock's growth is spread
across fixed income, alternatives, and active strategies where only the
iShares passive arm feeds $\kappa$.

### Reconciling with the paper

The paper states the 1980–2017 rise in $\kappa$ was driven by *broad
portfolio convergence*, not specifically by BlackRock and Vanguard growing.
Our finding — the Big Three account for ~78% of $\kappa$'s *level* in
2013–2025 — is not a contradiction. These are answers to two different
questions:

| Question | Paper's answer | Our answer |
|---|---|---|
| What drove κ's *growth* from 0.2 to 0.7, 1980–2017? | Broad portfolio convergence across all 13(f) filers | — (no pre-2013 data in this replication) |
| Who accounts for the *level* of κ in 2013–2025? | — | Big Three, ~78% |

The paper's own Figure 7 shows the Big Three's average ownership rose from
6% to 21% between 2000 and 2017 — i.e. their rise was largely complete before
our sample begins. We are measuring a post-rise snapshot: at Vanguard's ~9%
average stake, its $\beta^2$ contribution to $IHHI_f$ alone is already
25–30% of the total, mechanically dominant in the denominator before any
covariance term is considered. The paper's underlying mechanism (broad
diversification, not just the Big Three specifically) still holds within our
sample too — it's visible in the continued growth of κ from 0.7 (2017) toward
~1.0 (2025) despite the Big Three's own share plateauing, driven by
continued convergence among active managers and non-Big-Three passive
vehicles (Geode, Dimensional, Norges).

## Mean Profit Weight

The economy-wide summary statistic reported in Figure 1 of the paper is:

$$\bar{\kappa}_t = \frac{1}{P(P-1)} \sum_f \sum_{g \neq f} \kappa_{fg,t}$$

For the paper (full S&P 500): $P \approx 500$, yielding ~249,500 ordered pairs.
For our 48-firm sample: $P = 48$, yielding 2,256 ordered pairs.
