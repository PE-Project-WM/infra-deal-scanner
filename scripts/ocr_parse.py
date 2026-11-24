"""Step 03c: read the figures from the scanned-accounts text saved by ocr_fetch.py.

For each data/ocr/text/<number>_<filed>.txt, finds the profit and loss account and reads turnover (this year and last),
operating profit, profit before tax, depreciation and amortisation (from the notes), cash and net assets
(from the balance sheet). Handles £'000 presentation and dollar or euro accounts.
Writes data/ocr/ocr_financials.csv; clean.py fills these into companies whose latest accounts are a scan.
Every figure is labelled "OCR, check": OCR can misread digits, so the sanity checks below drop anything implausible.
"""
import os, re, glob
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TXT = f'{ROOT}/data/ocr/text'

PL_HEAD = re.compile(r'(profit and loss account|statement of (comprehensive )?income|income statement|statement of profit or loss|profit and loss)', re.I)
BS_HEAD = re.compile(r'(balance sheet|statement of financial position)', re.I)
NUM = re.compile(r'\(?-?\d{1,3}(?:[,.] ?\d{3})+\)?|\(?-?\d{4,}\)?')
YEAR = re.compile(r'^(19|20)\d\d$')

LINES = {
    'turnover': re.compile(r'^\W{0,3}(group |total )?(turnover|revenue)\b', re.I),
    'operating_profit': re.compile(r'^\W{0,3}(group )?(operating (profit|loss)|(profit|loss)\s*/?\s*\(?(profit|loss)?\)?\s*from operations)', re.I),
    'profit_before_tax': re.compile(r'^\W{0,3}(profit|loss)[^0-9]{0,40}before (income )?tax', re.I),
    'gross_profit': re.compile(r'^\W{0,3}gross (profit|loss)\b', re.I),
    'cost_of_sales': re.compile(r'^\W{0,3}cost of (sales|revenue)\b', re.I),
    'depreciation': re.compile(r'^\W{0,3}depreciation\b', re.I),
    'amortisation': re.compile(r'^\W{0,3}amorti[sz]ation\b', re.I),
    'cash': re.compile(r'^\W{0,3}cash (at bank( and in hand)?|and cash equivalents|in hand)\b', re.I),
    'net_assets': re.compile(r'^\W{0,3}(net assets|total equity|total shareholders. funds)\b', re.I),
}

def numbers(line, small_ok=False):
    """Amounts on a line, in order; skips years and note numbers. small_ok: the page is in £000s, so small amounts count."""
    out = []
    if not small_ok:   # whole pounds: OCR sometimes splits '2,247,576' into '2,247 576'
        line = re.sub(r'(\d{1,3}(?:,\d{3})+) (\d{3})(?![\d,])', r'\1,\2', line)
    for m in NUM.findall(line) if not small_ok else re.findall(r'\(?-?\d{1,3}(?:[,.] ?\d{3})+\)?|\(?-?\d+\)?', line):
        neg = m.startswith('(') or m.startswith('-')
        digits = re.sub(r'[^\d]', '', m)
        if not digits:
            continue
        if YEAR.match(digits) and ',' not in m and '.' not in m:
            continue
        v = float(digits)
        if v >= 1000 or (',' in m or '.' in m) or small_ok:
            out.append((-v if neg else v, m))
    while small_ok and len(out) >= 3 and abs(out[0][0]) <= 40 and ',' not in out[0][1]:
        out = out[1:]   # leading note numbers (e.g. '11, 12')
    return [v for v, _ in out]

