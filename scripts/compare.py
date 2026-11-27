"""Compare this run's ranking with the previous one and explain every move.

Reasons come from the per-criterion points (scripts/score.py) plus the week's Companies House events.
Writes data/updates/update_<date>.json and .md, and data/updates/latest.json for the website.
"""
import os, json, datetime
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, UPD = f'{ROOT}/data/outputs', f'{ROOT}/data/updates'
os.makedirs(UPD, exist_ok=True)
today = datetime.date.today().isoformat()
from settings import C
KEYS = list(C['scoring_weights'])
LABEL = {k: k.replace('_', ' ') for k in KEYS}

new = pd.read_csv(f'{OUT}/ranking_latest.csv', dtype={'CompanyNumber': str})
prev_path = f'{ROOT}/data/monitor/previous_ranking.csv'
prev = pd.read_csv(prev_path, dtype={'CompanyNumber': str}) if os.path.exists(prev_path) else new.copy()
ev_path = f'{ROOT}/data/monitor/events.csv'
E = pd.read_csv(ev_path, dtype={'CompanyNumber': str}) if os.path.exists(ev_path) else pd.DataFrame(columns=['CompanyNumber', 'CompanyName', 'event', 'date', 'detail'])
clean = pd.read_csv(f'{OUT}/candidates_clean.csv', dtype={'CompanyNumber': str})
state = json.load(open(f'{ROOT}/data/monitor/state.json')) if os.path.exists(f'{ROOT}/data/monitor/state.json') else {}

P = prev.set_index('CompanyNumber'); N = new.set_index('CompanyNumber')
import re as _re
def nice(s):
    stop = {'THE', 'AND', 'FOR', 'OF', 'LTD'}
    t = ' '.join(w if (len(w.strip('()')) <= 3 and w.strip('()').isalpha() and w.strip('()') not in stop) else w.title() for w in str(s).split())
    t = t.replace("'S", "'s")
    t = _re.sub(r'\s+(Limited|Ltd\.?|Plc)$', '', t)
    t = _re.sub(r'\bUk\b', 'UK', t)
    t = _re.sub(r'\(([A-Za-z]{2,4})\)', lambda m: '(' + m.group(1).upper() + ')', t)
    return t.replace('Ca Telecom', 'CA Telecom').replace('C.A.', 'C.A.')

METHOD_NOW = str(new['method_version'].iloc[0]) if 'method_version' in new else 'v1'
METHOD_PREV = str(prev['method_version'].iloc[0]) if 'method_version' in prev else 'v1'
METHOD_CHANGED = METHOD_NOW != METHOD_PREV

def component_reasons(n, p):
    if METHOD_CHANGED:   # points are not comparable across scoring methods
        return [f'scoring method changed ({METHOD_PREV} to {METHOD_NOW})']
    out = []
    for k in KEYS:
        d = float(n[f'pts_{k}']) - float(p[f'pts_{k}'])
        if abs(d) >= 0.5:
            out.append((abs(d), f'{LABEL[k]} {d:+.1f}'))
    return [t for _, t in sorted(out, reverse=True)]

def context(n, p):
    out = []
    if n['relevance'] != p['relevance']:
        out.append(f"thesis fit {p['relevance']} → {n['relevance']}")
    if str(n['accessibility']).split(':')[0] != str(p['accessibility']).split(':')[0]:
        out.append(f"accessibility now {str(n['accessibility']).split(':')[0]}")
    for col, lab, fmt in (('turnover', 'turnover', lambda v: f'£{v/1e6:.1f}m'), ('ebitda_margin', 'margin', lambda v: f'{v:.0%}')):
        if pd.notna(n.get(col)) and pd.notna(p.get(col)) and abs(n[col] - p[col]) > 1e-9:
            out.append(f'{lab} {fmt(p[col])} → {fmt(n[col])}')
    return out

