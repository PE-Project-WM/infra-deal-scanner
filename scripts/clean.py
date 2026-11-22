"""Step 04: clean the in-band candidates before scoring.

Flags implausible numbers, looks up ownership on the Companies House PSC register,
merges duplicates and applies the relevance review in config/relevance_draft.csv.
Skills: market-map-and-sourcing, deal-screening.
Run by GitHub Actions (.github/workflows/clean.yml). Needs the CH_API_KEY secret.
"""
import os, re, time, requests
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INP, OUT, CFG = f'{ROOT}/data/inputs', f'{ROOT}/data/outputs', f'{ROOT}/config'
os.makedirs(OUT, exist_ok=True)
KEY = os.environ['CH_API_KEY'].strip()

F = pd.read_csv(f'{INP}/financials_all.csv', dtype={'CompanyNumber': str})
IN_BAND = ['Shortlist', 'Watchlist (loss-making)', 'In band, EBITDA unknown']
D = F[F['status'].isin(IN_BAND)].copy().reset_index(drop=True)
print(f'Candidates to clean: {len(D)}')
print(D['status'].value_counts().to_string())


API = 'https://api.company-information.service.gov.uk'
S = requests.Session()
S.auth = (KEY, '')
_last = [0.0]
def get(url, **kw):
    r = None
    for _ in range(5):
        wait = 0.55 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = S.get(url, timeout=60, **kw)
        except requests.RequestException:
            time.sleep(5)
            continue
        if r.status_code == 429:
            time.sleep(60)
            continue
        return r
    return r

def data_flags(r):
    f = []
    m, g = r['ebitda_margin'], r['turnover_growth']
    if pd.notna(m) and m > 0.6:
        f.append('EBITDA margin above 60%')
    if pd.notna(r['ebitda']) and pd.notna(r['turnover']) and r['ebitda'] > r['turnover']:
        f.append('EBITDA bigger than turnover')
    if pd.notna(g) and abs(g) > 3:
        f.append('turnover growth above 300%')
    if pd.notna(m) and 0 < m < 0.005:
        f.append('EBITDA margin under 0.5% (check scale)')
    return '; '.join(f)

D['data_flags'] = D.apply(data_flags, axis=1)
D['numbers_ok'] = D['data_flags'] == ''
print(f"Companies with a number to check: {(~D['numbers_ok']).sum()}")
print(D.loc[~D['numbers_ok'], ['CompanyName', 'turnover', 'ebitda', 'ebitda_margin', 'turnover_growth', 'figures_source', 'data_flags']].to_string())

UK_WORDS = ('united kingdom', 'england', 'wales', 'scotland', 'northern ireland', 'great britain',
            'companies house', 'registrar of companies', 'uk')
SPONSOR_WORDS = r'\b(BIDCO|TOPCO|MIDCO|HOLDCO|CAPITAL|PARTNERS|EQUITY|INVESTMENTS?|ACQUISITIONS?|L\.?P\.?|FUND)\b'
psc_cache = {}

def psc(num):
    if num not in psc_cache:
        r = get(f'{API}/company/{num}/persons-with-significant-control', params={'items_per_page': 25})
        psc_cache[num] = [i for i in r.json().get('items', []) if not i.get('ceased_on')] if (r is not None and r.status_code == 200) else None
    return psc_cache[num]

def uk_number(reg):
    reg = re.sub(r'\s', '', str(reg or '')).upper()
    if re.fullmatch(r'\d{5,8}', reg):
        return reg.zfill(8)
    if re.fullmatch(r'(SC|NI|OC|SO)\d{6}', reg):
        return reg
    return None

