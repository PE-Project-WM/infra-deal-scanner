"""Step 06c: screening-level price check for the top ranked companies. Kept separate from the score.

For each company: an indicative price range (enterprise value) from listed-peer and deal multiples, and a
sponsor returns check: the IRR at the middle of the range, and the walk-away multiple, i.e. the highest entry
multiple at which a buyer still makes the 20% hurdle with debt fixed in pounds and the exit flat to entry.
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

def hs(num, col):
    if num in HS.index and col in HS.columns and pd.notna(HS.at[num, col]):
        return float(HS.at[num, col])
    return None

def returns(entry_mult, e0, sales0, debt, g, capex_pct, exit_mult=None, ebitda_shift=1.0):
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
        cash = e - capex - tax - interest - SP['working_capital_drag_pct_ebitda'] * e
        net_debt -= cash
    equity_exit = exit_mult * e * ebitda_shift - net_debt
    moic = equity_exit / equity0
    return {'irr': moic ** (1 / SP['hold_years']) - 1 if moic > 0 else -1.0, 'moic': moic, 'equity0': equity0}

def walk_away(e0, sales0, debt, g, capex_pct):
    lo, hi = 2.0, 20.0
    if (returns(hi, e0, sales0, debt, g, capex_pct) or {'irr': -1})['irr'] >= SP['hurdle_irr']:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        r = returns(mid, e0, sales0, debt, g, capex_pct)
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
    base = returns(band['mid'], e0, sales0, debt, g, capex_pct)
    wa = walk_away(e0, sales0, debt, g, capex_pct)
    up = returns(band['mid'], e0, sales0, debt, g, capex_pct, exit_mult=band['mid'] + 1)
    down = returns(band['mid'], e0, sales0, debt, g, capex_pct, exit_mult=band['mid'] - 1)
    eb_up = returns(band['mid'], e0, sales0, debt, g, capex_pct, ebitda_shift=1.1)
    eb_down = returns(band['mid'], e0, sales0, debt, g, capex_pct, ebitda_shift=0.9)
    verdict = ('Clears 20% at a typical price' if wa >= band['mid'] else
               'Clears 20% only at the low end of the range' if wa >= band['low'] else
               'Does not clear 20% within the range')
    rows.append({
        'rank': int(r['rank']), 'CompanyName': r['CompanyName'], 'CompanyNumber': num,
        'ebitda': e0, 'cash': None if pd.isna(r['cash']) else float(r['cash']),
        'basis': 'Recurring services' if kind == 'recurring_services' else 'Project contractor',
        'small_discount': small, 'mult_low': band['low'], 'mult_mid': band['mid'], 'mult_high': band['high'],
        'ev_low': band['low'] * e0, 'ev_mid': band['mid'] * e0, 'ev_high': band['high'] * e0,
        'debt_assumed': debt, 'growth_assumed': g, 'capex_pct': capex_pct,
        'irr_mid': base['irr'] if base else None, 'moic_mid': base['moic'] if base else None,
        'walk_away_mult': wa, 'walk_away_ev': wa * e0,
        'irr_exit_plus1': up['irr'] if up else None, 'irr_exit_minus1': down['irr'] if down else None,
        'irr_ebitda_plus10': eb_up['irr'] if eb_up else None, 'irr_ebitda_minus10': eb_down['irr'] if eb_down else None,
        'verdict': verdict,
        'notes': '; '.join(n['note'] for n in V.get('market_notes', []) if num in n['companies']),
    })

out = pd.DataFrame(rows)
out.to_csv(f'{OUT}/valuation_latest.csv', index=False)
json.dump({'as_of': V['as_of'], 'assumptions': {**SP, 'multiple_ranges': M}, 'benchmarks': V['benchmarks'],
           'companies': out.to_dict('records')}, open(f'{OUT}/valuation_latest.json', 'w'), indent=1, default=str)
pd.set_option('display.width', 250)
show = out[['rank', 'CompanyName', 'basis', 'mult_low', 'mult_high', 'ev_low', 'ev_high', 'growth_assumed', 'irr_mid', 'walk_away_mult', 'verdict']].copy()
for c in ('ev_low', 'ev_high'):
    show[c] = (show[c] / 1e6).round(1)
for c in ('growth_assumed', 'irr_mid'):
    show[c] = (show[c] * 100).round(1)
show['walk_away_mult'] = show['walk_away_mult'].round(1)
print(show.to_string(index=False))
print(f'\nSaved valuation_latest.csv and .json ({len(out)} companies)')