moves = []
for num in sorted(set(N.index) | set(P.index)):
    evs = E[E['CompanyNumber'] == num]
    evtext = [f"{r['event']} ({r['date']}): {r['detail']}" for _, r in evs.iterrows()]
    if num in N.index and num in P.index:
        n, p = N.loc[num], P.loc[num]
        dr = int(p['rank']) - int(n['rank'])
        ds = round(float(n['score']) - float(p['score']), 1)
        reasons = context(n, p) + component_reasons(n, p)
        if dr == 0 and abs(ds) < 0.1 and not evtext:
            continue
        kind = 'up' if dr > 0 else 'down' if dr < 0 else 'same'
        if dr != 0 and not reasons:
            reasons = ['moved because companies around it entered or left the ranking']
        moves.append({'company': nice(n['CompanyName']), 'number': num, 'kind': kind, 'from': int(p['rank']), 'to': int(n['rank']),
                      'score_from': float(p['score']), 'score_to': float(n['score']), 'reasons': reasons, 'events': evtext})
    elif num in N.index:
        n = N.loc[num]
        moves.append({'company': nice(n['CompanyName']), 'number': num, 'kind': 'new', 'from': None, 'to': int(n['rank']),
                      'score_from': None, 'score_to': float(n['score']),
                      'reasons': [f"entered the ranking ({n['relevance']} fit, {str(n['accessibility']).split(':')[0].lower()} accessibility)"], 'events': evtext})
    else:
        p = P.loc[num]
        why = clean.loc[clean['CompanyNumber'] == num, 'excluded_reason']
        why = why.iloc[0] if len(why) and isinstance(why.iloc[0], str) and why.iloc[0] else (
            'needs a sector check before it can be ranked (new sector gate)' if METHOD_CHANGED and num in set(pd.read_csv(f'{OUT}/sector_check.csv', dtype={'CompanyNumber': str})['CompanyNumber'])
            else 'no longer on the profitable shortlist')
        moves.append({'company': nice(p['CompanyName']), 'number': num, 'kind': 'out', 'from': int(p['rank']), 'to': None,
                      'score_from': float(p['score']), 'score_to': None, 'reasons': [why], 'events': evtext})

top_now = new.head(10)
top_prev = prev.head(10)
in_top = sorted(set(top_now['CompanyNumber']) - set(top_prev['CompanyNumber']))
out_top = sorted(set(top_prev['CompanyNumber']) - set(top_now['CompanyNumber']))
touch_top = sorted([m for m in moves if (m['to'] and m['to'] <= 10) or (m['from'] and m['from'] <= 10)], key=lambda m: (m['to'] or 99, m['from'] or 99))
headline = (f"{len(in_top)} new in the top 10, {len(out_top)} dropped out, {len([m for m in touch_top if m['kind'] in ('up', 'down')])} moved within it"
            if (in_top or out_top or touch_top) else 'No changes to the top 10 this week')
if METHOD_CHANGED:
    headline = f"Scoring method updated ({METHOD_NOW}): {headline[0].lower() + headline[1:]}"
update = {
    'date': today, 'checked_since': state.get('checked_since'), 'previous_scored_on': str(prev['scored_on'].iloc[0]) if 'scored_on' in prev else None,
    'headline': headline, 'method_changed': METHOD_CHANGED, 'method_version': METHOD_NOW, 'events_count': int(len(E)), 'companies_checked': state.get('companies_checked', len(new)),
    'top10': [{'rank': int(r['rank']), 'company': nice(r['CompanyName']), 'score': float(r['score']), 'fit': r['relevance'],
               'segment': r['segment'], 'turnover': float(r['turnover']), 'margin': float(r['ebitda_margin']) if pd.notna(r['ebitda_margin']) else None,
               'access': str(r['accessibility']).split(':')[0], 'access_note': str(r['accessibility']).split(': ', 1)[-1],
               'town': str(r.get('RegAddress.PostTown', '')).title(),
               'confidence': r.get('confidence'),
               'pts': {k: float(r[f'pts_{k}']) for k in KEYS}} for _, r in top_now.iterrows()],
    'top10_moves': touch_top, 'all_moves': moves,
    'events': E.head(40).to_dict('records'),
    'ranked': int(len(new)),
}
json.dump(update, open(f'{UPD}/update_{today}.json', 'w'), indent=1, default=str)
json.dump(update, open(f'{UPD}/latest.json', 'w'), indent=1, default=str)

lines = [f'# Weekly update: {today}', '', f'**{headline}.** Checked {update["companies_checked"]} ranked companies for changes since {update["checked_since"]}; {len(E)} Companies House events found.', '']
if touch_top:
    lines += ['## Top 10 changes', '']
    for m in touch_top:
        arrow = {'up': f"{m['from']} → {m['to']}", 'down': f"{m['from']} → {m['to']}", 'new': f"new at {m['to']}", 'out': f"{m['from']} → out", 'same': f"stays {m['to']}"}[m['kind']]
        lines.append(f"- **{m['company']}** ({arrow}): {'; '.join(m['reasons'])}" + (f" Events: {' | '.join(m['events'])}" if m['events'] else ''))
    lines.append('')
lines += ['## Current top 10', '', '| Rank | Company | Score | Fit | Accessibility |', '| --- | --- | --- | --- | --- |']
lines += [f"| {t['rank']} | {t['company']} | {t['score']:.1f} | {t['fit']} | {t['access']} |" for t in update['top10']]
if len(E):
    lines += ['', '## Companies House events', ''] + [f"- {r['date']} · {nice(r['CompanyName'])} · {r['event']}: {r['detail']}" for _, r in E.head(25).iterrows()]
lines += ['', '*Illustrative analysis from public Companies House data (Open Government Licence v3.0). Not investment advice.*']
open(f'{UPD}/update_{today}.md', 'w').write('\n'.join(lines))
print('\n'.join(lines[:30]))
