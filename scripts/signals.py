"""Exit and refinancing signals from the weekly Companies House events (data/updates/latest.json).

Some filings often come before or with a sale or a new debt package:
  - a change of owner (a person with significant control added or removed),
  - several directors appointed or resigning on the same day (boards are usually replaced at completion),
  - a new charge (security for a loan), especially in favour of a security agent or a private equity or debt fund,
  - a charge satisfied and a new one registered close together (refinancing).
A signal is a reason to look, never proof that anything happened. Names of individuals are left out.
Writes data/outputs/signals.json (this week) and adds new signals to data/outputs/signals_history.csv, so they build up over time
(useful for the back-test: a signal followed by a confirmed deal is a data point).
"""
import os, json, re, datetime
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U = json.load(open(f'{ROOT}/data/updates/latest.json'))
SPONSOR = re.compile(r'security agent|security trustee|private equity|capital|partners|credit|debt|fund|LLP', re.I)
BANK = re.compile(r'\bbank\b|barclays|lloyds|natwest|national westminster|hsbc|santander', re.I)

by_co = defaultdict(list)
for ev in U.get('events') or []:
    by_co[(ev['CompanyNumber'], ev['CompanyName'])].append(ev)

def nice(n):
    t = ' '.join(w.title() if len(w) > 3 else w for w in n.split())
    return re.sub(r'\s+(Limited|Ltd\.?|Plc)$', '', t, flags=re.I)

signals = []
for (num, name), evs in by_co.items():
    day = defaultdict(list)
    for ev in evs:
        day[ev['date']].append(ev)
    owners = [ev for ev in evs if ev['event'].startswith('Owner')]
    if owners:
        same_day_board = [ev for ev in day[owners[0]['date']] if ev['event'].startswith('Director')]
        strong = len(same_day_board) >= 2
        signals.append({'number': num, 'company': nice(name), 'date': max(ev['date'] for ev in owners),
                        'signal': 'Possible change of ownership', 'strength': 'strong' if strong else 'moderate',
                        'why': ('Owners changed and the board was reshaped on the same day, which usually happens when a sale completes'
                                if strong else 'A person with significant control was added or removed'),
                        'evidence': f"{len(owners)} owner {'change' if len(owners) == 1 else 'changes'}" + (f", {len(same_day_board)} director changes the same day" if strong else '')})
    for d, evs_d in day.items():
        board = [ev for ev in evs_d if ev['event'].startswith('Director')]
        if len(board) >= 3 and not (owners and d == owners[0]['date']):
            signals.append({'number': num, 'company': nice(name), 'date': d, 'signal': 'Board reshaped', 'strength': 'moderate',
                            'why': 'Several directors changed on one day; this often follows a sale, a refinancing or a group reorganisation',
                            'evidence': f'{len(board)} director changes on one day'})
    new = [ev for ev in evs if ev['event'] == 'New charge']
    done = [ev for ev in evs if ev['event'] == 'Charge satisfied']
    if new:
        lenders = '; '.join(sorted({re.sub(r'^Security registered in favour of\s*', '', ev['detail']).replace(' (possible new borrowing)', '') for ev in new}))
        sponsor = any(SPONSOR.search(ev['detail']) and not BANK.search(ev['detail']) for ev in new)
        if done and sponsor:
            sig, why = 'Refinancing with a fund or security agent', 'Old security released and new security registered in favour of a security agent or fund, which often comes with a buyout or a private credit loan'
        elif done:
            sig, why = 'Refinancing', 'Old security released and new security registered: debt repaid and replaced'
        elif sponsor:
            sig, why = 'New debt from a fund or security agent', 'Security in favour of a security agent, fund or private equity firm, which often comes with a buyout or a private credit loan'
        else:
            sig, why = 'New bank borrowing', 'A lender registered security over the company, usually for a new loan or facility'
        signals.append({'number': num, 'company': nice(name), 'date': max(ev['date'] for ev in new), 'signal': sig,
                        'strength': 'strong' if sponsor or done else 'weak', 'why': why,
                        'evidence': f"{len(new)} new {'charge' if len(new) == 1 else 'charges'} ({lenders})" + (f", {len(done)} released" if done else '')})

order = {'strong': 0, 'moderate': 1, 'weak': 2}
signals.sort(key=lambda s: (order[s['strength']], s['date']), reverse=False)
signals.sort(key=lambda s: order[s['strength']])
out = {'built': datetime.date.today().isoformat(), 'events_since': U.get('checked_since'), 'signals': signals,
       '_about': 'Signals are reasons to look, not proof. Names of individuals are left out.'}
json.dump(out, open(f'{ROOT}/data/outputs/signals.json', 'w'), indent=1)
import pandas as pd
HIST = f'{ROOT}/data/outputs/signals_history.csv'
new = pd.DataFrame(signals)
if len(new):
    new['found_on'] = out['built']
    old = pd.read_csv(HIST, dtype={'number': str}) if os.path.exists(HIST) else pd.DataFrame(columns=new.columns)
    both = pd.concat([old, new], ignore_index=True).drop_duplicates(['number', 'date', 'signal'], keep='first')
    both.to_csv(HIST, index=False)
print(f'Signals: {len(signals)} from {sum(len(v) for v in by_co.values())} events')
for s in signals:
    print(f"  {s['strength']:8} {s['company']}: {s['signal']} ({s['evidence']})")
