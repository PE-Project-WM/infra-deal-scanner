"""Size check: is each ranked company a realistic lower mid-market deal?

For every ranked company this estimates the enterprise value (the price for the business) from its
latest EBITDA and flags companies that are probably too big or too small for the target deal size.

- Service firms and contractors use the same multiple ranges as the price check (config/valuation.json).
- Owners of towers and fibre networks (config/asset_owners.csv) use the network asset owner range,
  because infrastructure funds price them far above services firms.
- Where a real price is public (a sale or a reported valuation), it is shown and used for the flag.

The flag never changes the score. Output: data/outputs/size_check.csv.
"""
import json, os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = json.load(open(f'{ROOT}/config/valuation.json'))
M = V['multiple_ranges']
BAND = V['deal_size_band_gbp']
from settings import C, TYPES
rk = pd.read_csv(f'{ROOT}/data/outputs/ranking_latest.csv', dtype={'CompanyNumber': str})
AO = pd.read_csv(f'{ROOT}/config/asset_owners.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber')


def m(x):
    return f'£{x / 1e9:.1f}bn' if x >= 1e9 else f'£{x / 1e6:.0f}m'


def flag(low, high):
    lo, hi = BAND['low'], BAND['high']
    if low > hi:
        return 'Probably above £250m'
    if high > hi:
        return 'Could be above £250m'
    if high < lo:
        return 'Below £10m'
    if low < lo:
        return 'Could be below £10m'
    return 'Within £10–250m'


rows = []
for _, r in rk.iterrows():
    num, e = r['CompanyNumber'], r['ebitda']
    out = {'rank': int(r['rank']), 'CompanyNumber': num, 'CompanyName': r['CompanyName'], 'ebitda': e}
    asset = num in AO.index
    kind = r['business_type'] if 'business_type' in r and pd.notna(r['business_type']) else ('network_owner' if asset else 'recurring_services')
    if kind == 'project_company':
        out.update(size_flag='Within £10–250m' if pd.notna(e) and e > 0 else 'Not estimated', size_basis='Project company: valued on the cash left in its contract (see the price check)', size_kind=TYPES[kind]['label'])
        rows.append(out)
        continue
    band = dict(TYPES[kind]['price_range'])
    if kind != 'network_owner' and pd.notna(e) and e < M['small_ebitda_threshold_gbp']:
        for k in ('low', 'high'):
            band[k] -= M['small_ebitda_discount']
    if pd.isna(e) or e <= 0:
        out.update(size_flag='Not estimated', size_basis='No positive EBITDA to price')
        rows.append(out)
        continue
    low, high = e * band['low'], e * band['high']
    basis = f'Network owner: {AO.at[num, "asset_type"].lower()}' if asset else TYPES[kind]['label']
    out.update(ev_low=round(low), ev_high=round(high), mult_low=band['low'], mult_high=band['high'], size_kind=basis)
    text = f'{m(low)}–{m(high)} at {band["low"]:g}–{band["high"]:g}x EBITDA of {m(e)} ({basis.lower()})'
    rep = AO.at[num, 'reported_ev_gbp'] if asset else None
    if rep is not None and pd.notna(rep):
        rep = float(rep)
        out.update(reported_ev=rep, reported_basis=AO.at[num, 'reported_ev_basis'], reported_source=AO.at[num, 'source'])
        text = f'{m(rep)}: {AO.at[num, "reported_ev_basis"][0].lower()}{AO.at[num, "reported_ev_basis"][1:]}. From EBITDA: {text}'
        out['size_flag'] = flag(rep, rep) if rep > BAND['high'] else flag(min(low, rep), max(high, rep))
    else:
        out['size_flag'] = flag(low, high)
    out['size_basis'] = text
    rows.append(out)

S = pd.DataFrame(rows)
S.to_csv(f'{ROOT}/data/outputs/size_check.csv', index=False)
top = S[S['rank'] <= 10]
print('Size check:', S['size_flag'].value_counts().to_dict())
print('Top ten:', top['size_flag'].value_counts().to_dict())
