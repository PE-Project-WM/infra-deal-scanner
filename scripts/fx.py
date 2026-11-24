"""Currency helper: companies whose accounts are not in pounds, and the rate used to convert them.

config/company_currency.csv lists the exceptions (everything else is taken as GBP);
the rates come from fx_to_gbp in config/valuation.json. Used by history, score, profiles and valuation,
so every figure the ranking compares is in pounds.
"""
import os, json
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RATES = json.load(open(f'{ROOT}/config/valuation.json')).get('fx_to_gbp', {'GBP': 1.0})
_P = f'{ROOT}/config/company_currency.csv'
CURRENCY = (pd.read_csv(_P, dtype={'CompanyNumber': str}).set_index('CompanyNumber')['currency'].to_dict()
            if os.path.exists(_P) else {})

def currency(num):
    return CURRENCY.get(str(num), 'GBP')

def rate(cur):
    return float(RATES.get(cur, 1.0))

def to_gbp(num):
    """Multiplier that turns a company's reported figures into pounds."""
    return rate(currency(num))

def label(num):
    cur = currency(num)
    if cur == 'GBP':
        return ''
    per = 1 / rate(cur)
    return f'converted from {cur} at {per:.2f} per £'
