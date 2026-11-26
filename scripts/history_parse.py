"""Step 04b: read two years of figures from the text of every filing saved by history_fetch.py and ocr_fetch.py.

Each set of accounts shows this year and last year. For every filing this reads, for both years where the
accounts show them: turnover and operating profit; and for the filing's own year: depreciation and amortisation,
cash, net assets, and the items the EBITDA rules need (exceptional items, R&D tax credits, other operating income,
depreciation of leased assets) and the items for net debt (bank loans, finance leases, cash from operations).

Scanned accounts use the tuned scan reader (ocr_parse.parse). Digital accounts put each table cell on its own
line, so for them a label is matched first and the amounts are taken from the lines that follow.
Writes data/history/text_figures.csv (one row per filing). history.py turns this into years per company and
checks each middle year against the next filing.
Skills: deal-screening (preliminary financial assessment), information-gap-log.
"""
import os, re, glob, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_parse as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = [f'{ROOT}/data/history/text', f'{ROOT}/data/ocr/text']   # earlier first: the history copy wins
NUM = re.compile(r'\(?-?\d{1,3}(?:,\d{3})+\)?|\(?-?\d{4,}\)?')

EXTRA = {   # label at the start of a line -> what it is
    'exceptional': r'(exceptional|non[- ]recurring) (items?|costs?|charges?|expenses?)\b',
    'rdec': r'(research and development|r ?& ?d) expenditure credits?\b|\brdec\b',   # RDEC is booked above operating profit; SME tax credits sit in the tax charge
    'other_operating_income': r'other operating income\b',
    'rou_depreciation': r'depreciation (of|on) right[- ]of[- ]use|right[- ]of[- ]use assets? depreciation',
    'bank_loans': r'bank (loans?|borrowings?)( and overdrafts?)?\b',
    'finance_leases': r'(obligations under )?(finance leases?|hire purchase)( (and|&) hire purchase)?( contracts?| liabilities| obligations)?\b|lease liabilities\b',
    'other_borrowings': r'(loans and borrowings|interest[- ]bearing (loans|borrowings)|other loans|invoice (discounting|finance)( facility)?|loan notes)\b',
    'cash_from_operations': r'(net )?cash (generated|inflow)? ?from operat(ions|ing activities)\b|cash generated from operations\b',
    'depreciation': r'depreciation\b',
    'amortisation': r'amorti[sz]ation\b',
}
SKIP = re.compile(r'revalu|policy|accumulated|at \d|cost or|brought forward|carried forward|charged so|useful|straight line|reducing balance', re.I)


DASH = re.compile(r'(?<![\w,])[-–—](?![\w\d(])')


def amounts(line, small_ok):
    out = []
    pat = (r'\(?-?\d{1,3}(?:,\d{3})+\)?|\(?-?\d{4,}\)?' if not small_ok else r'\(?-?\d{1,3}(?:,\d{3})+\)?|\(?-?\d+\)?') + r'|(?<![\w,])[-–—](?![\w\d(])'
    for m in re.findall(pat, line):
        if m in ('-', '–', '—'):
            out.append(0.0)   # a dash in a column means nil for that year
            continue
        digits = re.sub(r'[^\d]', '', m)
        if not digits:
            continue
        v = float(digits)
        if ',' not in m and 1990 <= v <= 2035:
            continue   # a year in a heading
        if v >= 1000 or small_ok:
            out.append(-v if (m.startswith('(') or m.startswith('-')) else v)
    while small_ok and len(out) >= 3 and abs(out[0]) <= 40:
        out = out[1:]   # leading note numbers
    return out


def follow(lines, label, small_ok, start=0):
    """Amounts for the first line that starts with the label: on the same line, else on the next few number-only lines."""
    rx = re.compile(r'^\W{0,3}' + label, re.I)
    for i in range(start, len(lines)):
        l = lines[i]
        if not rx.search(l) or SKIP.search(l):
            continue
        rest = rx.sub('', l, count=1)
        nums = amounts(rest, small_ok)
        j = i + 1
        while not nums and j < min(len(lines), i + 5) and not re.search(r'[A-Za-z]{3,}', lines[j]):
            nums += amounts(lines[j], small_ok)
            j += 1
        if nums:
            return nums
    return None