def pages(text):
    parts = re.split(r'=== page (\d+) ===\n', text)
    return [(int(parts[i]), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]

def scale_of(page):
    if re.search(r"(£|\$|€|us\$|usd|eur|gbp)\s?['’`]?\s?(000|k)\b|in thousands|['’]000", page, re.I):
        return 1000
    if re.search(r"(£|\$|€)\s?m\b|(£|\$|€)\s?million|in millions", page, re.I):
        return 1_000_000
    return 1

def currency_of(text):
    head = text[:60000]
    m = re.search(r'(presentation|functional|reporting) currency[^.]{0,160}', head, re.I)
    s = m.group(0).lower() if m else ''
    if 'dollar' in s or 'usd' in s:
        return 'USD'
    if 'euro' in s or ' eur' in s:
        return 'EUR'
    if 'sterling' in s or 'gbp' in s or '£' in s:
        return 'GBP'
    dollars = len(re.findall(r"US\$|\bUSD\b|\$\s?['’]?000|\$k\b|\$\s?\d", head))
    if dollars > 5 and dollars > 3 * len(re.findall('£', head)):
        return 'USD'
    return 'GBP'

def first_line(page, key, small_ok=False):
    for line in page.split('\n'):
        if LINES[key].search(line):
            nums = numbers(line, small_ok)
            if nums:
                return nums
    return None

def parse(text):
    P = pages(text)
    out = {}
    pl = [(n, t) for n, t in P if PL_HEAD.search(t) and first_line(t, 'turnover')]
    if not pl:
        return {'problem': 'no profit and loss account with turnover found'}
    n0, page = pl[0]   # group accounts put the consolidated statement first
    k = scale_of(page)
    raw = first_line(page, 'turnover', k > 1)
    if k == 1_000_000 and raw and abs(raw[0]) >= 100_000:
        k = 1   # whole pounds on the page; the 'million' was in a heading or note
    if k == 1 and raw and abs(raw[0]) < 100_000:
        k = scale_of(text[:20000]) if scale_of(text[:20000]) == 1000 else 1
    t = first_line(page, 'turnover', k > 1)
    out['turnover'] = t[0] * k
    out['turnover_prior'] = t[1] * k if len(t) > 1 else None
    for key in ('operating_profit', 'profit_before_tax', 'gross_profit', 'cost_of_sales'):
        v = first_line(page, key, k > 1)
        if v:
            out[key] = v[0] * k
    gp, cos = out.pop('gross_profit', None), out.pop('cost_of_sales', None)
    if gp is not None and cos is not None:
        implied = gp + abs(cos)   # turnover = gross profit + cost of sales: catches a misread digit
        if implied > 0 and abs(out['turnover'] - implied) / implied > 0.02:
            out['turnover'], out['turnover_prior'], out['fixed'] = implied, None, 'turnover rebuilt from gross profit + cost of sales'
    # depreciation and amortisation: the 'stated after charging' note first, then the cash flow statement,
    # then any other page from the P&L on. Lines about revaluation reserves or wrapped headings are skipped.
    BAD = re.compile(r'revalu|excess|transfer|before|accumulated|policy|provided|charged so', re.I)
    after = [(n, t) for n, t in P if n >= n0 and re.search(r'after charging', t, re.I)]
    cashflow = [(n, t) for n, t in P if n >= n0 and re.search(r'cash flows? from operating activities', t, re.I)]
    rest = [(n, t) for n, t in P if n >= n0]
    def find(group, key):
        for n, t in group:
            kt = scale_of(t) if scale_of(t) > 1 else k
            for line in t.split('\n'):
                if LINES[key].search(line) and not BAD.search(line):
                    v = numbers(line, kt > 1)
                    if v:
                        return abs(v[0]) * kt, n
        return None, None
    da = 0.0
    for group, basis in ((after, 'note'), (cashflow, 'cash flow'), (rest, 'other')):
        dep, _ = find(group, 'depreciation')
        amo, _ = find(group, 'amortisation')
        if dep or amo:
            if dep:
                out['depreciation'] = dep
            if amo and not (dep and basis == 'cash flow'):   # cash-flow lines usually combine D&A already
                out['amortisation'] = amo
            da = (dep or 0) + (out.get('amortisation') or 0)
            out['da_source'] = basis
            break
    if da:
        out['da_total'] = da
    bs = [(n, t) for n, t in P if BS_HEAD.search(t) and (first_line(t, 'net_assets') or first_line(t, 'cash'))]
    if bs:
        b = bs[0][1]
        kb = scale_of(b) if scale_of(b) > 1 else k
        for key in ('cash', 'net_assets'):
            v = first_line(b, key, kb > 1)
            if v:
                out[key] = v[0] * kb
    m = re.search(r'(year|period|52 weeks|53 weeks) ended\s+(\d{1,2}(st|nd|rd|th)? \w+ \d{4})', text, re.I)
    out['period_text'] = m.group(2) if m else None
    out['unit'] = {1: '£', 1000: "000s", 1_000_000: 'millions'}[k]
    head = page[:1500]   # the column headings of the P&L say which currency it is in
    if re.search(r"€|\bEUR\b", head) and not re.search('£', head):
        out['page_currency'] = 'EUR'
    elif re.search(r"\$|\bUSD\b", head) and not re.search('£', head):
        out['page_currency'] = 'USD'
    elif re.search('£', head):
        out['page_currency'] = 'GBP'
    return out

def checks(o):
    """Drop figures that cannot be right; OCR misreads usually show up as impossible ratios."""
    t = o.get('turnover')
    if not t or t < 100_000 or t > 50e9:
        return 'turnover implausible'
    if o.get('turnover_prior') and not (0.2 <= t / o['turnover_prior'] <= 5):
        o['turnover_prior'] = None   # likely misread; keep the current year
    for key in ('operating_profit', 'profit_before_tax'):
        if o.get(key) is not None and abs(o[key]) > 1.5 * t:
            o[key] = None
    if o.get('da_total') and o['da_total'] > 0.6 * t:
        o['da_total'] = None
    return ''

rows = []
for path in sorted(glob.glob(f'{TXT}/*.txt')):
    num, filed = os.path.basename(path)[:-4].rsplit('_', 1)
    text = open(path, errors='ignore').read()
    o = parse(text)
    o.update({'CompanyNumber': num, 'filed': filed})
    o['currency'] = o.pop('page_currency', None) or currency_of(text)
    if 'problem' not in o:
        o['problem'] = checks(o)
    op, da = o.get('operating_profit'), o.get('da_total')
    if op is not None and da:
        o['ebitda'], o['ebitda_basis'] = op + da, 'Operating profit + D&A (OCR)'
    elif op is not None:
        o['ebitda'], o['ebitda_basis'] = op, 'ESTIMATE: operating profit only (OCR, no D&A found)'
    o['figures_source'] = 'OCR, check'
    rows.append(o)

R = pd.DataFrame(rows)
cols = ['CompanyNumber', 'filed', 'period_text', 'currency', 'unit', 'turnover', 'turnover_prior', 'operating_profit',
        'profit_before_tax', 'depreciation', 'amortisation', 'da_total', 'ebitda', 'ebitda_basis', 'cash', 'net_assets',
        'da_source', 'figures_source', 'fixed', 'problem']
R = R.reindex(columns=cols)
R.to_csv(f'{ROOT}/data/ocr/ocr_financials.csv', index=False)
ok = R[R['problem'].fillna('') == '']
print(f'Read {len(R)} scanned filings: turnover found for {len(ok)}, operating profit for {ok["operating_profit"].notna().sum()}, '
      f'D&A for {ok["da_total"].notna().sum()}, cash for {ok["cash"].notna().sum()}')
print(R['problem'].fillna('').value_counts().to_string())
