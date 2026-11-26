"""Step 04d: one set of EBITDA rules for every company (method v4, rulebook section 5).

Reported EBITDA is operating profit plus depreciation and amortisation from the latest accounts. Before scoring,
the same rules are applied to every company, in this order:

  R0  Missing D&A. Where EBITDA was only operating profit because no D&A was tagged or read, D&A read from the
      text of the same accounts is added (a correction, not an adjustment).
  R1  R&D tax credits (RDEC) booked in operating profit are taken out: they are a tax relief, not trading profit.
  R2  IFRS 16. Accounts under IFRS put lease costs below EBITDA; depreciation of leased (right-of-use) assets is
      taken off so every company is on the UK GAAP (FRS 102) basis, where rent is an operating cost.
  R3  One-year margin jump. Where the latest margin is more than 10 points above the average of the earlier years
      read, EBITDA is priced on the average margin of the latest two years, until a second year shows it holds.
  R4  Exceptional items. Costs the accounts call exceptional are added back, and exceptional gains taken off, only
      where the item has been checked against the filing (config/ebitda_adjustments.csv). Items found by the
      reader but not yet checked are listed, not applied: an add-back needs evidence, a deduction does not.
  R5  Directors' pay is not adjusted: what owners pay themselves is a cost of running the business, and any
      add-back is for a buyer to negotiate.
  Hand-checked adjustments in config/ebitda_adjustments.csv are applied on top and win over the reader for the same item.

Writes data/outputs/ebitda_normalised.csv. score.py ranks on the normalised figure and shows both.
Skills: cim-red-flag-reviewer (quality of earnings), red-flag-register.
"""
import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, CFG = f'{ROOT}/data/outputs', f'{ROOT}/config'
D = pd.read_csv(f'{OUT}/candidates_clean.csv', dtype={'CompanyNumber': str})
D = D[D['goes_forward']].copy()
TF = f'{ROOT}/data/history/text_figures.csv'
T = pd.read_csv(TF, dtype={'CompanyNumber': str}) if os.path.exists(TF) else pd.DataFrame(columns=['CompanyNumber', 'filed'])
T = T[T.get('problem', pd.Series(dtype=str)).fillna('') == ''] if len(T) else T
latest = T.sort_values('filed').drop_duplicates('CompanyNumber', keep='last').set_index('CompanyNumber') if len(T) else pd.DataFrame()
HS_PATH = f'{OUT}/history_summary.csv'
HS = pd.read_csv(HS_PATH, dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(HS_PATH) else pd.DataFrame()
H = pd.read_csv(f'{OUT}/history.csv', dtype={'CompanyNumber': str}) if os.path.exists(f'{OUT}/history.csv') else pd.DataFrame(columns=['CompanyNumber', 'fy', 'margin'])
AD_PATH = f'{CFG}/ebitda_adjustments.csv'
AD = pd.read_csv(AD_PATH, dtype={'CompanyNumber': str}) if os.path.exists(AD_PATH) else pd.DataFrame(columns=['CompanyNumber', 'item', 'amount_gbp', 'reason', 'source'])
from fx import to_gbp
from settings import business_type


def val(row, col):
    v = row.get(col) if row is not None else None
    return None if v is None or pd.isna(v) else float(v)


rows = []
for _, r in D.iterrows():
    num = r['CompanyNumber']
    f = to_gbp(num)
    e = r['ebitda'] * f if pd.notna(r['ebitda']) else None
    sales = r['turnover'] * f if pd.notna(r['turnover']) else None
    out = {'CompanyNumber': num, 'ebitda_reported': e, 'basis_reported': r['ebitda_basis']}
    steps, listed = [], []
    t = latest.loc[num] if len(latest) and num in latest.index else None
    if t is not None and sales and abs(val(t, 'turnover') * f - sales) > 0.02 * sales:
        t = None   # the text reader found a different year or entity: do not mix figures
    norm = e
    if norm is not None and str(r['ebitda_basis']).startswith('ESTIMATE') and t is not None and val(t, 'da_total'):
        norm += val(t, 'da_total') * f
        steps.append(f"R0 D&A of £{val(t, 'da_total') * f / 1e6:.2f}m read from the accounts text added")
        out['basis_normalised'] = 'Operating profit + D&A (D&A read from the text)'
    hand = AD[AD['CompanyNumber'] == num]
    hand_items = set(hand['item'])
    if norm is not None and t is not None:
        if val(t, 'rdec') and 'rdec' not in hand_items and val(t, 'rdec') < 0.5 * abs(norm):
            norm -= val(t, 'rdec') * f
            steps.append(f"R1 R&D tax credit of £{val(t, 'rdec') * f / 1e6:.2f}m taken out")
        if t.get('ifrs') in (True, 'True') and val(t, 'rou_depreciation') and 'ifrs16' not in hand_items and val(t, 'rou_depreciation') < 0.5 * abs(norm):
            norm -= val(t, 'rou_depreciation') * f
            steps.append(f"R2 IFRS 16: £{val(t, 'rou_depreciation') * f / 1e6:.2f}m of leased-asset depreciation taken off")
        if val(t, 'exceptional') and 'exceptional' not in hand_items:
            listed.append(f"R4 exceptional item of about £{val(t, 'exceptional') * f / 1e6:.2f}m in the accounts: not applied until checked")
    for _, a in hand.iterrows():
        if norm is not None:
            norm += float(a['amount_gbp'])
            steps.append(f"{a['item']}: {'+' if a['amount_gbp'] > 0 else '−'}£{abs(float(a['amount_gbp'])) / 1e6:.2f}m, {a['reason']} (checked: {a['source']})")
    # R3 is for services and contractors with positive EBITDA: a network owner's margin is meant to rise as it fills
    if (norm is not None and norm > 0 and sales and business_type(num) in ('recurring_services', 'contractor')
            and num in HS.index and pd.notna(HS.at[num, 'margin_prior_avg']) and 'margin' not in hand_items):
        m_now, m_before = norm / sales, float(HS.at[num, 'margin_prior_avg'])
        g = H[H['CompanyNumber'] == num].dropna(subset=['margin']).sort_values('fy')
        # history margins are on operating profit; compare like with like by adding back this year's D&A share
        da_share = max(0.0, (norm - (r['operating_profit'] * f if pd.notna(r['operating_profit']) else norm)) / sales)
        if len(g) >= 2 and m_before + da_share > 0 and m_now - (m_before + da_share) > 0.10:
            two = (g['margin'].iloc[-1] + g['margin'].iloc[-2]) / 2 + da_share
            new = min(norm, two * sales)
            steps.append(f"R3 margin jumped from about {m_before + da_share:.0%} to {m_now:.0%} in one year: priced on the two-year average ({two:.0%})")
            norm = new
    out.update(ebitda_normalised=norm, adjustments='; '.join(steps), not_applied='; '.join(listed),
               adjusted=bool(steps) and not all(s.startswith('R0') for s in steps))
    rows.append(out)

N = pd.DataFrame(rows)
N.to_csv(f'{OUT}/ebitda_normalised.csv', index=False)
chg = N[N['adjustments'] != '']
print(f'EBITDA rules applied to {len(N)} companies; changed for {len(chg)}:')
pd.set_option('display.width', 250)
pd.set_option('display.max_colwidth', 160)
print(chg[['CompanyNumber', 'ebitda_reported', 'ebitda_normalised', 'adjustments']].to_string(index=False))
