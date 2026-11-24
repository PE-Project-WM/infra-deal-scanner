"""Step 04b: multi-year financial history for the companies with a deep dive (last 3 filed accounts).

Reads the tagged numbers saved by deep_dive.py and builds, per company and year: sales, operating profit
(profit before tax where operating profit is not tagged), margin, interest paid, capital spending and bank debt.
Then a summary per company: years of history, sales growth per year (CAGR), margin range and stability,
interest cover and capex as a share of sales.
Used by score.py (margin stability, interest cover), lenses.py (multi-year growth) and the website.
Skills: deal-screening (preliminary financial assessment).
"""
import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F_PATH, OUT = f'{ROOT}/data/deep_dive/facts.csv', f'{ROOT}/data/outputs'
TAGS = {
    'TurnoverRevenue': 'sales',
    'OperatingProfitLoss': 'operating_profit',
    'ProfitLossOnOrdinaryActivitiesBeforeTax': 'profit_before_tax',
    'InterestPayableSimilarChargesFinanceCosts': 'interest',
    'AdditionsOtherThanThroughBusinessCombinationsPropertyPlantEquipment': 'capex',
    'TotalAdditionsIncludingFromBusinessCombinationsPropertyPlantEquipment': 'capex_total',
    'BankBorrowings': 'bank_debt',
    'BankBorrowingsOverdrafts': 'bank_debt_overdraft',
    'FinanceLeaseLiabilitiesPresentValueTotal': 'finance_leases',
    'CashBankOnHand': 'cash',
}

if not os.path.exists(F_PATH):
    print('No deep-dive facts yet; skipping history.')
    raise SystemExit(0)

F = pd.read_csv(F_PATH, dtype={'CompanyNumber': str})
F = F[F['tag'].isin(TAGS) & F['has_dimension'].isna()].copy()
F['year_end'] = pd.to_datetime(F['period_end'])
# The same year can appear in two filings (as the current and the comparative year) and with dates a day apart: keep the latest filing's figure
F = F.sort_values('filed').drop_duplicates(['CompanyNumber', 'tag', 'period_end'], keep='last')
F['fy'] = F['year_end'].dt.year   # financial year labelled by the calendar year it ends in
H = (F.pivot_table(index=['CompanyNumber', 'CompanyName', 'fy'], columns='tag', values='value', aggfunc='last')
       .rename(columns=TAGS).reset_index())
for c in TAGS.values():
    if c not in H:
        H[c] = pd.NA
H['profit'] = H['operating_profit'].fillna(H['profit_before_tax'])
H['profit_basis'] = H['operating_profit'].notna().map({True: 'Operating profit', False: 'Profit before tax'})
H['margin'] = H['profit'] / H['sales']
H['capex'] = H['capex'].fillna(H['capex_total'])
H['bank_debt'] = H['bank_debt'].fillna(H['bank_debt_overdraft'])
H = H.drop(columns=['capex_total', 'bank_debt_overdraft']).sort_values(['CompanyNumber', 'fy'])
H.to_csv(f'{OUT}/history.csv', index=False)

rows = []
for num, g in H.groupby('CompanyNumber'):
    s = g.dropna(subset=['sales'])
    m = g.dropna(subset=['margin'])
    last = g.iloc[-1]
    years = len(s)
    cagr = (s['sales'].iloc[-1] / s['sales'].iloc[0]) ** (1 / (years - 1)) - 1 if years >= 3 and s['sales'].iloc[0] > 0 else None
    interest = g.dropna(subset=['interest'])
    cover = None
    if len(interest) and pd.notna(last['profit']) and interest['interest'].iloc[-1] > 0:
        cover = float(last['profit'] + interest['interest'].iloc[-1]) / float(interest['interest'].iloc[-1]) if last['profit_basis'] == 'Profit before tax' else float(last['profit']) / float(interest['interest'].iloc[-1])
    capex_share = (g['capex'] / g['sales']).dropna()
    rows.append({
        'CompanyNumber': num, 'CompanyName': g['CompanyName'].iloc[0],
        'years_of_sales': years, 'first_year': int(s['fy'].iloc[0]) if years else None, 'last_year': int(s['fy'].iloc[-1]) if years else None,
        'sales_cagr': cagr,
        'years_of_margin': len(m),
        'margin_min': m['margin'].min() if len(m) else None, 'margin_max': m['margin'].max() if len(m) else None,
        'margin_swing_pp': (m['margin'].max() - m['margin'].min()) * 100 if len(m) >= 3 else None,
        'margin_basis': m['profit_basis'].iloc[-1] if len(m) else None,
        'interest_latest': interest['interest'].iloc[-1] if len(interest) else None,
        'interest_cover': cover,
        'capex_share_avg': capex_share.mean() if len(capex_share) else None,
        'bank_debt_latest': g['bank_debt'].dropna().iloc[-1] if g['bank_debt'].notna().any() else None,
    })
S = pd.DataFrame(rows)
S.to_csv(f'{OUT}/history_summary.csv', index=False)
pd.set_option('display.width', 250)
show = S.copy()
for c in ('sales_cagr', 'margin_min', 'margin_max', 'capex_share_avg'):
    show[c] = show[c].map(lambda v: '' if pd.isna(v) else f'{v:.0%}')
print(show.drop(columns=['CompanyNumber']).to_string(index=False))
print(f'\nSaved history.csv ({len(H)} company-years) and history_summary.csv ({len(S)} companies)')
