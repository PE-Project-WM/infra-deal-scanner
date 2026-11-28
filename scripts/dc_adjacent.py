"""Data-centre adjacent check (method v4.1): which companies serve data centres, and are they in the universe?

Investors rank data centres as the most attractive infrastructure sector (88% in the Roland Berger 2025 survey) while
fibre favourability fell from 42% to 29%, so companies that supply data centres matter even when they are not
data-centre owners. This step reads every set of accounts the pipeline has (history, deep-dive and OCR text) and
lists companies whose accounts link them to data centres, with the role the wording points to:
  operator      owns or runs data centres (colocation, hosting)
  connectivity  fibre, interconnect or network links into data centres
  power         electrical, high-voltage, UPS or generator work for data centres
  cooling       cooling, chillers, HVAC or mechanical work
  fit-out       design, build, fit-out, structured cabling or installation in data centres
  mention only  the accounts mention data centres without saying they serve them (as a cost, a risk, a customer type)
Hand checks in config/dc_adjacent.csv (CompanyNumber, role, note, source) override the reading.
Status: ranked / in the universe but not ranked (with the reason) / not in our data. Companies coded only under
electrical installation (43210), cooling and plumbing (43220) or building M&E (43290) are outside the six digital codes;
43210 is in the universe extension (STAGE=list in universe_extend.py), the other two are not.
Writes data/outputs/dc_adjacent.csv and data/outputs/dc_adjacent.md.
Skills: market-map-and-sourcing (who sits around the target market), deal-screening.
"""
import os, re, glob
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, CFG = f'{ROOT}/data/outputs', f'{ROOT}/config'
DC = re.compile(r'data[ -]?cent(?:re|er)s?|colocation|co-location|hyperscal\w*', re.I)
ROLES = [
    ('operator', re.compile(r'colocation|co-location|our data cent|operates? (?:\w+ )?data cent|data cent(?:re|er) (?:operator|campus|portfolio|facilit)|racks?\b|MW of (?:IT|capacity)', re.I)),
    ('power', re.compile(r'electrical|high[- ]voltage|\bHV\b|\bUPS\b|generator|switchgear|power (?:install|distribut|infrastructure)|substation', re.I)),
    ('cooling', re.compile(r'cooling|chiller|\bHVAC\b|mechanical (?:and|&) electrical|\bM&E\b|air[- ]condition', re.I)),
    ('fit-out', re.compile(r'fit[- ]out|structured cabling|cabling|design and build|construction of data|install\w* (?:in|for|at) data|white space', re.I)),
    ('connectivity', re.compile(r'fibre|fiber|dark fibre|interconnect|connectivity|network links?|leased lines?|wavelength|cross[- ]connect', re.I)),
]


def texts():
    seen = {}
    for d in ['history/text', 'deep_dive/text', 'ocr/text']:
        for f in glob.glob(f'{ROOT}/data/{d}/*'):
            num = os.path.basename(f).split('_')[0].split('.')[0]
            if num not in seen or os.path.basename(f) > os.path.basename(seen[num]):
                seen[num] = f
    return seen


def read(num, f):
    t = re.sub(r'\s+', ' ', open(f, errors='ignore').read())
    spans = [t[max(0, m.start() - 160):m.end() + 160] for m in DC.finditer(t)]
    if not spans:
        return None
    joined = ' '.join(spans)
    roles = [name for name, rx in ROLES if len(rx.findall(joined)) >= 2 or (name == 'operator' and rx.search(joined))]
    return {'CompanyNumber': num, 'mentions': len(spans), 'role': ', '.join(roles) if roles else 'mention only',
            'example': spans[0][:300].strip(), 'text_file': os.path.relpath(f, ROOT)}


def main():
    U = pd.read_csv(f'{ROOT}/data/inputs/financials_all.csv', dtype={'CompanyNumber': str}).drop_duplicates('CompanyNumber').set_index('CompanyNumber')
    C = pd.read_csv(f'{OUT}/candidates_clean.csv', dtype={'CompanyNumber': str}).drop_duplicates('CompanyNumber').set_index('CompanyNumber')
    R = pd.read_csv(f'{OUT}/ranking_latest.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber')
    H = pd.read_csv(f'{CFG}/dc_adjacent.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber') if os.path.exists(f'{CFG}/dc_adjacent.csv') else pd.DataFrame()
    rows = []
    for num, f in texts().items():
        r = read(num, f)
        if r is None:
            continue
        if num in H.index:
            r.update(role=H.at[num, 'role'], note=H.at[num, 'note'], source=H.at[num, 'source'], checked='by hand')
        else:
            r.update(note='', source=r['text_file'], checked='read from the accounts text')
        r['CompanyName'] = U['CompanyName'].get(num, C['CompanyName'].get(num, ''))
        r['segment'] = U['segment'].get(num, '')
        r['turnover'] = C['turnover'].get(num, U['turnover'].get(num))
        if num in R.index:
            r['status'], r['rank'] = 'Ranked', int(R.at[num, 'rank'])
        elif num in C.index:
            why = C.at[num, 'excluded_reason'] if pd.notna(C.at[num, 'excluded_reason']) else C.at[num, 'status']
            r['status'], r['rank'] = f"In the universe, not ranked: {why}", None
        else:
            r['status'], r['rank'] = 'In the universe, not ranked: outside the size band or not read', None
        rows.append(r)
    D = pd.DataFrame(rows)
    D = D[(D['role'] != 'mention only') | (D['checked'] == 'by hand')].copy() if len(D) else D
    D['ranked'] = D['status'].eq('Ranked')
    D['hand'] = D['checked'].eq('by hand')
    D = D.sort_values(['hand', 'ranked', 'mentions'], ascending=[False, False, False])
    cols = ['CompanyNumber', 'CompanyName', 'role', 'status', 'rank', 'segment', 'turnover', 'mentions', 'checked', 'note', 'source', 'example']
    D[cols].to_csv(f'{OUT}/dc_adjacent.csv', index=False)
    chk = D[D['checked'] == 'by hand']
    lines = ['# Data-centre adjacent check', '',
             'Investors rank data centres highest (88% favourable, Roland Berger 2025) while fibre fell from 42% to 29%. '
             'This lists companies whose accounts link them to data centres, and whether they are in the ranking.', '',
             f'Checked by hand: {len(chk)} companies, {int(chk["ranked"].sum())} of them ranked. A further {len(D) - len(chk)} mention data centres in the accounts '
             '(mostly operators and large groups); they are in data/outputs/dc_adjacent.csv with the role read from the wording, not yet checked.', '',
             '| Company | Role | Status | Note |', '|---|---|---|---|']
    for _, r in chk.iterrows():
        rk = f" (rank {int(r['rank'])})" if pd.notna(r['rank']) else ''
        lines.append(f"| {str(r['CompanyName']).title()} | {r['role']} | {r['status']}{rk} | {r['note']} |")
    lines += ['', 'Outside the universe: companies coded only as electrical installation (43210), cooling and plumbing (43220) or building M&E (43290) are not in the six digital codes.',
              '43210 is in the universe extension (waiting for the Companies House download); 43220 and 43290 are not, so cooling and M&E fit-out specialists are not covered yet.']
    open(f'{OUT}/dc_adjacent.md', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:60]))


if __name__ == '__main__':
    main()
