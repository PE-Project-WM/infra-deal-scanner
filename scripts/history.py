"""Step 04c: multi-year financial history for every company going forward (method v4).

Combines two sources, year by year:
  - tagged numbers from digital accounts (data/deep_dive/facts.csv and data/history/facts.csv), and
  - figures read from the text of each filing, scanned or digital (data/history/text_figures.csv, history_parse.py).
Each filing shows two years, so most years are read twice: once as "this year" and once, a year later, as the
comparative. Where both readings agree within 2% the year is marked confirmed. A latest filing whose comparative
matches the previous filing shows the reader found the right lines, which history_summary records.

Per company and year: sales, operating profit (profit before tax where operating profit is not shown), margin,
interest paid, capital spending and bank debt. Then a summary per company: years of history, sales growth per
year (CAGR), margin range and stability, interest cover, capex as a share of sales, and confirmation.
Used by score.py (growth, margin stability, interest cover, confidence), lenses.py, valuation.py and the website.
Skills: deal-screening (preliminary financial assessment).
"""
import os, re
import pandas as pd
from fx import to_gbp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f'{ROOT}/data/outputs'
FACTS = [f'{ROOT}/data/deep_dive/facts.csv', f'{ROOT}/data/history/facts.csv']
TEXT = f'{ROOT}/data/history/text_figures.csv'
FILINGS = [f'{ROOT}/data/deep_dive/filings.csv', f'{ROOT}/data/history/filings.csv']
TAGS = {
    'TurnoverRevenue': 'sales',
    'OperatingProfitLoss': 'operating_profit',
    'ProfitLossOnOrdinaryActivitiesBeforeTax': 'profit_before_tax',
    'InterestPayableSimilarChargesFinanceCosts': 'interest',
    'AdditionsOtherThanThroughBusinessCombinationsPropertyPlantEquipment': 'capex',
    'TotalAdditionsIncludingFromBusinessCombinationsPropertyPlantEquipment': 'capex_total',
    'BankBorrowings': 'bank_debt',
    'BankBorrowingsOverdrafts': 'bank_debt_overdraft',
    'FinanceLeaseLiabilitiesPresentValueTotal': 'finance_leases',
    'CashBankOnHand': 'cash',
}
MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
                                       'september', 'october', 'november', 'december'], 1)}


def read_many(paths):
    parts = [pd.read_csv(p, dtype={'CompanyNumber': str}) for p in paths if os.path.exists(p) and os.path.getsize(p) > 2]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def year_from_text(t):
    m = re.search(r'(\d{1,2})\w*\s+([A-Za-z]+)\s+(\d{4})', str(t or ''))
    if not m or m.group(2).lower() not in MONTHS:
        return None
    return int(m.group(3))


# 1. Tagged numbers: one row per company and financial year
F = read_many(FACTS)
tagged = pd.DataFrame()
if len(F):
    F = F[F['tag'].isin(TAGS) & F['has_dimension'].isna()].copy()
    F['fy'] = pd.to_datetime(F['period_end'], errors='coerce').dt.year
    F = F.dropna(subset=['fy']).sort_values('filed').drop_duplicates(['CompanyNumber', 'tag', 'period_end'], keep='last')
    tagged = (F.pivot_table(index=['CompanyNumber', 'fy'], columns='tag', values='value', aggfunc='last')
                .rename(columns=TAGS).reset_index())
    for c in TAGS.values():
        if c not in tagged:
            tagged[c] = pd.NA
    tagged['capex'] = tagged['capex'].fillna(tagged['capex_total'])
    tagged['bank_debt'] = tagged['bank_debt'].fillna(tagged['bank_debt_overdraft'])
    tagged = tagged.drop(columns=['capex_total', 'bank_debt_overdraft'])
    tagged['fy'] = tagged['fy'].astype(int)

# 2. Figures read from text: each filing gives this year and last year
readings = []
T = pd.read_csv(TEXT, dtype={'CompanyNumber': str}) if os.path.exists(TEXT) else pd.DataFrame()
FI = read_many(FILINGS)
made = {}
if len(FI) and 'made_up_to' in FI:
    for _, f in FI.dropna(subset=['made_up_to']).iterrows():
        made[(f['CompanyNumber'], str(f['filed']))] = pd.to_datetime(f['made_up_to'], errors='coerce').year
