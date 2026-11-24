"""Build the public website (docs/index.html, served by GitHub Pages) from the latest update."""
import os, json, html, re as _re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U = json.load(open(f'{ROOT}/data/updates/latest.json'))
C = json.load(open(f'{ROOT}/config/criteria_digital_infra.json'))
fin = pd.read_csv(f'{ROOT}/data/inputs/financials_all.csv', dtype={'CompanyNumber': str})
clean = pd.read_csv(f'{ROOT}/data/outputs/candidates_clean.csv', dtype={'CompanyNumber': str})
IN_BAND = ['Shortlist', 'Watchlist (loss-making)', 'In band, EBITDA unknown']
funnel = [
    ('Companies registered under the six digital-infrastructure industry codes', 48467),
    ('Active, private, filing full accounts, three or more years old', len(fin)),
    ('Turnover between £10m and £250m', int(fin['status'].isin(IN_BAND).sum())),
    ('Left after ownership checks, duplicates and the thesis test', int(clean['goes_forward'].sum())),
    ('Profitable and scored', U['ranked']),
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
data = {'update': U, 'funnel': funnel, 'weights': weights, 'corr': corr}
payload = json.dumps(data, default=str).replace('</', '<\\/')

page = open(f'{ROOT}/scripts/site_template.html').read()   # layout and styles live in the template
open(f'{ROOT}/docs/index.html', 'w').write(page.replace('__DATA__', payload))
open(f'{ROOT}/docs/.nojekyll', 'w').write('')
print('Built docs/index.html')