def digital(text):
    """Digital accounts: one cell per line. Label first, then the current and prior-year amounts."""
    lines = [l.strip() for l in text.split('\n') if l.strip() and not l.startswith('=== page')]
    k = 1000 if any(re.search(r"£\s?['’]?000\b|£k\b", l) for l in lines[:4000]) else 1
    out = {}
    for key, label in (('turnover', r'(turnover|revenue)\s*$'), ('operating_profit', r'operating (profit|loss)(\s*/\s*\(?(profit|loss)\)?)?\s*$'),
                       ('profit_before_tax', r'(profit|loss)[^0-9]{0,40}before (income )?tax(ation)?\s*$')):
        nums = follow(lines, label, k > 1)
        if nums:
            out[key] = nums[0] * k
            if len(nums) > 1:
                out[key + '_prior'] = nums[1] * k
    out['_lines'], out['_k'] = lines, k
    return out


def scanned(text):
    o = P.parse(text)
    if 'problem' in o:
        return o
    P.checks(o)
    lines = [l.strip() for l in text.split('\n') if l.strip() and not l.startswith('=== page')]
    o['_lines'], o['_k'] = lines, {'£': 1, '000s': 1000, 'millions': 1_000_000}.get(o.get('unit'), 1)
    return o


def read(path):
    num, filed = os.path.basename(path)[:-4].rsplit('_', 1)
    text = open(path, errors='ignore').read()
    short = sum(1 for l in text.split('\n')[:3000] if 0 < len(l.strip()) < 25)
    is_digital = short > 0.6 * max(1, min(3000, text.count('\n')))
    o = digital(text) if is_digital else scanned(text)
    rec = {'CompanyNumber': num, 'filed': filed, 'reader': 'digital text' if is_digital else 'scan text', 'problem': o.get('problem', '')}
    if o.get('problem'):
        return rec
    lines, k = o.pop('_lines'), o.pop('_k')
    for key in ('turnover', 'turnover_prior', 'operating_profit', 'operating_profit_prior', 'profit_before_tax',
                'profit_before_tax_prior', 'da_total', 'cash', 'net_assets', 'period_text', 'unit'):
        if o.get(key) is not None:
            rec[key] = o[key]
    t, tp = rec.get('turnover'), rec.get('turnover_prior')
    if not t or t < 100_000:
        rec['problem'] = 'turnover not found'
        return rec
    for key in ('operating_profit', 'operating_profit_prior'):
        base = t if key == 'operating_profit' else tp
        if rec.get(key) is not None and (base is None or abs(rec[key]) > 1.5 * base):
            rec[key] = None
    for key, label in EXTRA.items():
        nums = follow(lines, label, k > 1)
        if nums and nums[0] != 0:
            v = abs(nums[0]) * k
            if v <= 0.6 * t:   # anything bigger than 60% of sales is a misread or a different line
                rec[key] = v
    if rec.get('da_total') is None and (rec.get('depreciation') or rec.get('amortisation')):
        rec['da_total'] = (rec.get('depreciation') or 0) + (rec.get('amortisation') or 0)
    rec['ifrs'] = bool(re.search(r'IFRS 16|right[- ]of[- ]use', text, re.I))
    return rec


def main():
    seen, rows = set(), []
    for d in DIRS:
        for path in sorted(glob.glob(f'{d}/*.txt')):
            key = os.path.basename(path)
            if key in seen:
                continue
            seen.add(key)
            try:
                rows.append(read(path))
            except Exception as e:   # one unreadable file must not stop the rest
                num, filed = key[:-4].rsplit('_', 1)
                rows.append({'CompanyNumber': num, 'filed': filed, 'problem': f'read error: {e}'})
    R = pd.DataFrame(rows)
    os.makedirs(f'{ROOT}/data/history', exist_ok=True)
    R.to_csv(f'{ROOT}/data/history/text_figures.csv', index=False)
    ok = R[R['problem'].fillna('') == '']
    print(f'Read {len(R)} filings: turnover for {len(ok)}, operating profit for {ok["operating_profit"].notna().sum()}, '
          f'prior-year operating profit for {ok.get("operating_profit_prior", pd.Series(dtype=float)).notna().sum()}')


if __name__ == '__main__':
    main()
