"""Step 02b: widen the universe to companies registered under neighbouring industry codes (method v4.1).

Some real deal targets in digital infrastructure are registered as IT services or electrical and civil contractors
(for example Excalibur, Ammcom, OryxAlign), so the six telecoms and data-centre codes never see them. This adds
the codes in the thesis file's "extra_segments" with the same entry rules as the original universe:
active, private limited company, files full or group accounts, incorporated at least three years ago.

Stage "list" (one job): downloads the Companies House free company data product and keeps matching companies
  -> data/inputs/universe_added.csv
Stage "read" (sharded, SHARD/SHARDS): reads each company's latest accounts exactly as the original run did
  (tagged numbers, else the accounts text) and, for digital accounts, keeps the principal activity sentence and
  any network words in it -> data/inputs/financials_added_<shard>.csv
Scanned (PDF) accounts are listed with status "PDF scan" for the OCR job to read later.

Companies in these codes are mostly IT and electrical firms with no network activity, so clean.py makes an
automatic rulebook call for them: OUT unless the accounts describe network, telecoms, fibre, data-centre or
connectivity work, in which case UNSURE for a manual call (method/METHOD.md, section 2).
Skills: market-map-and-sourcing (target universe), deal-screening.
"""
import os, re, io, sys, zipfile, datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from settings import C, ROOT

STAGE = os.environ.get('STAGE', 'list')
SHARD, SHARDS = int(os.environ.get('SHARD', '0')), int(os.environ.get('SHARDS', '1'))
INP = f'{ROOT}/data/inputs'
EXTRA = C.get('extra_segments', {})
NETWORK = re.compile(r'telecom|network|fibre|fiber|broadband|connectivity|data cent|datacent|wireless|mobile operator|5g|4g|'
                     r'radio|satellite|cabling|structured cabling|tower|mast|small cell|wifi|wi-fi|voip|unified comm|'
                     r'internet service|isp\b|hosting|colocation|co-location|cloud communication', re.I)


def list_companies():
    H = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'}
    import time
    raw, page = None, ''
    today = datetime.date.today()
    dates = [today.replace(day=1).isoformat(), (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1).isoformat()]
    for attempt in range(10):   # the download site has answered 'Service Unavailable' to cloud runners: keep trying for ~50 minutes
        for base in ('https://download.companieshouse.gov.uk', 'http://download.companieshouse.gov.uk'):
            try:
                page = requests.get(f'{base}/en_output.html', timeout=60, headers=H).text
            except requests.RequestException as e:
                page = f'error {e}'
            found = re.findall(r'BasicCompanyDataAsOneFile-(\d{4}-\d{2}-\d{2})\.zip', page)
            for snapshot in sorted(set(found), reverse=True) + dates:
                url = f'{base}/BasicCompanyDataAsOneFile-{snapshot}.zip'
                try:
                    r = requests.get(url, timeout=1800, headers=H)
                except requests.RequestException as e:
                    print('  ', url, e, flush=True)
                    continue
                print('  ', url, r.status_code, flush=True)
                if r.status_code == 200 and r.content[:2] == b'PK':
                    raw = r.content
                    break
            if raw is not None:
                break
        if raw is not None:
            break
        print(f'Attempt {attempt + 1} failed; index page starts: {page[:120]!r}; waiting 5 minutes', flush=True)
        time.sleep(300)
    if raw is None:
        print('Could not download the free company data product.')
        raise SystemExit(1)
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = z.namelist()[0]
    codes = {c: seg for seg, cs in EXTRA.items() for c in cs}
    cutoff = (datetime.date.fromisoformat(snapshot) - datetime.timedelta(days=3 * 365)).isoformat()
    have = set(pd.read_csv(f'{INP}/financials_all.csv', dtype={'CompanyNumber': str})['CompanyNumber'])
    keep = []
    cols = ['CompanyName', ' CompanyNumber', 'CompanyCategory', 'CompanyStatus', 'IncorporationDate', 'Accounts.AccountCategory',
            'RegAddress.PostTown', 'SICCode.SicText_1', 'SICCode.SicText_2', 'SICCode.SicText_3', 'SICCode.SicText_4']
    with z.open(name) as f:
        for chunk in pd.read_csv(f, dtype=str, usecols=lambda c: c.strip() in [x.strip() for x in cols], chunksize=200_000):
            chunk.columns = [c.strip() for c in chunk.columns]
            chunk = chunk[(chunk['CompanyStatus'] == 'Active') & (chunk['CompanyCategory'] == 'Private Limited Company')
                          & chunk['Accounts.AccountCategory'].isin(['FULL', 'GROUP'])]
            inc = pd.to_datetime(chunk['IncorporationDate'], dayfirst=True, errors='coerce').dt.strftime('%Y-%m-%d')
            chunk = chunk[inc <= cutoff]
            sic = chunk[[f'SICCode.SicText_{i}' for i in range(1, 5)]].fillna('').apply(lambda s: s.str[:5])
            seg = sic.apply(lambda r: next((codes[c] for c in r if c in codes), None), axis=1)
            chunk = chunk.assign(segment=seg)[seg.notna()]
            keep.append(chunk)
    U = pd.concat(keep, ignore_index=True)
    U = U[~U['CompanyNumber'].isin(have)].drop_duplicates('CompanyNumber')
    U['snapshot'] = snapshot
    U.to_csv(f'{INP}/universe_added.csv', index=False)
    print(f'{len(U)} companies added from codes {sorted(codes)}:', U['segment'].value_counts().to_dict())


