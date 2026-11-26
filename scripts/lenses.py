"""Step 06 (Version 2): deal-type buckets and the demand-driver correlation map.

Deal type: which kind of fund each company suits (Steady compounder, Fixable dip, High-growth).
Demand driver: what the company's revenue mainly depends on, grouped into macro factors, so we can
see whether the top 10 is really ten bets or two or three.
Skills: deal-screening (bucket rubric), red-flag-register (correlation test: one cause = one exposure).
Labels are kept beside the score and never change it.
"""
import os, re, json, datetime
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, CFG = f'{ROOT}/data/outputs', f'{ROOT}/config'
L = json.load(open(f'{CFG}/demand_drivers.json'))
T, DRIVERS, CT = L['deal_types'], L['drivers'], L['correlation_test']
OV = pd.read_csv(f'{CFG}/demand_driver_overrides.csv', dtype={'CompanyNumber': str}).fillna('').set_index('CompanyNumber')
pct = lambda x: f'{x * 100:.0f}%'

R = pd.read_csv(f'{OUT}/ranking_latest.csv', dtype={'CompanyNumber': str})
C = pd.read_csv(f'{OUT}/candidates_clean.csv', dtype={'CompanyNumber': str})
Wl = C[C['goes_forward'] & (C['status'] == 'Watchlist (loss-making)') & ~C['CompanyNumber'].isin(R['CompanyNumber'])].copy()   # EBITDA rules can lift a company into the ranking
R['list'], Wl['list'], Wl['rank'] = 'Ranked', 'Watchlist (loss-making)', pd.NA
from settings import W as _W
R['visibility'] = R['pts_revenue_visibility'] / _W['revenue_visibility']
Wl['visibility'] = pd.NA
keep = ['rank', 'list', 'CompanyName', 'CompanyNumber', 'score', 'relevance', 'relevance_reason', 'segment',
        'turnover', 'turnover_growth', 'ebitda_margin', 'visibility', 'revenue_visibility_basis', 'data_flags']
A = pd.concat([R.reindex(columns=keep), Wl.reindex(columns=keep)], ignore_index=True)
pct = lambda x: f'{x * 100:.0f}%'

