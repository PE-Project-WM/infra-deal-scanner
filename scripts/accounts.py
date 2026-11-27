"""Shared Companies House helpers and the accounts parser (same logic as the 03 financials notebook).

Used by the weekly monitor to read newly filed accounts exactly as the original run did.
"""
import os, re, time, json, requests
import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from settings import C   # the sector's thesis settings (config/thesis/<sector>.json)
KEY = os.environ.get('CH_API_KEY', '').strip()

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

def latest_accounts(num):
    r = get(f'{API}/company/{num}/filing-history', params={'category': 'accounts', 'items_per_page': 10})
    if r is None or r.status_code != 200:
        return None, f'filing history error {getattr(r, "status_code", "none")}'
    for item in r.json().get('items', []):
        meta = item.get('links', {}).get('document_metadata')
        if item.get('type') == 'AA' and meta:   # AA = accounts; skips AA01 year-end changes
            return item, None
    return None, 'no accounts document'

def fetch_document(meta_url):
    doc_id = meta_url.rstrip('/').split('/')[-1]
    m = get(DOC_API + doc_id)
    if m is None or m.status_code != 200:
        return None, None, f'metadata error {getattr(m, "status_code", "none")}'
    resources = m.json().get('resources', {})
    if 'application/xhtml+xml' in resources:
        c = get(DOC_API + doc_id + '/content', headers={'Accept': 'application/xhtml+xml'})
        if c is not None and c.status_code == 200:
            return c.content, 'ixbrl', None
        return None, None, f'content error {getattr(c, "status_code", "none")}'
    if 'application/pdf' in resources:
        return None, 'pdf', None
    return None, None, 'no readable format'

TAGS = {
    'turnover':          ['TurnoverRevenue', 'Revenue', 'Turnover'],
    'operating_profit':  ['OperatingProfitLoss', 'ProfitLossFromOperatingActivities'],
    'profit_before_tax': ['ProfitLossOnOrdinaryActivitiesBeforeTax', 'ProfitLossBeforeTax'],
    'da_total':          ['DepreciationAmortisationImpairmentExpense', 'DepreciationAndAmortisationExpense',
                          'DepreciationAmortisationExpense'],
    'depreciation':      ['DepreciationExpensePropertyPlantEquipment',
                          'DepreciationImpairmentExpensePropertyPlantEquipment'],
    'amortisation':      ['AmortisationExpenseIntangibleAssets', 'AmortisationImpairmentExpenseIntangibleAssets'],
    'cash':              ['CashBankOnHand', 'CashAndCashEquivalents', 'Cash'],
    'net_assets':        ['NetAssetsLiabilities', 'Equity'],
    'employees':         ['AverageNumberEmployeesDuringPeriod'],
    'staff_costs':       ['StaffCostsEmployeeBenefitsExpense'],
    'gross_profit':      ['GrossProfitLoss'],
}
LOOKUP = {name: metric for metric, names in TAGS.items() for name in names}

def to_number(tag, use_scale=True):
    text = tag.get_text().strip()
    fmt = (tag.get('format') or '').lower()
    if text in ('', '-', '\u2013', '\u2014') or 'zero' in fmt:
        return 0.0
    if any(f in fmt for f in ('numcommadecimal', 'num-comma-decimal', 'numdotcomma')):   # e.g. 1.234,5
        text = text.replace('.', '').replace(' ', '').replace(',', '.')
    else:
        text = text.replace(',', '').replace(' ', '')
    try:
        value = float(text) * (10 ** int(tag.get('scale') or 0) if use_scale else 1)
    except ValueError:
        return None
    return -value if tag.get('sign') == '-' else value

def parse_ixbrl(raw):
    soup = BeautifulSoup(raw, 'lxml')   # forgiving parser; the XML warning is silenced in Setup
    contexts = {}
    for c in soup.find_all(lambda t: t.name and t.name.endswith('context')):
        has_dimension = c.find(lambda t: t.name and (t.name.endswith('segment') or t.name.endswith('scenario')))
        end = c.find(lambda t: t.name and (t.name.endswith('enddate') or t.name.endswith('instant')))
        if end is not None and not has_dimension:
            contexts[c.get('id')] = end.get_text().strip()
    facts = {}
    for t in soup.find_all(lambda t: t.name and t.name.endswith('nonfraction')):
        metric = LOOKUP.get((t.get('name') or '').split(':')[-1])
        end = contexts.get(t.get('contextref'))
        if metric and end:
            value = to_number(t, use_scale=(metric != 'employees'))   # some software scales headcount oddly
            if value is not None:
                facts.setdefault(metric, {}).setdefault(end, value)
    out = {}
    for metric, by_date in facts.items():
        dates = sorted(by_date, reverse=True)
        out[metric] = by_date[dates[0]]
        out[metric + '_prior'] = by_date[dates[1]] if len(dates) > 1 else None
        if metric == 'turnover':
            out['period_end'] = dates[0]
    return out

