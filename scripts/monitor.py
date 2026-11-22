"""Weekly monitor: what changed at Companies House for every ranked company since the last check.

Checks new accounts, owners (PSC), charges (secured debt), directors and company status.
New accounts are read with the same parser as the original run and written into
data/inputs/financials_all.csv, so the clean and score steps that follow re-rank on fresh numbers.
Writes data/monitor/events.csv and updates data/monitor/state.json.
"""
import os, sys, json, datetime
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import accounts as A

ROOT = A.ROOT
MON = f'{ROOT}/data/monitor'
os.makedirs(MON, exist_ok=True)
STATE = f'{MON}/state.json'
today = datetime.date.today()
state = json.load(open(STATE)) if os.path.exists(STATE) else {}
lookback = int(os.environ.get('LOOKBACK_DAYS', '0') or 0)
since = (today - datetime.timedelta(days=lookback)).isoformat() if lookback else state.get('last_check', (today - datetime.timedelta(days=7)).isoformat())
print(f'Checking for changes since {since}')

R = pd.read_csv(f'{ROOT}/data/outputs/ranking_latest.csv', dtype={'CompanyNumber': str})
FIN_PATH = f'{ROOT}/data/inputs/financials_all.csv'
FIN = pd.read_csv(FIN_PATH, dtype={'CompanyNumber': str})
events, updated = [], []

def ev(num, name, kind, date, detail):
    events.append({'CompanyNumber': num, 'CompanyName': name, 'event': kind, 'date': date, 'detail': detail})

def items(path, **params):
    r = A.get(f'{A.API}/company/{path}', params=params)
    return r.json() if (r is not None and r.status_code == 200) else {}

for _, co in R.iterrows():
    num, name = co['CompanyNumber'], co['CompanyName']
    # status
    prof = items(num)
    st = prof.get('company_status')
    if st and st != 'active':
        ev(num, name, 'Status change', today.isoformat(), f'Company status is now "{st}"')
    # new accounts
    fh = items(f'{num}/filing-history', category='accounts', items_per_page=5).get('items', [])
    aa = [i for i in fh if i.get('type') == 'AA']
    if aa and aa[0].get('date', '') >= since:
        known = FIN.loc[FIN['CompanyNumber'] == num, 'accounts_filed']
        if known.empty or str(known.iloc[0]) != aa[0]['date']:
            row = A.read_latest_accounts(num)
            if row.get('turnover') is not None:
                for k, v in row.items():
                    if k in FIN.columns:
                        FIN.loc[FIN['CompanyNumber'] == num, k] = v
                updated.append(num)
                t = row['turnover']
                detail = f"New accounts filed (made up to {aa[0].get('description_values', {}).get('made_up_date', '?')}): turnover £{t/1e6:.1f}m"
                if row.get('turnover_growth') is not None:
                    detail += f" ({row['turnover_growth']:+.0%})"
                if row.get('ebitda_margin') is not None:
                    detail += f", EBITDA margin {row['ebitda_margin']:.0%}"
                if row.get('currency', 'GBP') != 'GBP':
                    detail += f" [reported in {row['currency']}: check before comparing]"
            else:
                detail = 'New accounts filed, but figures could not be read (PDF or untagged)'
            ev(num, name, 'New accounts', aa[0]['date'], detail)
    # owners
    for p in items(f'{num}/persons-with-significant-control', items_per_page=25).get('items', []):
        if (p.get('notified_on') or '') >= since:
            ev(num, name, 'New owner', p['notified_on'], f"{p.get('name', 'Unnamed')} registered as a person with significant control")
        if (p.get('ceased_on') or '') >= since:
            ev(num, name, 'Owner left', p['ceased_on'], f"{p.get('name', 'Unnamed')} ceased to be a person with significant control")
    # charges (secured debt)
    for c in items(f'{num}/charges', items_per_page=25).get('items', []):
        lender = ', '.join(x.get('name', '') for x in c.get('persons_entitled', [])) or 'lender not named'
        if (c.get('created_on') or '') >= since:
            ev(num, name, 'New charge', c['created_on'], f'Security registered in favour of {lender} (possible new borrowing)')
        if c.get('status') in ('fully-satisfied', 'satisfied') and (c.get('satisfied_on') or '') >= since:
            ev(num, name, 'Charge satisfied', c['satisfied_on'], f'Security for {lender} released (debt repaid or refinanced)')
    # directors
    for o in items(f'{num}/officers', items_per_page=50).get('items', []):
        role = o.get('officer_role', '')
        if 'director' not in role:
            continue
        if (o.get('appointed_on') or '') >= since:
            ev(num, name, 'Director appointed', o['appointed_on'], f"{o.get('name', '').title()} appointed")
        if (o.get('resigned_on') or '') >= since:
            ev(num, name, 'Director resigned', o['resigned_on'], f"{o.get('name', '').title()} resigned")

if updated:
    FIN.to_csv(FIN_PATH, index=False)
E = pd.DataFrame(events, columns=['CompanyNumber', 'CompanyName', 'event', 'date', 'detail']).sort_values('date', ascending=False)
E.to_csv(f'{MON}/events.csv', index=False)
json.dump({'last_check': today.isoformat(), 'checked_since': since, 'companies_checked': len(R),
           'accounts_updated': updated}, open(STATE, 'w'), indent=1)
print(f'Companies checked: {len(R)} | events: {len(E)} | accounts re-read: {len(updated)}')
print(E.groupby('event').size().to_string() if len(E) else 'No changes')
