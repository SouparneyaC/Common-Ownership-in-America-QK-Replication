import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy.ndimage import uniform_filter1d
from config import data_dir, plots_dir, SIC, INDUSTRY

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 11,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.grid': True,
    'grid.alpha': 0.25,
})


def fig1_kappa_over_time():
    # Mean profit weight across all 72 ordered pairs — replicates paper Figure 1
    df = pd.read_csv(data_dir / 'kappa_mean_by_quarter.csv')

    fig, ax = plt.subplots(figsize=(12, 5.5))
    smoothed = uniform_filter1d(df['kappa_all'].values, size=5)

    ax.plot(df['time'], df['kappa_all'],
            color='#1f77b4', linewidth=1.6, label=r'$\bar{\kappa}_t$ quarterly mean')
    ax.plot(df['time'], smoothed,
            color='#d62728', linewidth=1.4, linestyle='--',
            label='5-quarter moving average')

    ax.axhline(1.0, color='grey', linewidth=0.9, linestyle='--', alpha=0.5)
    ax.text(2013.5, 1.008, r'$\kappa=1$ (merger-equivalent)', color='grey', fontsize=9)
    ax.axhline(0.70, color='#2ca02c', linewidth=0.9, linestyle=':', alpha=0.6)
    ax.text(2025.6, 0.694, 'S&P 500 avg\n2017 (paper)', color='#2ca02c',
            fontsize=8, ha='right')

    ax.axvspan(2020.0, 2021.25, alpha=0.06, color='steelblue')
    ax.text(2020.1, 1.055, 'COVID-19', color='steelblue', fontsize=8.5, style='italic')
    ax.axvline(2023.125, color='#9467bd', linewidth=0.9, linestyle=':', alpha=0.6)
    ax.text(2023.2, 1.055, 'NVDA AI boom', color='#9467bd', fontsize=8, va='top')

    ax.set_xlim(2013.3, 2026.2)
    ax.set_ylim(0.40, 1.10)
    ax.set_xlabel('Year')
    ax.set_ylabel(r'Mean profit weight $\bar{\kappa}$')
    ax.set_title(
        'Common Ownership Profit Weights: 9 S&P 500 Firms, 2013Q3–2025Q4\n'
        'Replication of Backus, Conlon & Sinkinson (2019) Figure 1', fontsize=11.5)
    ax.legend(loc='lower right', fontsize=9.5)
    ax.set_xticks(range(2014, 2027, 2))

    note = ('Notes: AAPL, MSFT (Tech) | AAL, DAL (Airlines) | JPM, BAC (Banks) | '
            'PFE, MRK (Pharma) | NVDA (Semiconductors). '
            'Three data quality corrections applied. Data: QUANTkiosk 13(F); SEC EDGAR XBRL.')
    fig.text(0.5, 0.01, note, ha='center', fontsize=8, color='#444',
             bbox=dict(boxstyle='round,pad=0.4', facecolor='#f9f9f9',
                       edgecolor='#ccc', alpha=0.85))
    fig.subplots_adjust(bottom=0.18)
    fig.savefig(plots_dir / 'fig1_kappa_over_time.png', bbox_inches='tight', dpi=150)
    plt.close(fig)


def fig2_within_vs_cross_industry():
    # Within-industry vs cross-industry kappa — replicates paper Figure 11
    df = pd.read_csv(data_dir / 'kappa_9firms_corrected.csv')

    within = df[df.same_sic].groupby('time')['kappa'].mean()
    cross  = df[~df.same_sic].groupby('time')['kappa'].mean()

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(within.index, within.values, color='#d62728', linewidth=1.8,
            label='Within-industry (AAL–DAL, JPM–BAC, PFE–MRK)')
    ax.plot(cross.index, cross.values, color='#1f77b4', linewidth=1.8,
            label='Cross-industry')
    ax.set_xlabel('Year')
    ax.set_ylabel(r'Mean $\kappa$')
    ax.set_title('Within- vs Cross-Industry Common Ownership\n'
                 'Replication of Backus et al. (2019) Figure 11')
    ax.legend(fontsize=9.5)
    ax.set_xticks(range(2014, 2027, 2))
    fig.savefig(plots_dir / 'fig2_within_vs_cross_industry.png',
                bbox_inches='tight', dpi=150)
    plt.close(fig)


