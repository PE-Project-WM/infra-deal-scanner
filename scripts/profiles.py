"""Step 06b: a short profile for each ranked company: why it is on the list, and what to check first.

Built from the score parts, the multi-year history (history.py), ownership and the confidence notes, plus any
manual notes in config/company_notes.csv. Reasons are written in plain English for the website.
Skills: deal-screening (business-quality flags), red-flag-register (each check is something to price, fix or walk away on).
"""
import os, json
import pandas as pd
from fx import rate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, CFG = f'{ROOT}/data/outputs', f'{ROOT}/config'
W = json.load(open(f'{CFG}/criteria_digital_infra.json'))['scoring_weights']
R = pd.read_csv(f'{OUT}/ranking_latest.csv', dtype={'CompanyNumber': str})
L = pd.read_csv(f'{OUT}/lenses_latest.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber')
H = pd.read_csv(f'{OUT}/history.csv', dtype={'CompanyNumber': str}) if os.path.exists(f'{OUT}/history.csv') else pd.DataFrame(columns=['CompanyNumber'])
HS = pd.read_csv(f'{OUT}/history_summary.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(f'{OUT}/history_summary.csv') else pd.DataFrame()
BS = pd.read_csv(f'{CFG}/balance_sheet.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(f'{CFG}/balance_sheet.csv') else pd.DataFrame()
RM = pd.read_csv(f'{CFG}/revenue_mix.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(f'{CFG}/revenue_mix.csv') else pd.DataFrame()
_V = f'{os.path.dirname(OUT)}/ocr/verified.csv'
OCR_CHECKED = pd.read_csv(_V, dtype={'CompanyNumber': str}).set_index('CompanyNumber')['result'].to_dict() if os.path.exists(_V) else {}
NOTES = pd.read_csv(f'{CFG}/company_notes.csv', dtype={'CompanyNumber': str}) if os.path.exists(f'{CFG}/company_notes.csv') else pd.DataFrame(columns=['CompanyNumber', 'check'])
m = lambda v: f'£{v / 1e6:.1f}m'
pct = lambda v: f'{v * 100:.0f}%'

def hs(num, col):
    if num in HS.index and col in HS.columns and pd.notna(HS.at[num, col]):
        return HS.at[num, col]
    return None

def why(r):
    out = []
    frac = {k: r[f'pts_{k}'] / w for k, w in W.items() if w}
    if frac.get('strategy_fit', 0) >= 0.99:
        out.append('Squarely inside the investment case')
    if frac.get('margin_quality', 0) >= 0.75:
        out.append(f"High margin ({pct(r['ebitda_margin'])} EBITDA)")
    if frac.get('size_fit', 0) >= 0.99:
        out.append(f"EBITDA of {m(r['ebitda'])}, in the £2–15m range most mid-market buyers target")
    cagr = hs(r['CompanyNumber'], 'sales_cagr')
    if cagr is not None and cagr >= 0.1:
        out.append(f"Sales up {pct(cagr)} a year over {int(hs(r['CompanyNumber'], 'years_of_sales'))} years")
    elif pd.notna(r['turnover_growth']) and r['turnover_growth'] >= 0.15:
        out.append(f"Sales up {pct(r['turnover_growth'])} last year")
    if frac.get('balance_sheet', 0) >= 0.85:
        out.append(f"Cash of {m(r['cash'])} and net assets of {m(r['net_assets'])}")
    if str(r['accessibility']).startswith('High'):
        out.append('Founder-owned, so a direct approach is possible')
    if frac.get('revenue_visibility', 0) >= 0.85:
        out.append('Most sales repeat (read from the accounts)' if r['CompanyNumber'] in RM.index else 'A type of business that usually earns repeat revenue (estimated)')
    return out[:4]

def checks(r):
    num, out = r['CompanyNumber'], []
    own, since = str(r['ownership']), r['owner_since_year']
    if own.startswith('Sponsor-owned'):
        out.append(f"Bought by a private equity fund in {int(since) if pd.notna(since) else 'recent years'}: unlikely to be sold for a few years")
    elif own.startswith('Employee-owned'):
        out.append('Employee-owned: a sale needs the trustees to agree and is rare')
    elif own.startswith('Foreign parent'):
        out.append('Part of an overseas group: buying it means a carve-out from the parent')
    elif own.startswith('Likely sponsor'):
        out.append('Probably owned by a private equity fund: check when it bought in')
    elif own == 'Unknown':
        out.append('Owner not yet confirmed')
    if num in BS.index:
        b = BS.loc[num].fillna(0)
        f = rate(b['currency'])   # balance sheet converted to pounds, like the ranking EBITDA
        nd = float(b['bank_debt'] + b['leases_hp'] + b['shareholder_or_group_loans'] - b['cash']) * f
        owed = float(b['other_owed_to_group']) * f
        if r['ebitda'] > 0 and nd / r['ebitda'] >= 2:
            out.append(f"Net debt of {m(nd)}, {nd / r['ebitda']:.1f}x EBITDA: most of the price would go to lenders, not shareholders")
        if owed > 2 * max(r['ebitda'], 1):
            out.append(f"A further {m(owed)} is owed to group companies: find out whether it is debt")
    cover = hs(num, 'interest_cover')
    if cover is not None and cover < 3:
        out.append(f"Interest cover only {cover:.1f}x: check how much debt it already carries")
    swing = hs(num, 'margin_swing_pp')
    if swing is not None and swing >= 10:
        out.append(f"Margin moved between {pct(hs(num, 'margin_min'))} and {pct(hs(num, 'margin_max'))} over the years read: find out what drives it")
    g = r['turnover_growth']
    if pd.notna(g) and g <= -0.10:
        out.append(f"Sales fell {pct(-g)} last year: find out why")
    cagr = hs(num, 'sales_cagr')
    if (cagr is not None and cagr >= 0.3) or (cagr is None and pd.notna(g) and g >= 0.4):
        if not (NOTES['CompanyNumber'] == num).any():
            out.append(f"Sales up {pct(cagr if cagr is not None else g)} {'a year' if cagr is not None else 'in one year'}: check how much came from acquisitions or one-off contracts")
    if str(r['ebitda_basis']).startswith('ESTIMATE'):
        out.append('EBITDA is estimated because depreciation is not tagged: confirm from the accounts')
    if str(r['figures_source']).startswith('OCR') and num in OCR_CHECKED:
        out.append('Figures were read by OCR and checked against the filing: ' + OCR_CHECKED[num])
    elif str(r['figures_source']).startswith('OCR'):
        out.append('Figures were read by OCR from scanned accounts: check every number against the filing')
    elif str(r['figures_source']) != 'Tagged':
        out.append('Figures were read from the text of the accounts: check them against the filing')
    if r['relevance'] == 'ADJACENT':
        out.append('Only adjacent to the investment case: confirm it owns or runs infrastructure')
    out += NOTES.loc[NOTES['CompanyNumber'] == num, 'check'].tolist()
    if num in RM.index:
        if pd.notna(RM.at[num, 'concentration']):
            out.append(RM.at[num, 'concentration'])
        out.append('Repeat revenue is read from the accounts, which rarely give renewal rates: get the contract list and renewal history')
    else:
        out.append('Repeat revenue is estimated from the type of business: get the contract mix, customer concentration and renewal rates')
    return out

def history(num):
    g = H[H['CompanyNumber'] == num].dropna(subset=['sales'])
    return [{'year': int(x['fy']), 'sales': float(x['sales']), 'margin': None if pd.isna(x['margin']) else float(x['margin']),
             'basis': x['profit_basis']} for _, x in g.iterrows()]

P = {}
for _, r in R.iterrows():
    num = r['CompanyNumber']
    P[num] = {'rank': int(r['rank']), 'confidence': r['confidence'], 'confidence_reasons': '' if pd.isna(r['confidence_reasons']) else r['confidence_reasons'],
              'why': why(r), 'checks': checks(r), 'history': history(num), 'ebitda': None if pd.isna(r['ebitda']) else float(r['ebitda']),
              'interest_cover': hs(num, 'interest_cover'), 'revenue_mix': RM.at[num, 'evidence'] if num in RM.index else None,
              'revenue_mix_source': RM.at[num, 'source'] if num in RM.index else None, 'capex_share': hs(num, 'capex_share_avg')}
json.dump(P, open(f'{OUT}/profiles.json', 'w'), indent=1, default=str)
for num, p in list(P.items())[:3]:
    print(R.loc[R['CompanyNumber'] == num, 'CompanyName'].iloc[0], json.dumps(p, indent=1, default=str)[:900])
print(f'Saved profiles.json for {len(P)} ranked companies')
