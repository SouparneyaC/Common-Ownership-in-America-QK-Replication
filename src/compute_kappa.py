import numpy as np
import pandas as pd
from itertools import permutations
from config import TICKERS, SIC, data_dir


def load_data():
    h = pd.read_csv(data_dir / 'holdings_9firms.csv', dtype={'filer_cik': str})
    h['filer_cik'] = h['filer_cik'].str.replace(r'\.0$', '', regex=True).str.strip()
    shares = pd.read_csv(data_dir / 'shares_outstanding_9firms_fixed.csv')
    cmap   = pd.read_csv(data_dir / 'entity_consolidation_map.csv', dtype={'cik': str})
    contam = pd.read_csv(data_dir / 'contaminated_quarters.csv')
    return h, shares, cmap, contam


def build_beta(holdings_q, shares_q, cik_to_parent, contam_scale, year, quarter):
    # Apply entity consolidation then compute β_fs = shares / shares_outstanding
    # Scale contaminated firm-quarters so aggregate institutional share <= 1
    hq = holdings_q.copy()
    hq['parent'] = hq['filer_cik'].map(cik_to_parent).fillna(hq['filer_cik'])
    hq = hq.groupby(['ticker', 'parent'])['shares_held'].sum().reset_index()

    beta = {}
    for ticker in TICKERS:
        firm = hq[hq.ticker == ticker].set_index('parent')['shares_held']
        tot  = shares_q.loc[shares_q.ticker == ticker, 'shares'].values

        if len(tot) == 0 or tot[0] == 0 or firm.empty:
            beta[ticker] = pd.Series(dtype=float)
            continue

        b     = firm / tot[0]
        scale = contam_scale.get((ticker, year, quarter), 1.0)
        beta[ticker] = (b * scale).clip(upper=1.0)

    return beta


def calc_kappa(beta_f, beta_g):
    # κ_fg = <β_f, β_g> / <β_f, β_f>  (Rotemberg 1984, proportional control)
    u   = beta_f.index.union(beta_g.index)
    b_f = beta_f.reindex(u, fill_value=0.0).values
    b_g = beta_g.reindex(u, fill_value=0.0).values
    denom = np.dot(b_f, b_f)
    return np.dot(b_f, b_g) / denom if denom > 0 else np.nan


def main():
    h, shares, cmap, contam = load_data()

    cik_to_parent = dict(zip(cmap['cik'], cmap['parent_id']))
    contam_scale  = {(r.ticker, r.year, r.quarter): r.scale_factor
                     for _, r in contam.iterrows()}

    quarters = sorted(h[['year', 'quarter']].drop_duplicates().values.tolist())
    pairs    = list(permutations(TICKERS, 2))
    records  = []

    for year, quarter in quarters:
        h_q = h[(h.year == year) & (h.quarter == quarter)]
        s_q = shares[(shares.year == year) & (shares.quarter == quarter)]
        beta = build_beta(h_q, s_q, cik_to_parent, contam_scale, year, quarter)

        for f, g in pairs:
            if beta[f].empty or beta[g].empty:
                continue
            k = calc_kappa(beta[f], beta[g])
            if np.isnan(k):
                continue

            u   = beta[f].index.union(beta[g].index)
            b_f = beta[f].reindex(u, fill_value=0.0).values
            b_g = beta[g].reindex(u, fill_value=0.0).values

            cos = np.dot(b_f, b_g) / (np.linalg.norm(b_f) * np.linalg.norm(b_g) + 1e-12)
            records.append({
                'year': year, 'quarter': quarter,
                'time': year + (quarter - 0.5) / 4,
                'firm_f': f, 'firm_g': g,
                'sic_f': SIC[f], 'sic_g': SIC[g],
                'same_sic': SIC[f] == SIC[g],
                'kappa': round(k, 6),
                'cosine': round(cos, 6),
                'ihhi_f': round(np.dot(b_f, b_f), 8),
                'ihhi_g': round(np.dot(b_g, b_g), 8),
                'retail_f': round(max(0.0, 1.0 - b_f.sum()), 4),
            })

    df_kappa = pd.DataFrame(records)
    df_kappa.to_csv(data_dir / 'kappa_9firms_corrected.csv', index=False)

    mean_q = (df_kappa.groupby(['year', 'quarter', 'time'])['kappa']
                      .mean().reset_index()
                      .rename(columns={'kappa': 'kappa_all'}))
    mean_q.to_csv(data_dir / 'kappa_mean_by_quarter.csv', index=False)

    print(f'{len(df_kappa):,} pair-quarter observations')
    print(f'{len(mean_q)} quarterly means')


if __name__ == '__main__':
    main()
