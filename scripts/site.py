"""Assemble the data for the public website, then build it with scripts/northing/build.py (docs/, served by GitHub Pages)."""
import os, json, html, re as _re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U = json.load(open(f'{ROOT}/data/updates/latest.json'))
C = json.load(open(f'{ROOT}/config/criteria_digital_infra.json'))
fin = pd.read_csv(f'{ROOT}/data/inputs/financials_all.csv', dtype={'CompanyNumber': str})
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ocr_apply import apply_ocr
fin = apply_ocr(fin)   # scanned accounts read by OCR count as read
scanned_unread = int(fin['status'].astype(str).str.startswith('PDF scan').sum())
scanned_ocr = int(fin['figures_source'].astype(str).str.startswith('OCR').sum())
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
plain = lambda r: _re.sub(r'\s*\((draft|web-checked|checked against the filing|via subsidiary)[^)]*\)', '', str(r)).strip()
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
sz_path = f'{ROOT}/data/outputs/size_check.csv'   # likely deal size (size_check.py)
SZ = pd.read_csv(sz_path, dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(sz_path) else None
size_of = lambda num: (SZ.at[num, 'size_flag'], SZ.at[num, 'size_basis']) if SZ is not None and num in SZ.index else ('', '')
SECTORS = json.load(open(f'{ROOT}/config/sectors.json'))['sectors']   # sector map (sectors.py)
SEC_NAME = {x['id']: x.get('short', x['name']) for x in SECTORS}
sec_path = f'{ROOT}/data/outputs/sectors.csv'
SECDF = pd.read_csv(sec_path, dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(sec_path) else pd.DataFrame(columns=['sector', 'sector_source'])
sec_of = lambda num: SECDF.at[num, 'sector'] if num in SECDF.index and isinstance(SECDF.at[num, 'sector'], str) else ''
all_ranked = [{'rank': int(r['rank']), 'company': nice(r['CompanyName']), 'what': plain(r['relevance_reason']),
               'sec': sec_of(r['CompanyNumber']),
               'sector': SEC_NAME.get(sec_of(r['CompanyNumber']), SEG.get(r['segment'], r['segment'])), 'score': float(r['score']), 'confidence': r.get('confidence'),
               'type': (lens_by_num.at[r['CompanyNumber'], 'deal_type'] if r['CompanyNumber'] in lens_by_num.index else ''),
               'access': str(r['accessibility']).split(':')[0], 'sales': float(r['turnover']),
               'margin': None if pd.isna(r['ebitda_margin']) else float(r['ebitda_margin']),
               'size': size_of(r['CompanyNumber'])[0], 'size_text': size_of(r['CompanyNumber'])[1]} for _, r in rk.iterrows()]
by_rank = {a['rank']: a for a in all_ranked}
for t in U['top10']:
    a = by_rank.get(int(t['rank']), {})
    t['size'], t['size_text'] = a.get('size', ''), a.get('size_text', '')
    t['sec'], t['sector'] = a.get('sec', ''), a.get('sector', '')
top_ranks = {int(t['rank']) for t in U['top10']}
sector_stats = []   # one entry per sector, screened or planned, built the same way for every sector
for x in SECTORS:
    placed = clean.assign(sec=clean['CompanyNumber'].map(sec_of))
    placed = placed[placed['sec'] == x['id']]
    rk_s = [a for a in all_ranked if a['sec'] == x['id']]
    med = lambda v: float(pd.Series(v).median()) if len(v) else None
    conf = {k: sum(1 for a in rk_s if a['confidence'] == k) for k in ('High', 'Medium', 'Low')}
    types = {}
    for a in rk_s:
        if a['type']:
            types[a['type']] = types.get(a['type'], 0) + 1
    sector_stats.append({**{k: x[k] for k in ('id', 'name', 'status', 'covers', 'excludes', 'measures_to_add')},
        'in_band': int(len(placed)), 'forward': int(placed['goes_forward'].sum()), 'ranked': len(rk_s),
        'checked': int((SECDF.loc[SECDF.index.isin(placed['CompanyNumber']), 'sector_source'] == 'checked').sum()) if len(placed) else 0,
        'in_top10': sum(1 for a in rk_s if a['rank'] in top_ranks),
        'best': ({'rank': rk_s[0]['rank'], 'company': rk_s[0]['company'], 'score': rk_s[0]['score']} if rk_s else None),
        'median_score': med([a['score'] for a in rk_s]), 'median_sales': med([a['sales'] for a in rk_s]),
        'median_margin': med([a['margin'] for a in rk_s if a['margin'] is not None]),
        'in_size_band': sum(1 for a in rk_s if a['size'] and not _re.search('above|below|not', a['size'], _re.I)),
        'conf': conf, 'types': types})
size_band = json.load(open(f'{ROOT}/config/valuation.json')).get('deal_size_band_gbp')
wl = lens[(lens['list'] != 'Ranked') & (lens['deal_type'] == 'Growth infrastructure') & lens['relevance'].isin(C['sector_gate']['ranked_if_relevance_in'])] if len(lens) else lens
growth_infra = [{'company': nice(r['CompanyName']), 'what': plain(r['relevance_reason']), 'sales': float(r['turnover']),
                 'reason': r['deal_type_reason']} for _, r in wl.sort_values('turnover', ascending=False).iterrows()]
sc_path = f'{ROOT}/data/outputs/sector_check.csv'
sector_check = len(pd.read_csv(sc_path)) if os.path.exists(sc_path) else 0
val_path = f'{ROOT}/data/outputs/valuation_latest.json'   # price check (valuation.py)
val = json.load(open(val_path)) if os.path.exists(val_path) else None
if val:
    vby = {c['rank']: c for c in val['companies']}
    for t in U['top10']:
        t['price'] = vby.get(t['rank'])
    for c in val['companies']:
        c['company'] = nice(c['CompanyName'])
factor_avg = {k: {'all': float(rank_df[f'pts_{k}'].mean()), 'top': float(rank_df.loc[rank_df.index <= 10, f'pts_{k}'].mean())}
              for k in weights if f'pts_{k}' in rank_df}   # average points per scoring factor (overview)
fc = pd.read_csv(f'{ROOT}/config/figure_corrections.csv', dtype={'CompanyNumber': str})
vf = f'{ROOT}/data/ocr/verified.csv'
quality = {'corrected_filings': int(fc[['CompanyNumber', 'accounts_filed']].drop_duplicates().shape[0]),
           'checked_against_filing': int(len(pd.read_csv(vf))) if os.path.exists(vf) else 0,
           'sector_checked': int((SECDF['sector_source'] == 'checked').sum()) if len(SECDF) else 0,
           'sector_placed': int(len(SECDF))}
data = {'update': U, 'funnel': funnel, 'weights': weights, 'corr': corr, 'all': all_ranked, 'growth_infra': growth_infra,
        'sector_check': sector_check, 'scanned': scanned_unread, 'scanned_ocr': scanned_ocr, 'universe': len(fin), 'val': val, 'size_band': size_band, 'sectors': sector_stats, 'factor_avg': factor_avg, 'quality': quality}
excluded = pd.read_csv(f'{ROOT}/data/outputs/excluded_log.csv', dtype={'CompanyNumber': str})
sig_path = f'{ROOT}/data/outputs/signals.json'   # exit and refinancing signals (signals.py)
signals = json.load(open(sig_path))['signals'] if os.path.exists(sig_path) else []
from northing.build import build   # the Northing website and its data files (scripts/northing/)
build(dict(data=data, U=U, C=C, rk=rk, prof=prof, lens_by_num=lens_by_num, SZ=SZ, SECDF=SECDF, SECTORS=SECTORS,
           sector_stats=sector_stats, val=val, corr=corr, clean=clean, excluded=excluded, weights=weights,
           nice=nice, plain=plain, signals=signals))