if len(T):
    T = T[T['problem'].fillna('') == '']
    for _, t in T.iterrows():
        fy = made.get((t['CompanyNumber'], str(t['filed']))) or year_from_text(t.get('period_text'))
        if not fy:
            fy = (pd.to_datetime(t['filed']) - pd.DateOffset(months=9)).year   # accounts are filed up to 9 months after the year end
        for lag, suffix in ((0, ''), (1, '_prior')):
            s = t.get('turnover' + suffix)
            if pd.notna(s):
                op = t.get('operating_profit' + suffix)
                pbt = t.get('profit_before_tax' + suffix)
                readings.append({'CompanyNumber': t['CompanyNumber'], 'fy': int(fy) - lag, 'filed': t['filed'], 'as': 'this year' if lag == 0 else 'comparative',
                                 'sales': s, 'operating_profit': op if pd.notna(op) else None, 'profit_before_tax': pbt if pd.notna(pbt) else None})
# The main accounts reader's figures for the latest filing count as one more reading (this year and last year)
CC = f'{OUT}/candidates_clean.csv'
if os.path.exists(CC):
    cc = pd.read_csv(CC, dtype={'CompanyNumber': str})
    fy_of = {}
    for r in readings:
        fy_of.setdefault((r['CompanyNumber'], str(r['filed'])), r['fy'] + (1 if r['as'] == 'comparative' else 0))
    for _, c in cc.iterrows():
        if pd.isna(c.get('turnover')) or pd.isna(c.get('accounts_filed')):
            continue
        filed = str(c['accounts_filed'])[:10]
        fy = fy_of.get((c['CompanyNumber'], filed)) or made.get((c['CompanyNumber'], filed)) or (pd.to_datetime(filed) - pd.DateOffset(months=9)).year
        readings.append({'CompanyNumber': c['CompanyNumber'], 'fy': int(fy), 'filed': filed, 'as': 'this year', 'sales': c['turnover'],
                         'operating_profit': c['operating_profit'] if pd.notna(c['operating_profit']) else None, 'profit_before_tax': None, 'reader': 'main'})
        if pd.notna(c.get('turnover_prior')):
            readings.append({'CompanyNumber': c['CompanyNumber'], 'fy': int(fy) - 1, 'filed': filed, 'as': 'comparative', 'sales': c['turnover_prior'],
                             'operating_profit': None, 'profit_before_tax': None, 'reader': 'main'})
Rd = pd.DataFrame(readings)
if len(Rd):
    Rd['reader'] = Rd.get('reader', pd.Series(index=Rd.index, dtype=object)).fillna('text')

# 3. Merge: tagged first; else the latest text reading; confirmed where two readings of a year agree within 2%
rows = []
keys = set()
if len(tagged):
    keys |= set(zip(tagged['CompanyNumber'], tagged['fy']))
if len(Rd):
    keys |= set(zip(Rd['CompanyNumber'], Rd['fy']))
tg = tagged.set_index(['CompanyNumber', 'fy']) if len(tagged) else pd.DataFrame()
for num, fy in sorted(keys):
    row = {'CompanyNumber': num, 'fy': fy}
    tr = tg.loc[(num, fy)] if len(tg) and (num, fy) in tg.index else None
    rr = Rd[(Rd['CompanyNumber'] == num) & (Rd['fy'] == fy)].sort_values('filed') if len(Rd) else pd.DataFrame()
    if tr is not None and pd.notna(tr['sales']):
        row.update({c: tr[c] for c in TAGS.values() if c in tr.index and c not in ('capex_total', 'bank_debt_overdraft')})
        row['source'] = 'tagged'
    elif len(rr):
        # each figure from the best reading that has it: this year's column first, then the comparative a year later
        order = pd.concat([rr[rr['as'] == 'this year'].iloc[::-1], rr[rr['as'] != 'this year'].iloc[::-1]])
        pick = lambda col: next((v for v in order[col] if v is not None and pd.notna(v)), None)
        op = pick('operating_profit')
        row.update(sales=pick('sales'), operating_profit=op, profit_before_tax=None if op is not None else pick('profit_before_tax'))
        row['source'] = 'text'
        if tr is not None:   # tagged balance items still useful
            for c in ('interest', 'capex', 'bank_debt', 'finance_leases', 'cash'):
                if c in tr.index:
                    row[c] = tr[c]
    else:
        continue
    # a year is confirmed when two different filings agree on its sales within 2% (two readers of one filing do not count)
    by_filing = rr.groupby('filed')['sales'].first().tolist() if len(rr) else []
    if tr is not None and pd.notna(tr['sales']) and not by_filing:
        by_filing = [tr['sales']]
    row['readings'] = len(by_filing)
    row['confirmed'] = len(by_filing) >= 2 and (max(by_filing) - min(by_filing)) <= 0.02 * max(abs(v) for v in by_filing)
    rows.append(row)

