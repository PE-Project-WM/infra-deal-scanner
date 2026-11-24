"""Fill figures read by OCR (data/ocr/ocr_financials.csv) into companies whose latest accounts are a scanned PDF.

Only used where the OCR'd filing is the same one recorded in financials_all.csv (same filing date), and only
where ocr_parse.py found no problem. Non-sterling accounts are converted to pounds (config/valuation.json rates).
The size band and shortlist status are then worked out with the same rules as the digital accounts.
"""
import os
import pandas as pd
from accounts import classify
from fx import rate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR = f'{ROOT}/data/ocr/ocr_financials.csv'
MONEY = ['turnover', 'turnover_prior', 'operating_profit', 'profit_before_tax', 'ebitda', 'cash', 'net_assets']

def apply_ocr(F):
    if not os.path.exists(OCR):
        return F
    O = pd.read_csv(OCR, dtype={'CompanyNumber': str}).set_index(['CompanyNumber', 'filed'])
    F = F.copy()
    n_read = n_failed = 0
    for i, r in F[F['format'] == 'pdf'].iterrows():
        key = (r['CompanyNumber'], str(r['accounts_filed']))
        if key not in O.index:
            continue
        o = O.loc[key]
        if isinstance(o, pd.DataFrame):
            o = o.iloc[-1]
        if isinstance(o['problem'], str) and o['problem']:
            F.at[i, 'status'] = 'PDF scan, OCR could not read the figures'
            n_failed += 1
            continue
        f = rate(o['currency']) if isinstance(o['currency'], str) else 1.0
        row = r.to_dict()
        for c in MONEY:
            row[c] = None if pd.isna(o[c]) else float(o[c]) * f
        row['ebitda_basis'] = o['ebitda_basis'] if isinstance(o['ebitda_basis'], str) else 'Not available'
        row['figures_source'] = 'OCR, check' + ('' if f == 1 else f" (converted from {o['currency']})")
        row['period_end'] = pd.to_datetime(o['period_text'], errors='coerce', dayfirst=True)
        row['period_end'] = None if pd.isna(row['period_end']) else row['period_end'].date().isoformat()
        row = classify(row)
        for k, v in row.items():
            if k in F.columns:
                F.at[i, k] = v
        n_read += 1
    print(f'OCR: figures filled for {n_read} scanned filings; {n_failed} could not be read')
    return apply_corrections(F)

FIX = f'{ROOT}/config/figure_corrections.csv'

def apply_corrections(F):
    """Figures checked by hand against the filing replace misread ones (config/figure_corrections.csv).

    One row per corrected field, in pounds (or the accounts currency for companies in company_currency.csv), for the filing named by its filing date. EBITDA, margin and
    status are then worked out again.
    """
    if not os.path.exists(FIX):
        return F
    X = pd.read_csv(FIX, dtype={'CompanyNumber': str, 'accounts_filed': str})
    n = 0
    for (num, filed), g in X.groupby(['CompanyNumber', 'accounts_filed']):
        idx = F.index[(F['CompanyNumber'] == num) & (F['accounts_filed'].astype(str) == filed)]
        for i in idx:
            row = F.loc[i].to_dict()
            for _, x in g.iterrows():
                row[x['field']] = x['value'] if x['field'] == 'ebitda_basis' else float(x['value'])
            row['figures_source'] = str(row.get('figures_source', '')).split(' (')[0].replace(', check', '') + ', corrected by hand'
            row = classify(row)
            for k, v in row.items():
                if k in F.columns:
                    F.at[i, k] = v
            n += 1
    print(f'Hand corrections applied to {n} filings')
    return F
