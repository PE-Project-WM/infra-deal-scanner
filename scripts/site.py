"""Build the public website (docs/index.html, served by GitHub Pages) from the latest update."""
import os, json, html, re as _re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U = json.load(open(f'{ROOT}/data/updates/latest.json'))
C = json.load(open(f'{ROOT}/config/criteria_digital_infra.json'))
fin = pd.read_csv(f'{ROOT}/data/inputs/financials_all.csv', dtype={'CompanyNumber': str})
clean = pd.read_csv(f'{ROOT}/data/outputs/candidates_clean.csv', dtype={'CompanyNumber': str})
IN_BAND = ['Shortlist', 'Watchlist (loss-making)', 'In band, EBITDA unknown']
shortlist = clean[clean['goes_forward'] & (clean['status'] == 'Shortlist')]
funnel = [
    ('Companies House records under six digital-infrastructure industry codes', 48467),
    ('Active, private, filing full accounts, three or more years old', len(fin)),
    ('Sales between £10m and £250m', int(fin['status'].isin(IN_BAND).sum())),
    ('Left after ownership checks, duplicates and clearly off-topic firms', int(clean['goes_forward'].sum())),
    ('Profitable', len(shortlist)),
    ('Confirmed to trade in the sector, and ranked', U['ranked']),
]
weights = C['scoring_weights']
rank_df = pd.read_csv(f'{ROOT}/data/outputs/ranking_latest.csv', dtype={'CompanyNumber': str}).set_index('rank')
plain = lambda r: _re.sub(r'\s*\((draft|web-checked|via subsidiary)[^)]*\)', '', str(r)).strip()
for t in U['top10']:   # plain one-line description and growth for each company
    if t['rank'] in rank_df.index:
        row = rank_df.loc[t['rank']]
        t['what'] = plain(row['relevance_reason'])
        t['growth'] = None if pd.isna(row['turnover_growth']) else float(row['turnover_growth'])
corr_path = f'{ROOT}/data/outputs/correlation_latest.json'   # Version 2 lenses (scripts/lenses.py)
corr = json.load(open(corr_path)) if os.path.exists(corr_path) else None
if corr:
    by_rank = {t['rank']: t for t in corr['top10']}
    for t in U['top10']:
        t['lens'] = by_rank.get(t['rank'])
    explain = json.load(open(f'{ROOT}/config/demand_drivers.json')).get('factor_explainers', {})
    for f in corr['top_n']['factors']:
        f['explain'] = explain.get(f['factor'], '')
prof_path = f'{ROOT}/data/outputs/profiles.json'   # why on the list / what to check (profiles.py)
prof = json.load(open(prof_path)) if os.path.exists(prof_path) else {}
lens_path = f'{ROOT}/data/outputs/lenses_latest.csv'
lens = pd.read_csv(lens_path, dtype={'CompanyNumber': str}) if os.path.exists(lens_path) else pd.DataFrame(columns=['CompanyNumber', 'list'])
lens_by_num = lens.set_index('CompanyNumber') if len(lens) else lens
rk = rank_df.reset_index()
for t in U['top10']:
    num = rk.loc[rk['rank'] == t['rank'], 'CompanyNumber']
    if len(num) and num.iloc[0] in prof:
        t['profile'] = prof[num.iloc[0]]
SEG = {'Fibre and wired telecoms networks': 'Fibre', 'Wireless networks, towers and fixed wireless': 'Wireless',
       'Satellite networks': 'Satellite', 'Other telecoms networks': 'Telecoms services',
       'Data centres, data processing and hosting': 'Data centres and hosting',
       'Building and maintaining telecoms and utility networks': 'Network build'}
def nice(n):   # same tidy-up as compare.py
    stop = {'THE', 'AND', 'FOR', 'OF', 'LTD'}
    t = ' '.join(w if (len(w.strip('()')) <= 3 and w.strip('()').isalpha() and w.strip('()') not in stop) else w.title() for w in str(n).split())
    t = _re.sub(r'\s+(Limited|Ltd\.?|Plc\.?)$', '', t.replace("'S", "'s"))
    t = _re.sub(r'\bUk\b', 'UK', t)
    return _re.sub(r'\(([A-Za-z]{2,4})\)', lambda m: '(' + m.group(1).upper() + ')', t)
all_ranked = [{'rank': int(r['rank']), 'company': nice(r['CompanyName']), 'what': plain(r['relevance_reason']),
               'sector': SEG.get(r['segment'], r['segment']), 'score': float(r['score']), 'confidence': r.get('confidence'),
               'type': (lens_by_num.at[r['CompanyNumber'], 'deal_type'] if r['CompanyNumber'] in lens_by_num.index else ''),
               'access': str(r['accessibility']).split(':')[0], 'sales': float(r['turnover']),
               'margin': None if pd.isna(r['ebitda_margin']) else float(r['ebitda_margin'])} for _, r in rk.iterrows()]
wl = lens[(lens['list'] != 'Ranked') & (lens['deal_type'] == 'Growth infrastructure') & lens['relevance'].isin(C['sector_gate']['ranked_if_relevance_in'])] if len(lens) else lens
growth_infra = [{'company': nice(r['CompanyName']), 'what': plain(r['relevance_reason']), 'sales': float(r['turnover']),
                 'reason': r['deal_type_reason']} for _, r in wl.sort_values('turnover', ascending=False).iterrows()]
sc_path = f'{ROOT}/data/outputs/sector_check.csv'
sector_check = len(pd.read_csv(sc_path)) if os.path.exists(sc_path) else 0
data = {'update': U, 'funnel': funnel, 'weights': weights, 'corr': corr, 'all': all_ranked, 'growth_infra': growth_infra,
        'sector_check': sector_check, 'scanned': 842, 'universe': len(fin)}
payload = json.dumps(data, default=str).replace('</', '<\\/')

page = open(f'{ROOT}/scripts/site_template.html').read()   # layout and styles live in the template
open(f'{ROOT}/docs/index.html', 'w').write(page.replace('__DATA__', payload))
open(f'{ROOT}/docs/.nojekyll', 'w').write('')
print('Built docs/index.html')
