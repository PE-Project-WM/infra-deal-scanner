"""Step 06c: screening-level price check for the top ranked companies. Kept separate from the score.

For each company: an indicative price range (enterprise value) from listed-peer and deal multiples, and a
sponsor returns check: the IRR at the middle of the range, and the walk-away multiple, i.e. the highest entry
multiple at which a buyer still makes the 20% hurdle with debt fixed in pounds and the exit flat to entry.
Net debt and cash conversion come from config/balance_sheet.csv (figures transcribed from each company's latest
filed accounts, read from data/deep_dive/text), which turns the price of the business (enterprise value) into a
price for the shares (equity value). Accounts in other currencies are converted to pounds.
All inputs and benchmark sources are in config/valuation.json. Illustrative only; not a valuation of any company.
Skills: valuation-triangulator (lenses and reconciliation), returns-sensitivity (walk-away price and elasticity).
"""
import os, json
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, CFG = f'{ROOT}/data/outputs', f'{ROOT}/config'
V = json.load(open(f'{CFG}/valuation.json'))
M, SP = V['multiple_ranges'], V['sponsor_case']
W = json.load(open(f'{CFG}/criteria_digital_infra.json'))['scoring_weights']
R = pd.read_csv(f'{OUT}/ranking_latest.csv', dtype={'CompanyNumber': str})
HS = pd.read_csv(f'{OUT}/history_summary.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(f'{OUT}/history_summary.csv') else pd.DataFrame()
TOP_N = int(os.environ.get('VALUATION_TOP_N', '10'))
FX = V.get('fx_to_gbp', {'GBP': 1.0})
BS_PATH = f'{CFG}/balance_sheet.csv'
BS = pd.read_csv(BS_PATH, dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(BS_PATH) else pd.DataFrame()
num_or_none = lambda v: None if pd.isna(v) else float(v)

def hs(num, col):
    if num in HS.index and col in HS.columns and pd.notna(HS.at[num, col]):
        return float(HS.at[num, col])
    return None

def returns(entry_mult, e0, sales0, debt, g, capex_pct, exit_mult=None, ebitda_shift=1.0, wc=None):
    """Five-year sponsor case. Debt is fixed in pounds; spare cash repays it, then builds up as cash."""
    exit_mult = entry_mult if exit_mult is None else exit_mult
    ev0 = entry_mult * e0
    equity0 = ev0 * (1 + SP['fees_pct_of_ev']) - debt
    if equity0 <= 0:
        return None
    net_debt, e, sales = debt, e0, sales0
    for _ in range(SP['hold_years']):
        e *= 1 + g
        sales *= 1 + g
        capex = capex_pct * sales
        interest = SP['interest_rate'] * max(net_debt, 0)
        tax = SP['tax_rate'] * max(e - capex - interest, 0)   # capex as a stand-in for depreciation
        cash = e - capex - tax - interest - (SP['working_capital_drag_pct_ebitda'] if wc is None else wc) * e
        net_debt -= cash
    equity_exit = exit_mult * e * ebitda_shift - net_debt
    moic = equity_exit / equity0
    return {'irr': moic ** (1 / SP['hold_years']) - 1 if moic > 0 else -1.0, 'moic': moic, 'equity0': equity0}

def walk_away(e0, sales0, debt, g, capex_pct, wc=None):
    lo, hi = 2.0, 20.0
    if (returns(hi, e0, sales0, debt, g, capex_pct, wc=wc) or {'irr': -1})['irr'] >= SP['hurdle_irr']:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        r = returns(mid, e0, sales0, debt, g, capex_pct, wc=wc)
        if r is not None and r['irr'] >= SP['hurdle_irr']:
            lo = mid
        else:
            hi = mid
    return lo

rows = []
for _, r in R.head(TOP_N).iterrows():
    num, e0, sales0 = r['CompanyNumber'], float(r['ebitda']), float(r['turnover'])
    if pd.isna(e0) or e0 <= 0:
        continue
    b = BS.loc[num] if num in BS.index else None
    cur = b['currency'] if b is not None else 'GBP'
    fx = FX.get(cur, 1.0)
    # ranking figures are already in pounds (score.py converts them); balance-sheet items are converted below
    conv = fcf_conv = None
    net_debt = debt_parts = None
    if b is not None:
        cfo, capex_actual = num_or_none(b['cash_from_operations']), num_or_none(b['capex'])
        if cfo is not None:
            conv = cfo * fx / e0
            fcf_conv = (cfo - (capex_actual or 0)) * fx / e0
        debt_parts = {k: float(b[k] or 0) * fx for k in ('bank_debt', 'leases_hp', 'shareholder_or_group_loans')}
        net_debt = sum(debt_parts.values()) - float(b['cash'] or 0) * fx
        other_group = float(b['other_owed_to_group'] or 0) * fx
    vis = r['pts_revenue_visibility'] / W['revenue_visibility']
    kind = 'recurring_services' if vis >= 0.6 else 'project_contractors'
    band = dict(M[kind])
    small = e0 < M['small_ebitda_threshold_gbp']
    if small:
        for k in ('low', 'mid', 'high'):
            band[k] -= M['small_ebitda_discount']
    debt = (SP['debt_turns_recurring'] if kind == 'recurring_services' else SP['debt_turns_contractor']) * e0
    cagr = hs(num, 'sales_cagr')
    hist_g = cagr if cagr is not None else (float(r['turnover_growth']) if pd.notna(r['turnover_growth']) else 0.0)
    g = max(0.0, min(SP['growth_cap'], hist_g * SP['growth_haircut']))
    capex_pct = max(hs(num, 'capex_share_avg') or 0, SP['default_capex_pct_sales'])
    if b is not None and num_or_none(b['capex']) is not None:
        capex_pct = max(float(b['capex']) * fx / sales0, 0.0)   # actual capex from the latest accounts
    wc = None if conv is None else max(0.0, min(SP.get('max_working_capital_drag_pct_ebitda', 0.3), 1 - conv))
    base = returns(band['mid'], e0, sales0, debt, g, capex_pct, wc=wc)
    wa = walk_away(e0, sales0, debt, g, capex_pct, wc=wc)
    up = returns(band['mid'], e0, sales0, debt, g, capex_pct, exit_mult=band['mid'] + 1, wc=wc)
    down = returns(band['mid'], e0, sales0, debt, g, capex_pct, exit_mult=band['mid'] - 1, wc=wc)
    eb_up = returns(band['mid'], e0, sales0, debt, g, capex_pct, ebitda_shift=1.1, wc=wc)
    eb_down = returns(band['mid'], e0, sales0, debt, g, capex_pct, ebitda_shift=0.9, wc=wc)
    verdict = ('Clears 20% at a typical price' if wa >= band['mid'] else
               'Clears 20% only at the low end of the range' if wa >= band['low'] else
               'Does not clear 20% within the range')
    rows.append({
        'rank': int(r['rank']), 'CompanyName': r['CompanyName'], 'CompanyNumber': num,
        'ebitda': e0, 'sales': sales0,
        'basis': 'Recurring services' if kind == 'recurring_services' else 'Project contractor',
        'small_discount': small, 'mult_low': band['low'], 'mult_mid': band['mid'], 'mult_high': band['high'],
        'ev_low': band['low'] * e0, 'ev_mid': band['mid'] * e0, 'ev_high': band['high'] * e0,
        'debt_assumed': debt, 'growth_assumed': g, 'capex_pct': capex_pct,
        'irr_mid': base['irr'] if base else None, 'moic_mid': base['moic'] if base else None,
        'walk_away_mult': wa, 'walk_away_ev': wa * e0,
        'irr_exit_plus1': up['irr'] if up else None, 'irr_exit_minus1': down['irr'] if down else None,
        'irr_ebitda_plus10': eb_up['irr'] if eb_up else None, 'irr_ebitda_minus10': eb_down['irr'] if eb_down else None,
        'verdict': verdict, 'currency': cur, 'fx_to_gbp': fx,
        'accounts_year_end': None if b is None else b['year_end'],
        'net_debt': net_debt, 'debt_parts': debt_parts, 'cash_gbp': None if b is None else float(b['cash'] or 0) * fx,
        'restricted_cash': None if b is None else float(b['restricted_cash'] or 0) * fx,
        'other_owed_to_group': None if b is None else other_group,
        'equity_low': None if net_debt is None else band['low'] * e0 - net_debt,
        'equity_high': None if net_debt is None else band['high'] * e0 - net_debt,
        'walk_away_equity': None if net_debt is None else wa * e0 - net_debt,
        'net_debt_to_ebitda': None if net_debt is None else net_debt / e0,
        'cash_conversion': conv, 'fcf_conversion': fcf_conv, 'wc_drag_used': wc,
        'balance_note': None if b is None else b['note'],
        'notes': '; '.join(n['note'] for n in V.get('market_notes', []) if num in n['companies']),
    })

out = pd.DataFrame(rows)
out.to_csv(f'{OUT}/valuation_latest.csv', index=False)
json.dump({'as_of': V['as_of'], 'assumptions': {**SP, 'multiple_ranges': M}, 'benchmarks': V['benchmarks'],
           'companies': out.astype(object).where(pd.notna(out), None).to_dict('records')}, open(f'{OUT}/valuation_latest.json', 'w'), indent=1, default=str)
pd.set_option('display.width', 250)
show = out[['rank', 'CompanyName', 'currency', 'ebitda', 'ev_low', 'ev_high', 'net_debt', 'equity_low', 'equity_high', 'cash_conversion', 'irr_mid', 'walk_away_mult', 'verdict']].copy()
show['cash_conversion'] = show['cash_conversion'].map(lambda v: '' if pd.isna(v) else f'{v:.0%}')
show['growth_assumed'] = 0
for c in ('ebitda', 'ev_low', 'ev_high', 'net_debt', 'equity_low', 'equity_high'):
    show[c] = (show[c] / 1e6).round(1)
for c in ('growth_assumed', 'irr_mid'):
    show[c] = (show[c] * 100).round(1)
show['walk_away_mult'] = show['walk_away_mult'].round(1)
print(show.to_string(index=False))
print(f'\nSaved valuation_latest.csv and .json ({len(out)} companies)')