def ownership(num):
    chain, numbers, since, current = [], [], None, num
    seen = {num}
    for level in range(4):
        items = psc(current)
        if items is None:
            return 'Unknown', chain, numbers, since
        corps = [i for i in items if 'corporate' in i.get('kind', '') or 'legal-person' in i.get('kind', '')]
        people = [i for i in items if 'individual' in i.get('kind', '')]
        if not corps:
            if people:
                if level == 0:
                    since = min((i.get('notified_on') or '') for i in people) or None
                    return 'Founder or family-owned', chain, numbers, since
                return 'UK group, owner-managed', chain, numbers, since
            return 'Unknown', chain, numbers, since
        c = corps[0]
        ident = c.get('identification', {}) or {}
        chain.append(c.get('name', ''))
        if level == 0:
            since = c.get('notified_on')
        place = ' '.join(str(ident.get(k, '')) for k in ('country_registered', 'place_registered', 'legal_authority')).lower()
        is_uk = any(w in place for w in UK_WORDS)
        if place.strip() and not is_uk:   # registered abroad: don't follow a foreign registration number
            return 'Foreign-owned subsidiary', chain, numbers, since
        nxt = uk_number(ident.get('registration_number'))
        if not is_uk and not nxt:
            return 'Foreign-owned subsidiary', chain, numbers, since
        if not nxt:
            return 'UK group, owner-managed', chain, numbers, since
        if nxt in seen:   # ownership loops back, e.g. an employee ownership trust
            return 'UK group, owner-managed', chain, numbers, since
        seen.add(nxt)
        numbers.append(nxt)
        current = nxt
    return 'UK group, owner-managed', chain, numbers, since

rows, start = [], time.time()
for i, num in enumerate(D['CompanyNumber'], 1):
    kind, chain, numbers, since = ownership(num)
    if any(re.search(r'\bEOT\b|EMPLOYEE OWNERSHIP|EMPLOYEE BENEFIT|EMPLOYEE TRUST', n.upper()) for n in chain):
        kind = 'Employee-owned (EOT)'   # rarely for sale
    elif any(re.search(SPONSOR_WORDS, n.upper()) for n in chain):   # e.g. UK Bidco owned by a Jersey Topco
        kind = 'Likely sponsor-owned (check)'
    rows.append({'CompanyNumber': num, 'ownership': kind, 'owner_chain': ' > '.join(chain),
                 'parent_numbers': '|'.join(numbers), 'owner_since': since})
    if i % 25 == 0 or i == len(D):
        print(f'{i}/{len(D)} | {round((time.time() - start) / 60, 1)} min')

O = pd.DataFrame(rows)
D = D.drop(columns=[c for c in O.columns if c != 'CompanyNumber' and c in D.columns]).merge(O, on='CompanyNumber', how='left')
D['owner_since_year'] = pd.to_datetime(D['owner_since'], errors='coerce').dt.year

# Ownership found by web checks overrides the register (e.g. recent acquisitions not yet filed)
OV = f'{CFG}/ownership_overrides.csv'
if os.path.exists(OV):
    for _, o in pd.read_csv(OV, dtype=str).iterrows():
        m = D['CompanyNumber'] == o['CompanyNumber']
        D.loc[m, 'ownership'] = o['ownership']
        D.loc[m, 'owner_chain'] = f"{o['owner_chain']} (web-checked: {o['source']})"
    print(f'Ownership overrides applied: {len(pd.read_csv(OV))}')
print()
print(D['ownership'].value_counts().to_string())

in_list = set(D['CompanyNumber'])
name_of = dict(zip(D['CompanyNumber'], D['CompanyName']))
D['duplicate_of'] = ''
D['duplicate_of_number'] = ''

for idx, r in D.iterrows():
    parents = [p for p in str(r['parent_numbers'] or '').split('|') if p in in_list and p != r['CompanyNumber']]
    if parents:
        D.at[idx, 'duplicate_of'] = name_of[parents[-1]]
        D.at[idx, 'duplicate_of_number'] = parents[-1]

first_word = D['CompanyName'].str.upper().str.split().str[0]
for a in D.index:
    for b in D.index:
        if a >= b or D.at[a, 'duplicate_of'] or D.at[b, 'duplicate_of']:
            continue
        ta, tb = D.at[a, 'turnover'], D.at[b, 'turnover']
        if first_word[a] == first_word[b] and pd.notna(ta) and pd.notna(tb) and abs(ta - tb) <= 0.02 * max(ta, tb):
            top_is_a = bool(re.search(r'HOLDING|GROUP', D.at[a, 'CompanyName'].upper())) or ta >= tb
            keep, drop = (a, b) if top_is_a else (b, a)
            D.at[drop, 'duplicate_of'] = D.at[keep, 'CompanyName']
            D.at[drop, 'duplicate_of_number'] = D.at[keep, 'CompanyNumber']