HS_PATH = f'{OUT}/history_summary.csv'   # multi-year history for deep-dived companies (history.py)
HS = pd.read_csv(HS_PATH, dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(HS_PATH) else pd.DataFrame()
def hist(num, col):
    if num in HS.index and col in HS.columns and pd.notna(HS.at[num, col]):
        return HS.at[num, col]
    return None

def deal_type(r):
    m, v, num = r['ebitda_margin'], r['visibility'], r['CompanyNumber']
    fix = str(OV.at[num, 'fix']).strip() if num in OV.index and 'fix' in OV.columns else ''
    cagr, swing = hist(num, 'sales_cagr'), hist(num, 'margin_swing_pp')
    if cagr is not None:   # growth over several years beats a single year
        g, gtext = cagr, f"sales up {pct(cagr)} a year over {int(hist(num, 'years_of_sales'))} years"
        if cagr < 0:
            gtext = f"sales down {pct(-cagr)} a year over {int(hist(num, 'years_of_sales'))} years"
    else:
        g = r['turnover_growth']
        gtext = 'growth not known' if pd.isna(g) else (f"sales up {pct(g)} in one year (only one year read)" if g >= 0 else f"sales down {pct(-g)} in one year (only one year read)")
    if isinstance(r['data_flags'], str) and r['data_flags'].strip():
        return 'Numbers to check', f"flagged numbers ({r['data_flags']})"
    if r['list'] != 'Ranked':
        if pd.notna(g) and g >= T['growth_infra_min_growth']:
            return 'Growth infrastructure', f"loss-making (EBITDA margin {pct(m)}) while {gtext}"
        return 'Under pressure', f"loss-making (EBITDA margin {pct(m)}), {gtext}; no fix identified yet"
    high = T['high_growth_min_cagr'] if cagr is not None else T['high_growth_min_growth']
    if pd.notna(g) and g >= high:
        return 'High-growth', f"{gtext}, margin {pct(m)}"
    weak = (pd.notna(g) and g <= T['dip_max_growth']) or m < T['dip_max_margin']
    if weak or (swing is not None and r['turnover_growth'] <= T['dip_max_growth']):
        why = gtext if (pd.notna(g) and g <= T['dip_max_growth']) else f"thin EBITDA margin ({pct(m)})"
        if fix:
            return 'Fixable dip', f"{why}; fix identified: {fix}"
        return 'Under pressure', f"{why}; no specific fix identified yet"
    src = 'from the accounts' if str(r.get('revenue_visibility_basis', '')).startswith('From the accounts') else 'estimated'
    steady_margin = swing is None or swing <= T['compounder_max_margin_swing_pp']
    if v >= T['compounder_min_visibility'] and m >= T['compounder_min_margin'] and (pd.isna(g) or g >= T['compounder_min_growth']) and steady_margin:
        return 'Steady compounder', (f"recurring-type revenue ({src}), margin {pct(m)}, {gtext}" +
                                     (f", margin within {swing:.0f} points over the years read" if swing is not None else ", margin stability not yet tested"))
    if not steady_margin:
        return 'Between buckets', f"margin swung {swing:.0f} points over the years read, too uneven for a steady compounder"
    if v < T['compounder_min_visibility']:
        return 'Between buckets', f"margin {pct(m)} but project-based revenue ({src})"
    return 'Between buckets', f"recurring-type revenue ({src}) but margin only {pct(m)}"

SP_PATH = f'{CFG}/demand_driver_split.csv'   # revenue split across drivers, read from the accounts where possible
SP = pd.read_csv(SP_PATH, dtype={'CompanyNumber': str}) if os.path.exists(SP_PATH) else pd.DataFrame(columns=['CompanyNumber', 'driver', 'share', 'basis'])
assert (SP.groupby('CompanyNumber')['share'].sum().round(3) == 1).all(), 'Driver shares must add up to 1 for each company'

def driver(r):
    sp = SP[SP['CompanyNumber'] == r['CompanyNumber']].sort_values('share', ascending=False)
    if len(sp):
        return sp['driver'].iloc[0], sp['driver'].iloc[1] if len(sp) > 1 else '', 'Split: ' + sp['basis'].iloc[0]
    if r['CompanyNumber'] in OV.index:
        o = OV.loc[r['CompanyNumber']]
        return o['demand_driver'], o['second_driver'], o['basis']
    reason = '' if str(r['relevance_reason']).startswith('Not yet reviewed') else str(r['relevance_reason']).lower()
    for text, src in ((reason, 'business description'), (str(r['segment']).lower(), 'industry code only')):
        for pattern, d in L['driver_rules']:
            if text and re.search(pattern, text):
                return d, '', f'Rule from {src} (confirm)'
    return 'Unknown', '', 'No rule matched: needs a look'

A[['deal_type', 'deal_type_reason']] = A.apply(lambda r: pd.Series(deal_type(r)), axis=1)
A['fund_fit'] = A['deal_type'].map(T['fund_fit'])
A[['demand_driver', 'second_driver', 'driver_basis']] = A.apply(lambda r: pd.Series(driver(r)), axis=1)
bad = set(A['demand_driver']) - set(DRIVERS)
assert not bad, f'Drivers missing from config/demand_drivers.json: {bad}'
A['macro_factor'] = A['demand_driver'].map(DRIVERS)

def split(r):
    """[(driver, share)]: from config/demand_driver_split.csv, else 70/30 if a second driver is named, else 100%."""
    sp = SP[SP['CompanyNumber'] == r['CompanyNumber']]
    if len(sp):
        return [(d, float(x)) for d, x in zip(sp['driver'], sp['share'])], 'estimated split from the accounts'
    if isinstance(r['second_driver'], str) and r['second_driver']:
        return [(r['demand_driver'], 0.7), (r['second_driver'], 0.3)], 'assumed 70/30 split'
    return [(r['demand_driver'], 1.0)], 'single driver'
sp_all = A.apply(split, axis=1)
A['split'] = [x[0] for x in sp_all]
A['split_basis'] = [x[1] for x in sp_all]
bad = {d for sp in A['split'] for d, _ in sp} - set(DRIVERS)
assert not bad, f'Drivers missing from config/demand_drivers.json: {bad}'
A['driver_split'] = A['split'].map(lambda sp: '; '.join(f'{d} {x:.0%}' for d, x in sorted(sp, key=lambda t: -t[1])))
A['labelled_on'] = datetime.date.today().isoformat()
A.drop(columns=['visibility', 'split']).to_csv(f'{OUT}/lenses_latest.csv', index=False)

def nice(s):   # same tidy-up as compare.py
    stop = {'THE', 'AND', 'FOR', 'OF', 'LTD'}
    t = ' '.join(w if (len(w.strip('()')) <= 3 and w.strip('()').isalpha() and w.strip('()') not in stop) else w.title() for w in str(s).split())
    t = re.sub(r'\s+(Limited|Ltd\.?|Plc\.?)$', '', t.replace("'S", "'s"))
    t = re.sub(r'\bUk\b', 'UK', t)
    return re.sub(r'\(([A-Za-z]{2,4})\)', lambda m: '(' + m.group(1).upper() + ')', t)
# Correlation test on the top N (red-flag-register, step 5)
def concentration(df):
    """Exposure of the list to each macro factor, weighting each company by the share of its sales tied to that factor."""
    rows = [(d, DRIVERS[d], x, r['CompanyName']) for _, r in df.iterrows() for d, x in r['split']]
    E = pd.DataFrame(rows, columns=['driver', 'factor', 'x', 'company'])
    expo = E.groupby('factor')['x'].sum().sort_values(ascending=False)
    share = expo / len(df)
    hhi = float((share ** 2).sum())
    factors = []
    for f, s in share.items():
        flag = 'red' if s >= CT['red_share'] else 'amber' if s >= CT['amber_share'] else 'green'
        g = E[E['factor'] == f].groupby('company', sort=False)['x'].sum().sort_values(ascending=False)
        factors.append({'factor': f, 'share': round(float(s), 2), 'exposure': round(float(expo[f]), 1),
                        'count': int((g >= 0.5).sum()), 'flag': flag,
                        'companies': [f"{nice(n)} ({x:.0%})" if x < 0.999 else nice(n) for n, x in g.items()],
                        'drivers': sorted(E.loc[E['factor'] == f, 'driver'].unique().tolist())})
    worst = 'red' if any(x['flag'] == 'red' for x in factors) else 'amber' if any(x['flag'] == 'amber' for x in factors) else 'green'
    return {'n': len(df), 'effective_bets': round(1 / hhi, 1), 'flag': worst, 'factors': factors}

N = CT['top_n']
top = A[A['list'] == 'Ranked'].sort_values('rank').head(N)
corr = {'date': A['labelled_on'].iloc[0], 'top_n': concentration(top), 'top_20': concentration(A[A['list'] == 'Ranked'].sort_values('rank').head(20)),
        'top10': [{'rank': int(r['rank']), 'deal_type': r['deal_type'], 'deal_type_reason': r['deal_type_reason'], 'fund_fit': r['fund_fit'],
                   'demand_driver': r['demand_driver'], 'second_driver': r['second_driver'], 'macro_factor': r['macro_factor'],
                   'driver_basis': r['driver_basis'], 'driver_split': r['driver_split'], 'split_basis': r['split_basis'],
                   'split': [{'driver': d, 'share': x} for d, x in sorted(r['split'], key=lambda t: -t[1])]} for _, r in top.iterrows()],
        'deal_type_counts': {'ranked': A[A['list'] == 'Ranked']['deal_type'].value_counts().to_dict(),
                             'watchlist': A[A['list'] != 'Ranked']['deal_type'].value_counts().to_dict()},
        'thresholds': CT}
c = corr['top_n']
big = [f for f in c['factors'] if f['flag'] != 'green']
def lower_first(x):   # keep acronyms such as SME in capitals
    return x if x[:3].isupper() else x[0].lower() + x[1:]
parts = ', '.join(f"{f['share']:.0%} of it depends on {lower_first(f['factor'])}" for f in big)
corr['headline'] = f"The top {N} is about {c['effective_bets']:.0f} independent bets, not {N}" + (f": {parts}" if big else '')
json.dump(corr, open(f'{OUT}/correlation_latest.json', 'w'), indent=1, default=str)

# Markdown report (also appended to the weekly issue)
md = [f"## Deal types and correlation ({corr['date']})", '', f"**{corr['headline']}.**", '',
      f"Correlation flag for the top {N}: **{c['flag'].upper()}** (amber when {CT['amber_share']:.0%} of the top {N}, weighted by each company's share of sales, depends on one macro factor; red at {CT['red_share']:.0%}).", '',
      '| Rank | Company | Deal type | Suits | Sales depend on | Main macro factor |', '|---|---|---|---|---|---|']
md += [f"| {t['rank']} | {nice(n)} | {t['deal_type']} | {t['fund_fit']} | {t['driver_split']} | {t['macro_factor']} |"
       for t, n in zip(corr['top10'], top['CompanyName'])]
md += ['', '**Macro factors in the top 10**', '']
md += [f"- {f['factor']}: {f['share']:.0%} of the top {N} ({f['flag']}), {', '.join(f['companies'])}" for f in c['factors']]
md += ['', f"Top 20: about {corr['top_20']['effective_bets']:.0f} independent bets (flag {corr['top_20']['flag']}).", '',
       'Deal types across all ranked companies: ' + ', '.join(f'{k} {v}' for k, v in corr['deal_type_counts']['ranked'].items()) + '.',
       f"Watchlist ({sum(corr['deal_type_counts']['watchlist'].values())} loss-making companies): " + ', '.join(f'{k} {v}' for k, v in corr['deal_type_counts']['watchlist'].items()) + '.', '',
       '_Splits for the top 10 are estimated from the accounts and web checks (config/demand_driver_split.csv); companies with two named drivers are assumed 70/30; the rest come from judgement or rules and should be confirmed._']
open(f'{OUT}/correlation_report.md', 'w').write('\n'.join(md) + '\n')
print('\n'.join(md))
print('\nSaved lenses_latest.csv, correlation_latest.json and correlation_report.md in data/outputs/')
