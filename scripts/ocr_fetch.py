"""Step 03b: read the accounts that were filed as scanned PDFs (Version 2 item 5).

For every company in data/inputs/financials_all.csv whose latest accounts are a PDF, download that PDF from
Companies House and get its text: the PDF's own text layer if it has one, otherwise OCR (tesseract) page by page.
Saves one text file per filing in data/ocr/text/<number>_<filed>.txt, with "=== page N ===" markers,
so the figures can be re-read (scripts/ocr_parse.py) without downloading or OCR-ing again.

Runs in GitHub Actions, split into shards that run in parallel (SHARD = i, SHARDS = n).
Only the pages around the profit and loss account and the notes are OCR'd, to keep run time down.
"""
import os, re, sys, time, subprocess, tempfile
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import accounts as A

ROOT = A.ROOT
OUT = f'{ROOT}/data/ocr/text'
os.makedirs(OUT, exist_ok=True)
SHARD, SHARDS = int(os.environ.get('SHARD', '0')), int(os.environ.get('SHARDS', '1'))
LIMIT = int(os.environ.get('LIMIT', '0') or 0)
MAX_PAGES = int(os.environ.get('MAX_PAGES', '45'))
DPI = os.environ.get('DPI', '200')

PL_HEAD = re.compile(r'(profit and loss account|statement of (comprehensive )?income|income statement|statement of profit or loss)', re.I)
PL_LINE = re.compile(r'^\s*(turnover|revenue)\b', re.I | re.M)

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def pages_in(pdf):
    info = run(['pdfinfo', pdf]).stdout
    m = re.search(r'Pages:\s+(\d+)', info)
    return int(m.group(1)) if m else 0

def text_layer(pdf, n):
    """The PDF's own text, page by page (empty for image-only scans)."""
    out = []
    for p in range(1, n + 1):
        out.append(run(['pdftotext', '-layout', '-f', str(p), '-l', str(p), pdf, '-']).stdout)
    return out

def ocr_page(pdf, p, tmp):
    base = f'{tmp}/p{p}'
    run(['pdftoppm', '-r', DPI, '-gray', '-f', str(p), '-l', str(p), '-singlefile', '-png', pdf, base])
    if not os.path.exists(base + '.png'):
        return ''
    t = run(['tesseract', base + '.png', '-', '--psm', '6']).stdout   # psm 6: one block of text keeps table rows on one line
    os.remove(base + '.png')
    return t

def ocr_pages(pdf, n):
    """OCR pages in order; once the profit and loss account is found, read 18 more pages (notes) and stop."""
    texts, stop = {}, min(n, MAX_PAGES)
    with tempfile.TemporaryDirectory() as tmp:
        p = 1
        while p <= stop:
            t = ocr_page(pdf, p, tmp)
            texts[p] = t
            if PL_HEAD.search(t) and PL_LINE.search(t) and stop > p + 18:
                stop = min(stop, p + 18)
            p += 1
    return [texts.get(i, '') for i in range(1, n + 1)]

F = pd.read_csv(f'{ROOT}/data/inputs/financials_all.csv', dtype={'CompanyNumber': str})
todo = F[F['format'] == 'pdf'].sort_values('CompanyNumber').reset_index(drop=True)
todo = todo[todo.index % SHARDS == SHARD]
if LIMIT:
    todo = todo.head(LIMIT)
print(f'Shard {SHARD + 1} of {SHARDS}: {len(todo)} PDF filings')

log = []
for _, co in todo.iterrows():
    num, t0 = co['CompanyNumber'], time.time()
    rec = {'CompanyNumber': num, 'CompanyName': co['CompanyName'], 'accounts_filed': co['accounts_filed']}
    item, err = A.latest_accounts(num)
    if not item:
        rec['result'] = err
        log.append(rec)
        continue
    rec['filed'] = item.get('date')
    path = f"{OUT}/{num}_{rec['filed']}.txt"
    if os.path.exists(path):
        rec['result'] = 'already read'
        log.append(rec)
        continue
    doc_id = item['links']['document_metadata'].rstrip('/').split('/')[-1]
    r = A.get(A.DOC_API + doc_id + '/content', headers={'Accept': 'application/pdf'})
    if r is None or r.status_code != 200 or not r.content.startswith(b'%PDF'):
        rec['result'] = f'download error {getattr(r, "status_code", "none")}'
        log.append(rec)
        continue
    with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
        f.write(r.content)
        f.flush()
        n = pages_in(f.name)
        layer = text_layer(f.name, n)
        if sum(len(t.strip()) for t in layer) > 300 * max(1, min(n, 5)):
            pages, rec['method'] = layer, 'text layer'
        else:
            pages, rec['method'] = ocr_pages(f.name, n), 'OCR'
    open(path, 'w').write(''.join(f'=== page {i + 1} ===\n{t}\n' for i, t in enumerate(pages) if t.strip()))
    rec.update({'pages': n, 'pages_read': sum(1 for t in pages if t.strip()), 'seconds': round(time.time() - t0),
                'result': 'saved'})
    log.append(rec)
    print(f"{co['CompanyName']}: {rec['method']}, {rec['pages_read']}/{n} pages, {rec['seconds']}s", flush=True)

os.makedirs(f'{ROOT}/data/ocr/logs', exist_ok=True)
pd.DataFrame(log).to_csv(f'{ROOT}/data/ocr/logs/fetch_shard_{SHARD}.csv', index=False)
print(f'Done: {sum(1 for x in log if x.get("result") == "saved")} saved')