def activity(raw):
    text = re.sub(r'\s+', ' ', BeautifulSoup(raw, 'lxml').get_text(' '))
    m = re.search(r'principal activit(?:y|ies)[^.]{0,40}?(?:is|was|were|are|continued to be|consists? of|comprises?)\s*([^.]{10,300})', text, re.I)
    return (m.group(1).strip() if m else '')[:300]


def read_companies():
    import accounts as A
    U = pd.read_csv(f'{INP}/universe_added.csv', dtype={'CompanyNumber': str})
    U = U.sort_values('CompanyNumber').reset_index(drop=True)
    U = U[U.index % SHARDS == SHARD]
    print(f'Shard {SHARD + 1} of {SHARDS}: {len(U)} companies', flush=True)
    rows = []
    for i, (_, u) in enumerate(U.iterrows()):
        num = u['CompanyNumber']
        row = {'CompanyNumber': num}
        item, err = A.latest_accounts(num)
        raw = None
        if item:
            row.update(accounts_type=item.get('type'), accounts_filed=item.get('date'),
                       accounts_kind=(item.get('description') or '').replace('accounts-with-accounts-type-', ''))
            raw, fmt, err = A.fetch_document(item['links']['document_metadata'])
            row['format'] = fmt
            if raw:
                try:
                    row.update(A.parse_ixbrl(raw))
                    if row.get('turnover') is not None:
                        row['figures_source'] = 'Tagged'
                    else:
                        for k, v in A.from_text(raw).items():
                            if row.get(k) is None:
                                row[k] = v
                    row['currency'] = A.currency_of(raw)
                    row['activity_text'] = activity(raw)
                except Exception as e:
                    err = f'parse error: {e}'
        row['error'] = err
        row = A.classify(A.add_ebitda(row))
        row.update(CompanyName=u['CompanyName'], segment=u['segment'], CompanyCategory=u['CompanyCategory'],
                   **{'RegAddress.PostTown': u.get('RegAddress.PostTown')}, source='Companies House free company data product (extra codes)',
                   snapshot=u['snapshot'])
        row['network_words'] = ', '.join(sorted({w.lower() for w in NETWORK.findall(row.get('activity_text') or '')}))
        rows.append(row)
        if i % 50 == 0:
            print(f'{i} read', flush=True)
    pd.DataFrame(rows).to_csv(f'{INP}/financials_added_{SHARD}.csv', index=False)
    print(f'Saved {len(rows)} companies')


if __name__ == '__main__':
    list_companies() if STAGE == 'list' else read_companies()
