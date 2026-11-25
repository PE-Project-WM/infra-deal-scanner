"""Place every screened company in one sector (config/sectors.json).

A company's sector is its main activity. It comes from config/sector_map.csv where the company
has been checked; otherwise it falls back to the sector its Companies House industry code points to,
and is marked as such. Writes data/outputs/sectors.csv.
"""
import os, json, sys
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(f'{ROOT}/config/sectors.json'))['sectors']
C = json.load(open(f'{ROOT}/config/criteria_digital_infra.json'))
ids = {s['id'] for s in S}
code_to_sector = {code: s['id'] for s in S for code in s['sic_fallback']}
label_to_code = {v: k for k, v in C['segments'].items()}   # 'Satellite networks' -> '61300'

smap = pd.read_csv(f'{ROOT}/config/sector_map.csv', dtype={'CompanyNumber': str})
bad = sorted(set(smap['sector']) - ids)
if bad:
    sys.exit(f'sector_map.csv uses sectors not in config/sectors.json: {bad}')
dup = smap[smap['CompanyNumber'].duplicated()]['CompanyNumber'].tolist()
if dup:
    sys.exit(f'sector_map.csv places these companies twice: {dup}')
checked = smap.set_index('CompanyNumber')

cand = pd.read_csv(f'{ROOT}/data/outputs/candidates_clean.csv', dtype={'CompanyNumber': str})
rows = []
for _, r in cand.iterrows():
    num = r['CompanyNumber']
    if num in checked.index:
        rows.append((num, checked.at[num, 'sector'], 'checked', checked.at[num, 'basis']))
    else:
        code = label_to_code.get(r['segment'], '')
        sec = code_to_sector.get(code, '')
        rows.append((num, sec, 'industry code', f'Industry code {code} only, not yet checked' if sec else 'No sector'))
out = pd.DataFrame(rows, columns=['CompanyNumber', 'sector', 'sector_source', 'sector_basis'])
out.to_csv(f'{ROOT}/data/outputs/sectors.csv', index=False)

rank = pd.read_csv(f'{ROOT}/data/outputs/ranking_latest.csv', dtype={'CompanyNumber': str})
unplaced = rank[~rank['CompanyNumber'].isin(checked.index)]
for _, r in unplaced.iterrows():
    print(f'  Ranked but not yet in sector_map.csv (placed by industry code): {r["CompanyName"]} {r["CompanyNumber"]}')
print(f'Sectors: {len(out)} companies placed, {int((out.sector_source == "checked").sum())} checked, '
      f'{int((out.sector_source == "industry code").sum())} by industry code only')
print(out['sector'].value_counts().to_string())
