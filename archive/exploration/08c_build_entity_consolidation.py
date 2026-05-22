"""
SCRIPT 08c: Build Comprehensive Entity Consolidation Map
=========================================================
Systematically identifies every institutional investor in our
holdings_9firms.csv that files under multiple CIKs, and maps
all sub-entity CIKs to a single canonical parent_id.

METHOD:
  1. Extract all unique (CIK, name) pairs from holdings data
  2. Group by name keywords to find multi-CIK parents
  3. Manually verify each group to remove false positives
  4. Save definitive mapping → data/entity_consolidation_map.csv

The κ computation script then uses this to aggregate holdings by
parent_id before computing β, exactly as the paper does for BlackRock.

OUTPUT: data/entity_consolidation_map.csv
"""

import os, pandas as pd

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUTPUT_CSV = os.path.join(DATA_DIR, "entity_consolidation_map.csv")

# ─────────────────────────────────────────────────────────────────────────────
# COMPLETE CONSOLIDATION MAP
# Format: (cik, parent_id, parent_name, notes)
# Only genuine same-parent entities — false positives excluded
# ─────────────────────────────────────────────────────────────────────────────

CONSOLIDATION = [

    # ── BLACKROCK (8 CIKs) ────────────────────────────────────────────────────
    # Critical for 2013-2016. Paper explicitly merged these.
    ("913414",  "BLACKROCK",       "BlackRock Inc.",              "BlackRock Institutional Trust Company N.A."),
    ("1006249", "BLACKROCK",       "BlackRock Inc.",              "BlackRock Fund Advisors"),
    ("1003283", "BLACKROCK",       "BlackRock Inc.",              "BlackRock Group LTD"),
    ("1086364", "BLACKROCK",       "BlackRock Inc.",              "BlackRock Advisors LLC"),
    ("1305227", "BLACKROCK",       "BlackRock Inc.",              "BlackRock Investment Management LLC"),
    ("1085635", "BLACKROCK",       "BlackRock Inc.",              "BlackRock Japan Co. Ltd"),
    ("1364742", "BLACKROCK",       "BlackRock Inc.",              "BlackRock Inc. (main, 2017+)"),
    ("2012383", "BLACKROCK",       "BlackRock Inc.",              "BlackRock Inc. (2024+ CIK)"),

    # ── CAPITAL GROUP (6 CIKs) ────────────────────────────────────────────────
    # Three investment divisions + legacy international entities. All Capital Group.
    ("1422848", "CAPITAL_GROUP",   "Capital Group",               "Capital Research Global Investors"),
    ("1422849", "CAPITAL_GROUP",   "Capital Group",               "Capital World Investors"),
    ("1562230", "CAPITAL_GROUP",   "Capital Group",               "Capital International Investors"),
    ("895213",  "CAPITAL_GROUP",   "Capital Group",               "Capital International Inc. (legacy)"),
    ("1065349", "CAPITAL_GROUP",   "Capital Group",               "Capital International SARL (Europe)"),
    ("1065350", "CAPITAL_GROUP",   "Capital Group",               "Capital International Ltd (UK)"),

    # ── VANGUARD (3 CIKs) ─────────────────────────────────────────────────────
    # Two tiny new sub-entities from 2017+. Main entity is 102909.
    ("102909",  "VANGUARD",        "Vanguard Group Inc.",         "Vanguard Group Inc. (main)"),
    ("1767306", "VANGUARD",        "Vanguard Group Inc.",         "Vanguard Personalized Indexing Management"),
    ("1730578", "VANGUARD",        "Vanguard Group Inc.",         "Vanguard Capital Wealth Advisors"),

    # ── T. ROWE PRICE (2 CIKs) ────────────────────────────────────────────────
    # New investment management entity spun off ~2022.
    ("80255",   "T_ROWE_PRICE",    "T. Rowe Price Associates",    "Price T Rowe Associates Inc /MD/ (main)"),
    ("1897612", "T_ROWE_PRICE",    "T. Rowe Price Associates",    "T. Rowe Price Investment Management Inc."),

    # ── NORTHERN TRUST (2 CIKs) ───────────────────────────────────────────────
    # Connecticut subsidiary is tiny ($14M vs $25B).
    ("73124",   "NORTHERN_TRUST",  "Northern Trust Corp",         "Northern Trust Corp (main)"),
    ("1065441", "NORTHERN_TRUST",  "Northern Trust Corp",         "Northern Trust Co of Connecticut"),

    # ── INVESCO (2 CIKs) ──────────────────────────────────────────────────────
    ("914208",  "INVESCO",         "Invesco Ltd.",                "Invesco Ltd. (NYSE-listed, main)"),
    ("1990080", "INVESCO",         "Invesco Ltd.",                "INVESCO LLC (small entity)"),

    # ── UBS (4 CIKs) ──────────────────────────────────────────────────────────
    # Multiple legal entities under UBS Group AG umbrella.
    ("1610520", "UBS",             "UBS Group AG",                "UBS Group AG (Zurich parent)"),
    ("861177",  "UBS",             "UBS Group AG",                "UBS Asset Management Americas"),
    ("1114446", "UBS",             "UBS Group AG",                "UBS AG (Swiss bank)"),
    ("1132716", "UBS",             "UBS Group AG",                "UBS OConnor LLC (hedge fund arm)"),

    # ── NUVEEN (3 CIKs) ───────────────────────────────────────────────────────
    # Investment management arm of TIAA. Multiple filing entities.
    ("1521019", "NUVEEN",          "Nuveen (TIAA)",               "Nuveen Asset Management LLC (main, 6.6B)"),
    ("1871926", "NUVEEN",          "Nuveen (TIAA)",               "Nuveen LLC (1.3B)"),
    ("1311016", "NUVEEN",          "Nuveen (TIAA)",               "Nuveen Fund Advisors LLC (tiny)"),

    # ── TIAA (2 CIKs) ─────────────────────────────────────────────────────────
    # Teachers Insurance and Annuity. Separate from Nuveen in filing terms.
    ("887793",  "TIAA",            "TIAA",                        "TIAA CREF Investment Management LLC (main)"),
    ("1091559", "TIAA",            "TIAA",                        "TIAA CREF Trust Co FSB/MO"),

    # ── CHARLES SCHWAB (3 CIKs) ───────────────────────────────────────────────
    # Investment management arm + advisory + trust.
    ("884546",  "CHARLES_SCHWAB",  "Charles Schwab",              "Charles Schwab Investment Management (main, 9B)"),
    ("1501902", "CHARLES_SCHWAB",  "Charles Schwab",              "Charles Schwab Investment Advisory Inc."),
    ("1789219", "CHARLES_SCHWAB",  "Charles Schwab",              "Charles Schwab Trust Co"),

    # ── RAYMOND JAMES (5 CIKs) ────────────────────────────────────────────────
    # Broker-dealer and its subsidiaries all file separately.
    ("1084208", "RAYMOND_JAMES",   "Raymond James Financial",     "Raymond James & Associates (main, 2.1B)"),
    ("1462284", "RAYMOND_JAMES",   "Raymond James Financial",     "Raymond James Financial Services Advisors"),
    ("720005",  "RAYMOND_JAMES",   "Raymond James Financial",     "Raymond James Financial Inc"),
    ("1088950", "RAYMOND_JAMES",   "Raymond James Financial",     "Raymond James Trust N.A."),
    ("1927067", "RAYMOND_JAMES",   "Raymond James Financial",     "Raymond James Trust Co. of NH"),

    # ── BNP PARIBAS (3 CIKs) ──────────────────────────────────────────────────
    # Note: 1166588 and 1520354 each filed under multiple names over time
    # but are single CIKs — we still merge them to one parent.
    ("1166588", "BNP_PARIBAS",     "BNP Paribas",                 "BNP Paribas Arbitrage / Financial Markets"),
    ("1520354", "BNP_PARIBAS",     "BNP Paribas",                 "BNP Paribas Asset Management / Inv Partners"),
    ("872786",  "BNP_PARIBAS",     "BNP Paribas",                 "BNP Paribas (bank entity, tiny)"),

    # ── SUSQUEHANNA (3 CIKs) ──────────────────────────────────────────────────
    # US LLP entity + international UK/Irish entities. Same HFT firm.
    ("1446194", "SUSQUEHANNA",     "Susquehanna International",   "Susquehanna International Group LLP (main, 3.7B)"),
    ("1765924", "SUSQUEHANNA",     "Susquehanna International",   "Susquehanna International Group Ltd."),
    ("1765923", "SUSQUEHANNA",     "Susquehanna International",   "Susquehanna International Securities Ltd."),

    # ── APG (2 CIKs) ──────────────────────────────────────────────────────────
    # Dutch pension asset manager. NV = Dutch entity, US Inc = US subsidiary.
    ("1434819", "APG",             "APG Asset Management",        "APG Asset Management N.V. (main, 3.2B)"),
    ("1323255", "APG",             "APG Asset Management",        "APG Asset Management US Inc."),

    # ── SUMITOMO MITSUI TRUST (2 CIKs) ───────────────────────────────────────
    # Trust banking group. DS Asset Management is a subsidiary.
    ("1475365", "SUMITOMO_MITSUI", "Sumitomo Mitsui Trust",       "Sumitomo Mitsui Trust Holdings / Group Inc."),
    ("1411530", "SUMITOMO_MITSUI", "Sumitomo Mitsui Trust",       "Sumitomo Mitsui DS Asset Management Co."),

    # ── NATIXIS (3 CIKs) ──────────────────────────────────────────────────────
    # French bank (Groupe BPCE subsidiary) + US advisor + international.
    ("1274981", "NATIXIS",         "Natixis",                     "Natixis (French bank parent, 1.0B)"),
    ("1018331", "NATIXIS",         "Natixis",                     "Natixis Advisors LLC/LP (US, 0.6B)"),
    ("1166767", "NATIXIS",         "Natixis",                     "Natixis Investment Managers International"),

    # ── SWEDBANK (2 CIKs) ─────────────────────────────────────────────────────
    # Same Swedish bank under two registration periods/names.
    ("946431",  "SWEDBANK",        "Swedbank AB",                 "Swedbank AB (1.3B)"),
    ("1633050", "SWEDBANK",        "Swedbank AB",                 "Swedbank (0.9B)"),

    # ── NOMURA (3 CIKs) ───────────────────────────────────────────────────────
    # Japanese investment bank. All subsidiaries of Nomura Holdings.
    ("1055964", "NOMURA",          "Nomura Group",                "Nomura Asset Management Co. Ltd (0.7B)"),
    ("1163653", "NOMURA",          "Nomura Group",                "Nomura Holdings Inc (0.6B)"),
    ("921739",  "NOMURA",          "Nomura Group",                "Nomura Asset Management International"),

    # ── BANK OF NOVA SCOTIA (2 CIKs) ─────────────────────────────────────────
    # Scotiabank. Trust Co is a small subsidiary.
    ("9631",    "BANK_OF_NS",      "Bank of Nova Scotia",         "Bank of Nova Scotia (main, 1.1B)"),
    ("1335382", "BANK_OF_NS",      "Bank of Nova Scotia",         "Bank of Nova Scotia Trust Co"),

    # ── CI FINANCIAL (2 CIKs) ────────────────────────────────────────────────
    # Canadian asset manager. Global entity is subsidiary.
    ("1163648", "CI_FINANCIAL",    "CI Financial Corp",           "CI Investments Inc. (main, 1.0B)"),
    ("1523847", "CI_FINANCIAL",    "CI Financial Corp",           "CI Global Investments Inc."),

    # ── LANSDOWNE PARTNERS (2 CIKs) ──────────────────────────────────────────
    # UK-based hedge fund. UK LLP + US LP are same fund.
    ("1608485", "LANSDOWNE",       "Lansdowne Partners",          "Lansdowne Partners (UK) LLP (1.4B)"),
    ("1315309", "LANSDOWNE",       "Lansdowne Partners",          "Lansdowne Partners LP (US entity)"),

    # ── MITSUBISHI UFJ ASSET MANAGEMENT (2 CIKs) ─────────────────────────────
    # Japan-based AM. UK entity is subsidiary. (Excludes Morgan Stanley JV)
    ("1466546", "MUFG_AM",         "Mitsubishi UFJ Asset Mgmt",   "Mitsubishi UFJ Asset Management Co. Ltd (1.0B)"),
    ("1694895", "MUFG_AM",         "Mitsubishi UFJ Asset Mgmt",   "Mitsubishi UFJ Asset Management (UK) Ltd"),
]

