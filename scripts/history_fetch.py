"""Step 04a: read the last three filed accounts of every company that goes forward (method v4).

Each set of accounts shows two years (this year and the comparative), so three filings give three to four years
and every middle year is read twice. history_parse.py uses that overlap as an independent check of the figures.

For every filing:
  - digital (iXBRL) accounts: every tagged number is saved (data/history/facts_<shard>.csv) and the text is kept;
  - scanned (PDF) accounts: the PDF's own text layer if it has one, otherwise OCR (tesseract), as in ocr_fetch.py.
Text is saved as data/history/text/<number>_<filed>.txt with "=== page N ===" markers. Filings already read by
ocr_fetch.py or deep_dive.py are not downloaded again.

Runs in GitHub Actions (.github/workflows/deep_dive.yml), split into shards: SHARD = i, SHARDS = n. Needs CH_API_KEY.
Skills: deal-screening (preliminary financial assessment), information-gap-log (which years are still missing).
"""
import os, re, sys, time, tempfile
import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import accounts as A
from ocr_fetch import pages_in, text_layer, ocr_pages

ROOT = A.ROOT
OUT = f'{ROOT}/data/history'
TXT = f'{OUT}/text'
os.makedirs(TXT, exist_ok=True)
SHARD, SHARDS = int(os.environ.get('SHARD', '0')), int(os.environ.get('SHARDS', '1'))
YEARS = int(os.environ.get('YEARS', '3'))
LIMIT = int(os.environ.get('LIMIT', '0') or 0)
EARLIER = [f'{ROOT}/data/ocr/text', f'{ROOT}/data/deep_dive/text', TXT]


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


def pseudo_pages(text, size=70):
    """Digital accounts have no pages: cut the text into blocks of about one printed page each."""
    lines = [l for l in text.split('\n') if l.strip()]
    return [('\n'.join(lines[i:i + size])) for i in range(0, len(lines), size)]


def already_read(num, filed):
    for d in EARLIER:
        p = f'{d}/{num}_{filed}.txt'
        if os.path.exists(p):
            return p
    return None


def main():
    D = pd.read_csv(f'{ROOT}/data/outputs/candidates_clean.csv', dtype={'CompanyNumber': str})
    todo = D[D['goes_forward']].sort_values('CompanyNumber').reset_index(drop=True)
    only = [n.strip() for n in os.environ.get('NUMBERS', '').split(',') if n.strip()]
    if only:   # a top-up run for named companies (e.g. ones that started going forward after the last run)
        todo = D[D['CompanyNumber'].isin(only)].drop_duplicates('CompanyNumber').reset_index(drop=True)
    todo = todo[todo.index % SHARDS == SHARD]
    if LIMIT:
        todo = todo.head(LIMIT)
    print(f'Shard {SHARD + 1} of {SHARDS}: {len(todo)} companies, last {YEARS} accounts each', flush=True)
    facts, log = [], []
    for _, co in todo.iterrows():
        num, name = co['CompanyNumber'], co['CompanyName']
        r = A.get(f'{A.API}/company/{num}/filing-history', params={'category': 'accounts', 'items_per_page': 25})
        items = ([i for i in r.json().get('items', []) if i.get('type') == 'AA' and i.get('links', {}).get('document_metadata')]
                 if r is not None and r.status_code == 200 else [])
        for item in items[:YEARS]:
            t0 = time.time()
            filed = item.get('date')
            rec = {'CompanyNumber': num, 'CompanyName': name, 'filed': filed,
                   'made_up_to': item.get('description_values', {}).get('made_up_date'),
                   'kind': (item.get('description') or '').replace('accounts-with-accounts-type-', '')}
            have = already_read(num, filed)
            doc_id = item['links']['document_metadata'].rstrip('/').split('/')[-1]
            m = A.get(A.DOC_API + doc_id)
            res = m.json().get('resources', {}) if m is not None and m.status_code == 200 else {}
            rec['format'] = 'ixbrl' if 'application/xhtml+xml' in res else 'pdf' if 'application/pdf' in res else 'none'
            if rec['format'] == 'ixbrl':
                c = A.get(A.DOC_API + doc_id + '/content', headers={'Accept': 'application/xhtml+xml'})
                if c is None or c.status_code != 200:
                    rec['result'] = 'download error'
                    log.append(rec)
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
                    facts.append({'CompanyNumber': num, 'CompanyName': name, 'filed': filed,
                                  'tag': (t.get('name') or '').split(':')[-1], 'period_end': end,
                                  'has_dimension': dim, 'value': to_number(t)})
                if not have:
                    text = re.sub(r'\n\s*\n+', '\n', soup.get_text('\n'))
                    pages = pseudo_pages(text)
                    open(f'{TXT}/{num}_{filed}.txt', 'w').write(''.join(f'=== page {i + 1} ===\n{p}\n' for i, p in enumerate(pages)))
                rec['result'] = 'tagged numbers saved' + ('' if have else ', text saved')
            elif rec['format'] == 'pdf':
                if have:
                    rec['result'] = 'already read'
                    log.append(rec)
                    continue
                r2 = A.get(A.DOC_API + doc_id + '/content', headers={'Accept': 'application/pdf'})
                if r2 is None or r2.status_code != 200 or not r2.content.startswith(b'%PDF'):
                    rec['result'] = 'download error'
                    log.append(rec)
                    continue
                with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
                    f.write(r2.content)
                    f.flush()
                    n = pages_in(f.name)
                    layer = text_layer(f.name, n)
                    if sum(len(t.strip()) for t in layer) > 300 * max(1, min(n, 5)):
                        pages, rec['method'] = layer, 'text layer'
                    else:
                        pages, rec['method'] = ocr_pages(f.name, n), 'OCR'
                open(f'{TXT}/{num}_{filed}.txt', 'w').write(''.join(f'=== page {i + 1} ===\n{t}\n' for i, t in enumerate(pages) if t.strip()))
                rec['result'] = 'text saved'
            else:
                rec['result'] = 'no document'
            rec['seconds'] = round(time.time() - t0)
            log.append(rec)
        print(f'{name}: {len(items[:YEARS])} filings', flush=True)
    tag = f'{SHARD}' + ('_topup' if only else '')
    pd.DataFrame(facts).to_csv(f'{OUT}/facts_{tag}.csv', index=False)
    pd.DataFrame(log).to_csv(f'{OUT}/filings_{tag}.csv', index=False)
    print(f'Saved {len(log)} filings and {len(facts)} tagged numbers')


if __name__ == '__main__':
    main()