def add_ebitda(row):
    op = row.get('operating_profit')
    da = row.get('da_total')
    if da is None and (row.get('depreciation') is not None or row.get('amortisation') is not None):
        da = abs(row.get('depreciation') or 0) + abs(row.get('amortisation') or 0)
    if op is not None and da is not None:
        row['ebitda'], row['ebitda_basis'] = op + abs(da), 'Operating profit + D&A'
    elif op is not None:
        row['ebitda'], row['ebitda_basis'] = op, 'ESTIMATE: operating profit only (no D&A tagged)'
    else:
        row['ebitda'], row['ebitda_basis'] = None, 'Not available'
    return row

# Backup: some accounts software doesn't tag the P&L, so read it from the text instead.
# Finds a line that is just 'Turnover' (or 'Revenue', 'Operating profit') and takes the numbers
# on that line and the few lines below it, current year first, prior year second.
NUM = re.compile(r'\(?-?\d{1,3}(?:,\d{3})+\)?|\(?-?\d{4,}\)?')
LABELS = {
    'turnover':         r'(turnover|revenue)',
    'operating_profit': r'operating (profit|loss)(\s*/\s*\(?(profit|loss)\)?)?',
}

def _numbers_after(lines, i):
    found = []
    for j, l in enumerate(lines[i:i + 6]):
        if j > 0 and re.search(r'[A-Za-z]{3,}', l):
            break
        for m in NUM.findall(l):
            plain = m.strip('()').replace(',', '').lstrip('-')
            v = float(plain)
            if ',' not in m and 1990 <= v <= 2035:
                continue   # a year in a column heading, not an amount
            if v >= 1000:   # skips note numbers like 3 or 12
                found.append(-v if (m.startswith('(') or m.startswith('-')) else v)
    return found

def from_text(raw):
    text = BeautifulSoup(raw, 'lxml').get_text('\n')
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    in_thousands = any(re.search(r"£\s?['’]?000\b|£k\b", l) for l in lines)
    out = {}
    for metric, label in LABELS.items():
        pattern = re.compile(label + r'[\s\d,().£-]*', re.I)
        for i, l in enumerate(lines):
            if pattern.fullmatch(l):
                nums = _numbers_after(lines, i)
                if nums:
                    k = 1000 if in_thousands else 1
                    out[metric] = nums[0] * k
                    out[metric + '_prior'] = nums[1] * k if len(nums) > 1 else None
                    break
    if 'turnover' in out:
        out['figures_source'] = 'FROM TEXT, check' + (' (read as £000s)' if in_thousands else '')
    return out

DC_WORDS = r'DATA ?CENT|DATACENT|HOSTING|COLO|CLOUD|SERVER|NETWORK|FIBRE|CONNECT|TELECOM|INFRA'

def classify(r):
    """Size band and shortlist status for one company row (same rules as notebook 03)."""
    band = C['size_band_gbp']
    t, tp, e = r.get('turnover'), r.get('turnover_prior'), r.get('ebitda')
    r['in_size_band'] = t is not None and band['turnover_min'] <= t <= band['turnover_max']
    r['ebitda_margin'] = round(e / t, 3) if (e is not None and t) else None
    r['turnover_growth'] = round(t / tp - 1, 3) if (t is not None and tp) else None
    if t is None:
        r['status'] = {'ixbrl': 'Digital accounts, turnover not found', 'pdf': 'PDF scan (check by hand or OCR later)'}.get(r.get('format'), 'No accounts found')
    elif not r['in_size_band']:
        r['status'] = 'Outside size band'
    elif e is None:
        r['status'] = 'In band, EBITDA unknown'
    else:
        r['status'] = 'Shortlist' if e > 0 else 'Watchlist (loss-making)'
    return r

CURRENCY = re.compile(r'(presentation|functional|reporting) currency[^.]{0,160}', re.I)

def currency_of(raw):
    """'GBP' unless the accounts say they are presented in another currency (Version 2 check)."""
    text = BeautifulSoup(raw, 'lxml').get_text(' ')
    for m in CURRENCY.finditer(text):
        s = m.group(0).lower()
        if 'sterling' in s or '£' in s or 'gbp' in s:
            return 'GBP'
        for code, words in (('USD', ('us dollar', 'united states dollar', 'usd')), ('EUR', ('euro', 'eur'))):
            if any(w in s for w in words):
                return code
    return 'GBP'

def read_latest_accounts(num):
    """Fetch and parse a company's latest filed accounts into one row (financials_all format)."""
    row = {'CompanyNumber': num}
    item, err = latest_accounts(num)
    if item:
        row['accounts_type'] = item.get('type')
        row['accounts_filed'] = item.get('date')
        row['accounts_kind'] = (item.get('description') or '').replace('accounts-with-accounts-type-', '')
        raw, fmt, err = fetch_document(item['links']['document_metadata'])
        row['format'] = fmt
        if raw:
            try:
                row.update(parse_ixbrl(raw))
                if row.get('turnover') is not None:
                    row['figures_source'] = 'Tagged'
                else:
                    for k, v in from_text(raw).items():
                        if row.get(k) is None:
                            row[k] = v
                row['currency'] = currency_of(raw)
            except Exception as e:
                err = f'parse error: {e}'
    row['error'] = err
    return classify(add_ebitda(row))
