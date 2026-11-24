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

R = pd.read_csv(f'{OUT}/ranking_latest.csv', dtype={'CompanyNumber': str})
C = pd.read_csv(f'{OUT}/candidates_clean.csv', dtype={'CompanyNumber': str})
Wl = C[C['goes_forward'] & (C['status'] == 'Watchlist (loss-making)')].copy()
R['list'], Wl['list'], Wl['rank'] = 'Ranked', 'Watchlist (loss-making)', pd.NA
R['visibility'] = R['pts_revenue_visibility'] / json.load(open(f'{CFG}/criteria_digital_infra.json'))['scoring_weights']['revenue_visibility']
Wl['visibility'] = pd.NA
keep = ['rank', 'list', 'CompanyName', 'CompanyNumber', 'score', 'relevance', 'relevance_reason', 'segment',
        'turnover', 'turnover_growth', 'ebitda_margin', 'visibility', 'data_flags']
A = pd.concat([R.reindex(columns=keep), Wl.reindex(columns=keep)], ignore_index=True)
pct = lambda x: f'{x * 100:.0f}%'

def deal_type(r):
    g, m, v = r['turnover_growth'], r['ebitda_margin'], r['visibility']
    if isinstance(r['data_flags'], str) and r['data_flags'].strip():
        return 'Numbers to check', f"flagged numbers ({r['data_flags']})"
    if r['list'] != 'Ranked':
        return 'Fixable dip', f"loss-making (EBITDA margin {pct(m)}); the fix still has to be identified"
    if pd.notna(g) and g >= T['high_growth_min_growth']:
        return 'High-growth', f"turnover up {pct(g)} in the latest year, margin {pct(m)}"
    if pd.notna(g) and g <= T['dip_max_growth']:
        return 'Fixable dip', f"turnover down {pct(-g)} in the latest year; check whether it is temporary"
    if m < T['dip_max_margin']:
        return 'Fixable dip', f"thin EBITDA margin ({pct(m)}); check for a clear lever"
    if v >= T['compounder_min_visibility'] and m >= T['compounder_min_margin'] and (pd.isna(g) or g >= T['compounder_min_growth']):
        return 'Steady compounder', f"recurring-type revenue (visibility {v:.1f}), margin {pct(m)}, turnover {'+' if g >= 0 else ''}{pct(g)}"
    if v < T['compounder_min_visibility']:
        return 'Between buckets', f"stable numbers (margin {pct(m)}) but project-based revenue (visibility {v:.2f})"
    return 'Between buckets', f"recurring-type revenue but margin only {pct(m)}"

def driver(r):
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
A['labelled_on'] = datetime.date.today().isoformat()
A.drop(columns=['visibility']).to_csv(f'{OUT}/lenses_latest.csv', index=False)

def nice(s):   # same tidy-up as compare.py
    stop = {'THE', 'AND', 'FOR', 'OF', 'LTD'}
    t = ' '.join(w if (len(w.strip('()')) <= 3 and w.strip('()').isalpha() and w.strip('()') not in stop) else w.title() for w in str(s).split())
    t = re.sub(r'\s+(Limited|Ltd\.?|Plc\.?)$', '', t.replace("'S", "'s"))
    t = re.sub(r'\bUk\b', 'UK', t)
    return re.sub(r'\(([A-Za-z]{2,4})\)', lambda m: '(' + m.group(1).upper() + ')', t)
# Correlation test on the top N (red-flag-register, step 5)
def concentration(df):
    share = df['macro_factor'].value_counts(normalize=True)
    hhi = float((share ** 2).sum())
    factors = []
    for f, s in share.items():
        flag = 'red' if s >= CT['red_share'] else 'amber' if s >= CT['amber_share'] else 'green'
        names = [nice(n) for n in df.loc[df['macro_factor'] == f, 'CompanyName']]
        factors.append({'factor': f, 'share': round(float(s), 2), 'count': len(names), 'flag': flag, 'companies': names,
                        'drivers': sorted(df.loc[df['macro_factor'] == f, 'demand_driver'].unique().tolist())})
    worst = 'red' if any(x['flag'] == 'red' for x in factors) else 'amber' if any(x['flag'] == 'amber' for x in factors) else 'green'
    return {'n': len(df), 'effective_bets': round(1 / hhi, 1), 'flag': worst, 'factors': factors}

N = CT['top_n']
top = A[A['list'] == 'Ranked'].sort_values('rank').head(N)
corr = {'date': A['labelled_on'].iloc[0], 'top_n': concentration(top), 'top_20': concentration(A[A['list'] == 'Ranked'].sort_values('rank').head(20)),
        'top10': [{'rank': int(r['rank']), 'deal_type': r['deal_type'], 'deal_type_reason': r['deal_type_reason'], 'fund_fit': r['fund_fit'],
                   'demand_driver': r['demand_driver'], 'second_driver': r['second_driver'], 'macro_factor': r['macro_factor'],
                   'driver_basis': r['driver_basis']} for _, r in top.iterrows()],
        'deal_type_counts': {'ranked': A[A['list'] == 'Ranked']['deal_type'].value_counts().to_dict(),
                             'watchlist': A[A['list'] != 'Ranked']['deal_type'].value_counts().to_dict()},
        'thresholds': CT}
c = corr['top_n']
big = [f for f in c['factors'] if f['flag'] != 'green']
corr['headline'] = (f"The top {N} is about {c['effective_bets']:.0f} independent bets, not {N}" +
                    (f": {', '.join(f'{f['count']} depend on {f['factor'] if f['factor'][:3].isupper() else f['factor'][0].lower() + f['factor'][1:]}' for f in big)}" if big else ''))
json.dump(corr, open(f'{OUT}/correlation_latest.json', 'w'), indent=1, default=str)

# Markdown report (also appended to the weekly issue)
md = [f"## Deal types and correlation ({corr['date']})", '', f"**{corr['headline']}.**", '',
      f"Correlation flag for the top {N}: **{c['flag'].upper()}** (amber at {CT['amber_share']:.0%} of the top {N} on one macro factor, red at {CT['red_share']:.0%}).", '',
      '| Rank | Company | Deal type | Suits | Main demand driver | Macro factor |', '|---|---|---|---|---|---|']
md += [f"| {t['rank']} | {nice(n)} | {t['deal_type']} | {t['fund_fit']} | {t['demand_driver']} | {t['macro_factor']} |"
       for t, n in zip(corr['top10'], top['CompanyName'])]
md += ['', '**Macro factors in the top 10**', '']
md += [f"- {f['factor']}: {f['count']} of {N} ({f['flag']}), {', '.join(nice(x) for x in f['companies'])}" for f in c['factors']]
md += ['', f"Top 20: about {corr['top_20']['effective_bets']:.0f} independent bets (flag {corr['top_20']['flag']}).", '',
       'Deal types across all ranked companies: ' + ', '.join(f'{k} {v}' for k, v in corr['deal_type_counts']['ranked'].items()) + '.',
       f"Watchlist ({sum(corr['deal_type_counts']['watchlist'].values())} loss-making companies): all labelled Fixable dip until a fix is identified.", '',
       '_Drivers for the top 20 are judgement calls from business descriptions (see config/demand_driver_overrides.csv); the rest come from rules and should be confirmed. Growth is one year only._']
open(f'{OUT}/correlation_report.md', 'w').write('\n'.join(md) + '\n')
print('\n'.join(md))
print('\nSaved lenses_latest.csv, correlation_latest.json and correlation_report.md in data/outputs/')