dups = D[D['duplicate_of'] != '']
print(f'Duplicates found: {len(dups)}')
print(dups[['CompanyName', 'duplicate_of', 'turnover']].to_string())

R = pd.read_csv(f'{CFG}/relevance_draft.csv', dtype={'CompanyNumber': str})
D = D.drop(columns=[c for c in ('relevance', 'relevance_reason') if c in D.columns])
D = D.merge(R[['CompanyNumber', 'relevance', 'relevance_reason']], on='CompanyNumber', how='left')
D['relevance'] = D['relevance'].fillna('UNSURE')
D['relevance_reason'] = D['relevance_reason'].fillna('Not yet reviewed')

# A group company kept in place of its subsidiary takes the subsidiary's relevance call if it has none of its own
for _, child in D[D['duplicate_of_number'] != ''].iterrows():
    parent = D.index[D['CompanyNumber'] == child['duplicate_of_number']]
    if len(parent) and D.at[parent[0], 'relevance'] == 'UNSURE' and child['relevance'] != 'UNSURE':
        D.at[parent[0], 'relevance'] = child['relevance']
        D.at[parent[0], 'relevance_reason'] = f"{child['relevance_reason']} (via subsidiary {child['CompanyName'].title()})"
print(D['relevance'].value_counts().to_string())

def exclusion(r):
    if r['relevance'] == 'OUT':
        return 'Not digital infrastructure: ' + r['relevance_reason'].split(' (draft')[0]
    if r['duplicate_of']:
        return 'Duplicate of ' + r['duplicate_of']
    if r['ownership'] == 'Foreign-owned subsidiary':
        return 'Foreign-owned subsidiary (not buyable on its own): ' + str(r['owner_chain']).split(' > ')[0]
    return ''

D['excluded_reason'] = D.apply(exclusion, axis=1)
D['goes_forward'] = D['excluded_reason'] == ''
D['plc_check_listed'] = D['CompanyCategory'].str.startswith('Public') & D['goes_forward']

keep = D[D['goes_forward']]
print(f'Candidates: {len(D)} | going forward: {len(keep)} | excluded: {(~D["goes_forward"]).sum()}')
print()
print('Going forward, by status:')
print(keep['status'].value_counts().to_string())
print()
print('Shortlist going forward, by relevance and ownership:')
print(pd.crosstab(keep[keep['status'] == 'Shortlist']['relevance'], keep[keep['status'] == 'Shortlist']['ownership'], margins=True).to_string())
print()
print('PLCs to check are not listed:', keep[keep['plc_check_listed']]['CompanyName'].tolist())

cols = ['CompanyName', 'CompanyNumber', 'segment', 'status', 'goes_forward', 'excluded_reason',
        'relevance', 'relevance_reason', 'ownership', 'owner_chain', 'owner_since', 'owner_since_year',
        'numbers_ok', 'data_flags', 'figures_source', 'duplicate_of', 'plc_check_listed',
        'turnover', 'turnover_prior', 'turnover_growth', 'operating_profit', 'ebitda', 'ebitda_basis', 'ebitda_margin',
        'gross_profit', 'staff_costs', 'profit_before_tax', 'cash', 'net_assets', 'employees',
        'accounts_kind', 'accounts_filed', 'CompanyCategory', 'RegAddress.PostTown', 'source', 'snapshot']
cols = [c for c in cols if c in D.columns]
D = D.sort_values(['goes_forward', 'status', 'turnover'], ascending=[False, True, False])
D[cols].to_csv(f'{OUT}/candidates_clean.csv', index=False)
D[~D['goes_forward']][['CompanyName', 'CompanyNumber', 'status', 'excluded_reason']].to_csv(f'{OUT}/excluded_log.csv', index=False)
print('Saved candidates_clean.csv and excluded_log.csv to data/outputs')