H = pd.DataFrame(rows)
if not len(H):
    print('No history yet; skipping.')
    raise SystemExit(0)
for c in ['sales', 'operating_profit', 'profit_before_tax', 'interest', 'capex', 'bank_debt', 'finance_leases', 'cash']:
    if c not in H:
        H[c] = pd.NA
    H[c] = pd.to_numeric(H[c], errors='coerce') * H['CompanyNumber'].map(to_gbp)   # accounts in another currency
H['profit'] = H['operating_profit'].fillna(H['profit_before_tax'])
H['profit_basis'] = H['operating_profit'].notna().map({True: 'Operating profit', False: 'Profit before tax'})
H['margin'] = H['profit'] / H['sales']
H = H.sort_values(['CompanyNumber', 'fy'])
names = {}
for p in (f'{OUT}/candidates_clean.csv',):
    if os.path.exists(p):
        c = pd.read_csv(p, dtype={'CompanyNumber': str})
        names = dict(zip(c['CompanyNumber'], c['CompanyName']))
H.insert(1, 'CompanyName', H['CompanyNumber'].map(names))
# Keep only consecutive years ending at the latest one (a gap means a missing or changed year end)
keep = []
for num, g in H.groupby('CompanyNumber'):
    g = g.sort_values('fy')
    run = [g.index[-1]]
    for i in range(len(g) - 2, -1, -1):
        if g['fy'].iloc[i] == g['fy'].iloc[i + 1] - 1:
            run.append(g.index[i])
        else:
            break
    keep += run
H = H.loc[sorted(keep)]
H.to_csv(f'{OUT}/history.csv', index=False)

rows = []
for num, g in H.groupby('CompanyNumber'):
    s = g.dropna(subset=['sales'])
    m = g.dropna(subset=['margin'])
    last = g.iloc[-1]
    years = len(s)
    cagr = (s['sales'].iloc[-1] / s['sales'].iloc[0]) ** (1 / (years - 1)) - 1 if years >= 3 and s['sales'].iloc[0] > 0 else None
    growth_1y = s['sales'].iloc[-1] / s['sales'].iloc[-2] - 1 if years >= 2 and s['sales'].iloc[-2] > 0 else None
    interest = g.dropna(subset=['interest'])
    cover = None
    if len(interest) and pd.notna(last['profit']) and interest['interest'].iloc[-1] > 0:
        cover = (float(last['profit'] + interest['interest'].iloc[-1]) / float(interest['interest'].iloc[-1]) if last['profit_basis'] == 'Profit before tax'
                 else float(last['profit']) / float(interest['interest'].iloc[-1]))
    capex_share = (g['capex'] / g['sales']).dropna()
    prev = g.iloc[-2] if len(g) >= 2 else None
    rows.append({
        'CompanyNumber': num, 'CompanyName': g['CompanyName'].iloc[0],
        'years_of_sales': years, 'first_year': int(s['fy'].iloc[0]) if years else None, 'last_year': int(s['fy'].iloc[-1]) if years else None,
        'sales_cagr': cagr, 'growth_1y': growth_1y,
        'years_of_margin': len(m),
        'margin_min': m['margin'].min() if len(m) else None, 'margin_max': m['margin'].max() if len(m) else None,
        'margin_swing_pp': (m['margin'].max() - m['margin'].min()) * 100 if len(m) >= 3 else None,
        'margin_prior_avg': m['margin'].iloc[:-1].mean() if len(m) >= 2 else None,
        'margin_basis': m['profit_basis'].iloc[-1] if len(m) else None,
        'interest_latest': interest['interest'].iloc[-1] if len(interest) else None,
        'interest_cover': cover,
        'capex_share_avg': capex_share.mean() if len(capex_share) else None,
        'bank_debt_latest': g['bank_debt'].dropna().iloc[-1] if g['bank_debt'].notna().any() else None,
        'sources': '+'.join(sorted(set(g['source']))),
        'confirmed_years': int(g['confirmed'].sum()),
        'latest_line_confirmed': bool(prev is not None and prev['confirmed']),
    })
S = pd.DataFrame(rows)
S.to_csv(f'{OUT}/history_summary.csv', index=False)
print(f'Saved history.csv ({len(H)} company-years) and history_summary.csv ({len(S)} companies)')
print('Years of sales read:', S['years_of_sales'].value_counts().sort_index().to_dict())
print('Companies with a year confirmed by two filings:', int((S['confirmed_years'] > 0).sum()))
