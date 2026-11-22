"""Step 05: score and rank the cleaned shortlist.

Each company gets 0-1 on six criteria, multiplied by the weights in the criteria file (total 100).
Accessibility (ownership) is kept as a separate label and never blended into the score.
Skills: deal-screening (scoring rubric), market-map-and-sourcing (fit and access kept apart; estimates labelled).
"""
import os, re, json, datetime
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, CFG = f'{ROOT}/data/outputs', f'{ROOT}/config'
C = json.load(open(f'{CFG}/criteria_digital_infra.json'))
W = C['scoring_weights']
D = pd.read_csv(f'{OUT}/candidates_clean.csv', dtype={'CompanyNumber': str})
S = D[D['goes_forward'] & (D['status'] == 'Shortlist')].copy()
print(f'Companies to score: {len(S)}')

clip = lambda x, lo, hi: max(lo, min(hi, x))

# 1. Revenue visibility (ESTIMATE): accounts don't split recurring revenue, so judge by business type
VIS_RULES = [
    (0.9, r'network operator|altnet|fibre network|data cent|satellite communications|cloud|managed .*networks|connectivity|mobile infrastructure|remote communications|offshore'),
    (0.7, r'business telecoms|broadband|phone|voice|hosting|managed it|iot'),
    (0.5, r'integrator|radio|equipment|tracking|secure|products|manufactur'),
    (0.35, r'contractor|civil|reinstatement|installation|build'),
]
SEGMENT_DEFAULT = {'Fibre and wired telecoms networks': 0.6, 'Wireless networks, towers and fixed wireless': 0.6,
                   'Satellite networks': 0.6, 'Other telecoms networks': 0.55,
                   'Data centres, data processing and hosting': 0.5,
                   'Building and maintaining telecoms and utility networks': 0.35}

def visibility(r):
    reason = str(r['relevance_reason']).lower()
    if r['relevance'] != 'UNSURE':
        for score, pattern in VIS_RULES:
            if re.search(pattern, reason):
                return score, 'ESTIMATE from business type'
    return SEGMENT_DEFAULT.get(r['segment'], 0.5), 'ESTIMATE from industry code only'

# 2. Strategy fit: thesis relevance
FIT = {'IN': 1.0, 'ADJACENT': 0.6, 'UNSURE': 0.4}

# 3. Size fit: sweet spot £20m-£100m turnover inside the £10m-£250m band
def size(t):
    if t < 20e6:
        return 0.5 + 0.5 * (t - 10e6) / 10e6
    if t <= 100e6:
        return 1.0
    return 1.0 - 0.4 * (t - 100e6) / 150e6

# 4. Margin quality: EBITDA margin level (0-30% scale) plus turnover trend as a stability proxy
def margin(r):
    if not r['numbers_ok']:
        return 0.0
    level = clip(r['ebitda_margin'] / 0.30, 0, 1)
    g = r['turnover_growth']
    trend = 0.5 if pd.isna(g) else (1.0 if -0.05 <= g <= 0.5 else 0.6 if g > 0.5 else clip(1 + g * 2, 0, 1))
    return 0.75 * level + 0.25 * trend

# 5. Data completeness: how far the numbers can be trusted
def completeness(r):
    if not r['numbers_ok']:
        return 0.0
    src = str(r['figures_source'])
    s = 1.0 if src == 'Tagged' else 0.5 if '£000s' in src else 0.6
    if str(r['ebitda_basis']).startswith('ESTIMATE'):
        s -= 0.2
    s -= 0.1 * sum(pd.isna(r[c]) for c in ('cash', 'net_assets', 'turnover_prior'))
    return clip(s, 0, 1)

# 6. Debt capacity (PROXY): positive net assets, cash cover and margin headroom
def debt(r):
    s = 0.4 if r['net_assets'] > 0 else 0.0
    if pd.notna(r['cash']) and r['turnover'] > 0:
        s += 0.3 * clip(r['cash'] / r['turnover'] / 0.15, 0, 1)
    if r['numbers_ok'] and r['ebitda_margin'] >= 0.10:
        s += 0.3
    elif r['numbers_ok'] and r['ebitda_margin'] >= 0.05:
        s += 0.15
    return s

vis = S.apply(visibility, axis=1)
S['s_revenue_visibility'] = [v[0] for v in vis]
S['revenue_visibility_basis'] = [v[1] for v in vis]
S['s_strategy_fit'] = S['relevance'].map(FIT)
S['s_size_fit'] = S['turnover'].apply(size)
S['s_margin_quality'] = S.apply(margin, axis=1)
S['s_data_completeness'] = S.apply(completeness, axis=1)
S['s_debt_capacity'] = S.apply(debt, axis=1)

for k, w in W.items():
    S[f'pts_{k}'] = (S[f's_{k}'] * w).round(1)
S['score'] = S[[f'pts_{k}' for k in W]].sum(axis=1).round(1)

ACCESS = {'Founder or family-owned': 'High: founder-owned, proprietary approach possible',
          'Likely sponsor-owned (check)': 'Medium: sponsor-owned, sale timing depends on hold year',
          'UK group, owner-managed': 'Medium: owned via a UK holding company',
          'Employee-owned (EOT)': 'Low: employee-owned, rarely for sale',
          'Unknown': 'Check: ownership not found'}
S['accessibility'] = S['ownership'].map(ACCESS).fillna('Check')

S = S.sort_values('score', ascending=False).reset_index(drop=True)
S.insert(0, 'rank', S.index + 1)
S['scored_on'] = datetime.date.today().isoformat()

cols = (['rank', 'CompanyName', 'CompanyNumber', 'score'] + [f'pts_{k}' for k in W] +
        ['accessibility', 'relevance', 'relevance_reason', 'segment', 'turnover', 'turnover_growth', 'ebitda',
         'ebitda_margin', 'ebitda_basis', 'figures_source', 'revenue_visibility_basis', 'data_flags',
         'ownership', 'owner_chain', 'owner_since_year', 'cash', 'net_assets', 'employees',
         'RegAddress.PostTown', 'accounts_filed', 'scored_on'])
S = S[[c for c in cols if c in S.columns]]

os.makedirs(f'{OUT}/rankings', exist_ok=True)
S.to_csv(f'{OUT}/ranking_latest.csv', index=False)
S.to_csv(f'{OUT}/rankings/ranking_{S["scored_on"].iloc[0]}.csv', index=False)   # dated copy, for change tracking later

pd.set_option('display.width', 250)
show = S.head(20).copy()
show['turnover'] = (show['turnover'] / 1e6).round(1).astype(str) + 'm'
show['ebitda_margin'] = (show['ebitda_margin'] * 100).round(0).astype(str) + '%'
print(show[['rank', 'CompanyName', 'score', 'relevance', 'turnover', 'ebitda_margin', 'accessibility']].to_string(index=False))
print('\nSaved ranking_latest.csv and a dated copy in data/outputs/rankings/')