# ─────────────────────────────────────────────────────────────────────────────
# BUILD AND SAVE
# ─────────────────────────────────────────────────────────────────────────────

df = pd.DataFrame(CONSOLIDATION, columns=["cik","parent_id","parent_name","notes"])
df.to_csv(OUTPUT_CSV, index=False)

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 65)
print("ENTITY CONSOLIDATION MAP — COMPLETE")
print("=" * 65)
print(f"Total entries: {len(df)}")
print(f"Parent groups: {df.parent_id.nunique()}")
print()

for parent_id, group in df.groupby("parent_id"):
    print(f"{parent_id:<22} {len(group)} CIKs merged")

# Check coverage against our holdings data
h = pd.read_csv(os.path.join(DATA_DIR, "holdings_9firms.csv"), dtype={"filer_cik": str})
h["filer_cik"] = h["filer_cik"].str.replace(r"\.0$","",regex=True).str.strip()
mapped_ciks = set(df["cik"].astype(str))
h["is_mapped"] = h["filer_cik"].isin(mapped_ciks)

mapped_shares   = h[h["is_mapped"]]["shares_held"].sum()
total_shares    = h["shares_held"].sum()
print()
print(f"\nShares in mapped entities: {mapped_shares/1e12:.2f}T ({mapped_shares/total_shares*100:.1f}% of total)")
print(f"Shares in unmapped CIKs:   {(total_shares-mapped_shares)/1e12:.2f}T ({(1-mapped_shares/total_shares)*100:.1f}% of total)")
print(f"\nSaved → {OUTPUT_CSV}")