def fig3_blackrock_consolidation():
    # Two-panel: BlackRock CIK count per year + effect on AAPL beta
    cmap     = pd.read_csv(data_dir / 'entity_consolidation_map.csv', dtype={'cik': str})
    holdings = pd.read_csv(data_dir / 'holdings_9firms.csv', dtype={'filer_cik': str})
    shares   = pd.read_csv(data_dir / 'shares_outstanding_9firms_fixed.csv')

    holdings['filer_cik'] = holdings['filer_cik'].str.replace(r'\.0$', '', regex=True).str.strip()
    br_ciks  = cmap[cmap.parent_id == 'BLACKROCK']['cik'].tolist()
    br_data  = holdings[holdings.filer_cik.isin(br_ciks)].copy()
    br_count = br_data.groupby('year')['filer_cik'].nunique().reset_index()

    shares_aapl = shares[shares.ticker == 'AAPL'].set_index(['year', 'quarter'])['shares']
    br_aapl     = br_data[br_data.ticker == 'AAPL'].copy()

    br_total = br_aapl.groupby(['year', 'quarter'])['shares_held'].sum().reset_index()
    br_total['time'] = br_total['year'] + (br_total['quarter'] - 0.5) / 4
    br_total['beta'] = br_total.apply(
        lambda r: r.shares_held / shares_aapl.get((r.year, r.quarter), np.nan), axis=1)

    br_main = (br_aapl[br_aapl.filer_cik == '913414']
               .groupby(['year', 'quarter'])['shares_held'].sum().reset_index())
    br_main['time'] = br_main['year'] + (br_main['quarter'] - 0.5) / 4
    br_main['beta'] = br_main.apply(
        lambda r: r.shares_held / shares_aapl.get((r.year, r.quarter), np.nan), axis=1)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))

    colors = ['#d62728' if y <= 2016 else '#2ca02c' for y in br_count['year']]
    ax1.bar(br_count['year'], br_count['filer_cik'], color=colors, edgecolor='white')
    ax1.axvline(2016.5, color='black', linestyle='--', linewidth=1.2)
    ax1.set_title('BlackRock: Distinct Filing Entities by Year')
    ax1.set_ylabel('Number of CIKs')
    ax1.set_ylim(0, 9)

    ax2.plot(br_total['time'], br_total['beta'] * 100, color='#2ca02c',
             linewidth=2.2, label='All entities consolidated')
    ax2.plot(br_main['time'][br_main.year <= 2016],
             br_main['beta'][br_main.year <= 2016] * 100,
             color='#d62728', linewidth=2, linestyle='--',
             label='Largest entity only')
    ax2.axvline(2016.75, color='black', linestyle=':', linewidth=1)
    ax2.set_title('Apple: BlackRock Ownership Fraction')
    ax2.set_ylabel(r'BlackRock $\beta$ (% of AAPL shares)')
    ax2.set_xlabel('Year')
    ax2.legend(fontsize=8.5)
    ax2.set_xlim(2013.4, 2020)

    fig.suptitle('Entity Consolidation: BlackRock Multi-CIK Filing Problem', fontsize=12)
    fig.tight_layout()
    fig.savefig(plots_dir / 'fig3_blackrock_consolidation.png',
                bbox_inches='tight', dpi=150)
    plt.close(fig)


def fig4_contamination():
    # Institutional holdings exceeding 100% of shares outstanding (NVDA, AAL)
    holdings = pd.read_csv(data_dir / 'holdings_9firms.csv', dtype={'filer_cik': str})
    shares   = pd.read_csv(data_dir / 'shares_outstanding_9firms_fixed.csv')

    inst = (holdings.groupby(['ticker', 'year', 'quarter'])['shares_held']
                    .sum().reset_index()
                    .rename(columns={'shares_held': 'inst_total'}))
    merged = shares.merge(inst, on=['ticker', 'year', 'quarter'], how='left')
    merged['inst_pct'] = merged['inst_total'] / merged['shares']
    merged['time']     = merged['year'] + (merged['quarter'] - 0.5) / 4

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))

    for ax, ticker, color, title in [
        (ax1, 'NVDA', '#9467bd',
         'NVDA: $1.5B Convertible Notes (Nov 2013)\n10 quarters contaminated 2014Q4–2017Q1'),
        (ax2, 'AAL', '#d62728',
         'AAL: CARES Act Warrants (2020)\n21 quarters contaminated 2020Q2–2025Q2'),
    ]:
        firm = merged[merged.ticker == ticker].sort_values('time')
        ax.fill_between(firm['time'], firm['inst_pct'] * 100,
                        where=firm['inst_pct'] > 1.0,
                        color=color, alpha=0.22, label='Above 100%')
        ax.fill_between(firm['time'], firm['inst_pct'] * 100,
                        where=firm['inst_pct'] <= 1.0,
                        color=color, alpha=0.1)
        ax.plot(firm['time'], firm['inst_pct'] * 100, color=color, linewidth=1.8)
        ax.axhline(100, color='red', linestyle='--', linewidth=1.2, label='100% of shares')
        ax.axhline(120, color='orange', linestyle=':', linewidth=1,
                   label='Paper threshold (120%)')
        ax.set_title(title, fontsize=10)
        ax.set_xlabel('Year')
        ax.set_ylabel('Institutional holdings (% of shares outstanding)')
        ax.legend(fontsize=8)
        ax.yaxis.set_major_formatter(mticker.PercentFormatter())

    fig.suptitle('Institutional Holdings as % of Shares Outstanding', fontsize=12)
    fig.tight_layout()
    fig.savefig(plots_dir / 'fig4_contamination.png', bbox_inches='tight', dpi=150)
    plt.close(fig)


def main():
    plots_dir.mkdir(exist_ok=True)
    fig1_kappa_over_time()
    fig2_within_vs_cross_industry()
    fig3_blackrock_consolidation()
    fig4_contamination()
    print(f'Figures saved to {plots_dir}')


if __name__ == '__main__':
    main()
