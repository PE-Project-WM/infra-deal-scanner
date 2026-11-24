"""Render chosen pages of scanned filings as images, so OCR figures can be checked by eye.

Reads config/ocr_verify_pages.txt (one line per company: '<number> <page>,<page>') and saves
data/ocr/pages/<number>_p<page>.png from the company's latest accounts PDF.
"""
import os, sys, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import accounts as A

OUT = f'{A.ROOT}/data/ocr/pages'
os.makedirs(OUT, exist_ok=True)
for line in open(f'{A.ROOT}/config/ocr_verify_pages.txt'):
    if not line.strip():
        continue
    num, pages = line.split()
    item, err = A.latest_accounts(num)
    if not item:
        print(num, err)
        continue
    doc_id = item['links']['document_metadata'].rstrip('/').split('/')[-1]
    r = A.get(A.DOC_API + doc_id + '/content', headers={'Accept': 'application/pdf'})
    if r is None or r.status_code != 200:
        print(num, 'download error')
        continue
    with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
        f.write(r.content)
        f.flush()
        for p in pages.split(','):
            base = f'{OUT}/{num}_p{p}'
            subprocess.run(['pdftoppm', '-r', '110', '-gray', '-f', p, '-l', p, '-singlefile', '-png', f.name, base])
    print(num, 'pages', pages)
