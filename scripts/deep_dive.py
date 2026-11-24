"""Deep dive on the top-ranked companies: last 3 filed accounts each.

Saves every tagged number (data/deep_dive/facts.csv) and the full text of each digital filing
(data/deep_dive/text/), for the valuation check and the memo.
Skills: deal-screening (preliminary financial assessment), dcf-model and ic-memo-drafting (inputs).
"""
import os, re, time, requests
import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f'{ROOT}/data/deep_dive'
os.makedirs(f'{OUT}/text', exist_ok=True)
TOP_N = int(os.environ.get('TOP_N', '10'))
YEARS = 3
KEY = os.environ['CH_API_KEY'].strip()
API = 'https://api.company-information.service.gov.uk'
DOC_API = 'https://document-api.company-information.service.gov.uk/document/'
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

def to_number(tag):
    text = tag.get_text().strip()
    fmt = (tag.get('format') or '').lower()
    if text in ('', '-', '–', '—') or 'zero' in fmt:
        return 0.0
    if any(f in fmt for f in ('numcommadecimal', 'num-comma-decimal', 'numdotcomma')):
        text = text.replace('.', '').replace(' ', '').replace(',', '.')
    else:
        text = text.replace(',', '').replace(' ', '')
    try:
        value = float(text)
    except ValueError:
        return None
    name = (tag.get('name') or '').split(':')[-1]
    if 'Employee' not in name:
        value *= 10 ** int(tag.get('scale') or 0)
    return -value if tag.get('sign') == '-' else value

ranking = pd.read_csv(f'{ROOT}/data/outputs/ranking_latest.csv', dtype={'CompanyNumber': str}).head(TOP_N)
facts, filings = [], []
for _, co in ranking.iterrows():
    num, name = co['CompanyNumber'], co['CompanyName']
    r = get(f'{API}/company/{num}/filing-history', params={'category': 'accounts', 'items_per_page': 20})
    items = [i for i in r.json().get('items', []) if i.get('type') == 'AA' and i.get('links', {}).get('document_metadata')] if r is not None and r.status_code == 200 else []
    for item in items[:YEARS]:
        doc_id = item['links']['document_metadata'].rstrip('/').split('/')[-1]
        m = get(DOC_API + doc_id)
        res = m.json().get('resources', {}) if m is not None and m.status_code == 200 else {}
        rec = {'CompanyNumber': num, 'CompanyName': name, 'filed': item.get('date'),
               'made_up_to': item.get('description_values', {}).get('made_up_date'),
               'kind': (item.get('description') or '').replace('accounts-with-accounts-type-', ''),
               'format': 'ixbrl' if 'application/xhtml+xml' in res else 'pdf' if 'application/pdf' in res else 'none',
               'document_url': f'{DOC_API}{doc_id}/content'}
        filings.append(rec)
        if rec['format'] != 'ixbrl':
            continue
        c = get(DOC_API + doc_id + '/content', headers={'Accept': 'application/xhtml+xml'})
        if c is None or c.status_code != 200:
            continue
        soup = BeautifulSoup(c.content, 'lxml')
        contexts = {}
        for ctx in soup.find_all(lambda t: t.name and t.name.endswith('context')):
            end = ctx.find(lambda t: t.name and (t.name.endswith('enddate') or t.name.endswith('instant')))
            dim = ctx.find(lambda t: t.name and (t.name.endswith('segment') or t.name.endswith('scenario')))
            if end is not None:
                contexts[ctx.get('id')] = (end.get_text().strip(), 'dimension' if dim else '')
        for t in soup.find_all(lambda t: t.name and t.name.endswith('nonfraction')):
            end, dim = contexts.get(t.get('contextref'), ('', ''))
            facts.append({'CompanyNumber': num, 'CompanyName': name, 'filed': rec['filed'],
                          'tag': (t.get('name') or '').split(':')[-1], 'period_end': end,
                          'has_dimension': dim, 'value': to_number(t)})
        text = soup.get_text('\n')
        text = re.sub(r'\n\s*\n+', '\n', text)
        safe = re.sub(r'[^A-Z0-9]+', '_', name.upper()).strip('_')
        open(f'{OUT}/text/{safe}_{rec["filed"]}.txt', 'w').write(text)
    print(f'{name}: {len(items[:YEARS])} filings')

# Keep earlier deep dives for companies that have since left the top N, so their history (and score inputs) stay stable
def keep_old(new, path):
    new = pd.DataFrame(new)
    if os.path.exists(path) and len(new):
        old = pd.read_csv(path, dtype={'CompanyNumber': str})
        new = pd.concat([old[~old['CompanyNumber'].isin(new['CompanyNumber'])], new], ignore_index=True)
    return new
keep_old(filings, f'{OUT}/filings.csv').to_csv(f'{OUT}/filings.csv', index=False)
keep_old(facts, f'{OUT}/facts.csv').to_csv(f'{OUT}/facts.csv', index=False)
print(f'Saved {len(filings)} filings and {len(facts)} tagged numbers to data/deep_dive')
