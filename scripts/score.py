"""Step 05: score and rank the cleaned shortlist.

Each company gets 0-1 on five criteria, multiplied by the weights in the criteria file (total 100).
Kept beside the score and never blended into it: accessibility (ownership) and confidence (how far the inputs can be trusted).
Method v3 (24 Nov 2026), after an analyst review: data quality moved out of the score into a confidence rating;
size scored on EBITDA; margin stability from multi-year history; only IN/ADJACENT companies ranked (sector gate);
"debt capacity" renamed "balance sheet resilience" and adjusted for interest cover where known.
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
GATE = C['sector_gate']['ranked_if_relevance_in']
check = S[~S['relevance'].isin(GATE)].copy()   # sector gate: an industry code alone is not enough to be ranked
S = S[S['relevance'].isin(GATE)].copy()
print(f'Companies to score: {len(S)} ({len(check)} more need a sector check first)')

HS_PATH = f'{OUT}/history_summary.csv'   # from history.py (deep-dived companies only)
HS = pd.read_csv(HS_PATH, dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(HS_PATH) else pd.DataFrame()

def hist(num, col):
    if num in HS.index and col in HS.columns and pd.notna(HS.at[num, col]):
        return HS.at[num, col]
    return None

clip = lambda x, lo, hi: max(lo, min(hi, x))

# 1. Revenue visibility (PROVISIONAL ESTIMATE): accounts don't split recurring revenue, so judge by business type
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
    for score, pattern in VIS_RULES:
        if re.search(pattern, reason):
            return score, 'Provisional: estimated from business type'
    return SEGMENT_DEFAULT.get(r['segment'], 0.5), 'Provisional: estimated from industry code only'

# 2. Strategy fit: thesis relevance (UNSURE companies are no longer ranked)
FIT = {'IN': 1.0, 'ADJACENT': 0.6}

# 3. Size fit: EBITDA, the base a buyer prices off (sweet spot £2m-£15m)
Z = C['size_ebitda_gbp']
def size(r):
    e = r['ebitda']
    if not r['numbers_ok'] or pd.isna(e) or e <= 0:
        return 0.0
    if e < Z['min_useful']:
        return 0.2
    if e < Z['sweet_spot_min']:
        return 0.2 + 0.8 * (e - Z['min_useful']) / (Z['sweet_spot_min'] - Z['min_useful'])
    if e <= Z['sweet_spot_max']:
        return 1.0
    return max(0.6, 1.0 - 0.4 * (e - Z['sweet_spot_max']) / (Z['upper_fade_to'] - Z['sweet_spot_max']))

# 4. Margin quality: EBITDA margin level (0-30% scale) and, where 3+ years exist, how much the margin swings
def margin(r):
    if not r['numbers_ok']:
        return 0.0, 'no reliable margin'
    level = clip(r['ebitda_margin'] / 0.30, 0, 1)
    swing = hist(r['CompanyNumber'], 'margin_swing_pp')
    if swing is None:
        return 0.7 * level + 0.3 * 0.5, 'stability not tested (fewer than 3 years read)'
    years = int(hist(r['CompanyNumber'], 'years_of_margin'))
    stability = clip(1 - (swing - 3) / 15, 0, 1)   # within 3 points = stable; 18+ points = unstable
    return 0.7 * level + 0.3 * stability, f'margin moved {swing:.0f} points across {years} years'

# 5. Balance sheet resilience (PROXY, not true debt capacity): net assets, cash cover, margin headroom, interest cover
def balance(r):
    s = 0.4 if r['net_assets'] > 0 else 0.0
    if pd.notna(r['cash']) and r['turnover'] > 0:
        s += 0.3 * clip(r['cash'] / r['turnover'] / 0.15, 0, 1)
    if r['numbers_ok'] and r['ebitda_margin'] >= 0.10:
        s += 0.3
    elif r['numbers_ok'] and r['ebitda_margin'] >= 0.05:
        s += 0.15
    cover = hist(r['CompanyNumber'], 'interest_cover')
    if cover is not None and cover < 3:
        s -= 0.3 * (3 - cover) / 3   # thin interest cover eats into room for new debt
    return clip(s, 0, 1)

# Confidence (not scored): how far the inputs can be trusted
def confidence(r):
    if not r['numbers_ok']:
        return 'Low', 'numbers flagged'
    src = str(r['figures_source'])
    c = 1.0 if src == 'Tagged' else 0.5 if '£000s' in src else 0.6
    reasons = [] if src == 'Tagged' else ['figures read from the accounts text']
    if str(r['ebitda_basis']).startswith('ESTIMATE'):
        c -= 0.2
        reasons.append('EBITDA estimated')
    missing = [lab for col, lab in (('cash', 'cash'), ('net_assets', 'net assets'), ('turnover_prior', 'prior-year sales')) if pd.isna(r[col])]
    c -= 0.1 * len(missing)
    if missing:
        reasons.append('missing ' + ', '.join(missing))
    if (hist(r['CompanyNumber'], 'years_of_sales') or 0) >= 3:
        c += 0.1
    else:
        c -= 0.1
        reasons.append('fewer than 3 years read')
    if r['relevance'] == 'ADJACENT':
        c -= 0.1
        reasons.append('only adjacent to the thesis')
    reasons.append('recurring revenue estimated')
    level = 'High' if c >= 0.95 else 'Medium' if c >= 0.6 else 'Low'
    return level, '; '.join(reasons)

vis = S.apply(visibility, axis=1)
S['s_revenue_visibility'] = [v[0] for v in vis]
S['revenue_visibility_basis'] = [v[1] for v in vis]
S['s_strategy_fit'] = S['relevance'].map(FIT)
S['s_size_fit'] = S.apply(size, axis=1)
mq = S.apply(margin, axis=1)
S['s_margin_quality'] = [m[0] for m in mq]
S['margin_stability_basis'] = [m[1] for m in mq]
S['s_balance_sheet'] = S.apply(balance, axis=1)
cf = S.apply(confidence, axis=1)
S['confidence'] = [c[0] for c in cf]
S['confidence_reasons'] = [c[1] for c in cf]

for k, w in W.items():
    S[f'pts_{k}'] = (S[f's_{k}'] * w).round(1)
S['score'] = S[[f'pts_{k}' for k in W]].sum(axis=1).round(1)

ACCESS = {'Founder or family-owned': 'High: founder-owned, proprietary approach possible',
          'Likely sponsor-owned (check)': 'Medium: sponsor-owned, sale timing depends on hold year',
          'UK group, owner-managed': 'Medium: owned via a UK holding company',
          'Employee-owned (EOT)': 'Low: employee-owned, rarely for sale',
          'Foreign parent, founder group': 'Low-Medium: UK arm of an overseas founder group, carve-out needed',
          'Sponsor-owned, recent entry': 'Low: sponsor bought in the last 2 years, unlikely to sell soon',
          'Unknown': 'Check: ownership not found'}
S['accessibility'] = S['ownership'].map(ACCESS).fillna('Check')

S = S.sort_values('score', ascending=False).reset_index(drop=True)
S.insert(0, 'rank', S.index + 1)
S['scored_on'] = datetime.date.today().isoformat()
S['method_version'] = C['method_version'].split(' ')[0]

cols = (['rank', 'CompanyName', 'CompanyNumber', 'score'] + [f'pts_{k}' for k in W] +
        ['confidence', 'confidence_reasons', 'margin_stability_basis', 'method_version',
         'accessibility', 'relevance', 'relevance_reason', 'segment', 'turnover', 'turnover_growth', 'ebitda',
         'ebitda_margin', 'ebitda_basis', 'figures_source', 'revenue_visibility_basis', 'data_flags',
         'ownership', 'owner_chain', 'owner_since_year', 'cash', 'net_assets', 'employees',
         'RegAddress.PostTown', 'accounts_filed', 'scored_on'])
S = S[[c for c in cols if c in S.columns]]

os.makedirs(f'{OUT}/rankings', exist_ok=True)
S.to_csv(f'{OUT}/ranking_latest.csv', index=False)
S.to_csv(f'{OUT}/rankings/ranking_{S["scored_on"].iloc[0]}.csv', index=False)   # dated copy, for change tracking
check[['CompanyName', 'CompanyNumber', 'relevance', 'relevance_reason', 'segment', 'turnover', 'ebitda_margin', 'ownership']].sort_values(
    'turnover', ascending=False).to_csv(f'{OUT}/sector_check.csv', index=False)   # not ranked until the trading business is confirmed

pd.set_option('display.width', 250)
show = S.head(20).copy()
show['turnover'] = (show['turnover'] / 1e6).round(1).astype(str) + 'm'
show['ebitda_margin'] = (show['ebitda_margin'] * 100).round(0).astype(str) + '%'
print(show[['rank', 'CompanyName', 'score', 'confidence', 'relevance', 'turnover', 'ebitda_margin', 'accessibility']].to_string(index=False))
print('\nSaved ranking_latest.csv, a dated copy in data/outputs/rankings/ and sector_check.csv')
