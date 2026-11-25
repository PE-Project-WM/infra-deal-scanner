"""Northing: build the public website and its data files (docs/, served by GitHub Pages).

Every page is plain HTML written here, so people, search engines and AI agents can all read it without
running JavaScript. The same facts are published as JSON and CSV under docs/api/v1/, described on the
Data & API page and in docs/llms.txt. Called at the end of scripts/site.py with the data it assembles.
"""
import os, re, json, html, shutil, datetime, csv, io
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DOCS = f'{ROOT}/docs'
S = json.load(open(f'{ROOT}/config/site.json'))
BASE = S['base_url']
API = f"api/{S['api_version']}"
CH = 'https://find-and-update.company-information.service.gov.uk/company/'
OGL = 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/'

e = lambda s: html.escape('' if s is None else str(s), quote=True)
def isnum(v):
    return v is not None and not (isinstance(v, float) and v != v)
def money(v, dp=1):
    if not isnum(v):
        return '–'
    v = float(v)
    s = f'£{abs(v) / 1e6:,.{dp}f}m' if abs(v) < 1e9 else f'£{abs(v) / 1e9:,.2f}bn'
    return ('−' if v < 0 else '') + s
def pct(v):
    return '–' if not isnum(v) else f'{round(float(v) * 100):.0f}%'
def fdate(d, short=False):
    try:
        x = datetime.date.fromisoformat(str(d)[:10])
    except ValueError:
        return str(d)
    return f"{x.day} {x.strftime('%b' if short else '%B')} {x.year}"
def cap(s):
    s = str(s or '').strip()
    return s[:1].upper() + s[1:]
def nz(v):
    return None if not isnum(v) else v
def clean_json(o):   # no NaN in published JSON
    if isinstance(o, dict):
        return {k: clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    if isinstance(o, float) and o != o:
        return None
    if hasattr(o, 'item'):
        return clean_json(o.item())
    return o

NAMES_RE = re.compile(r'^(Director (appointed|resigned)|Owner (left|added)|Person with significant control).*', re.I)
def event_text(ev):
    """Weekly events without the names of individuals (directors and owners are people)."""
    kind, detail = ev.get('event', ''), ev.get('detail', '')
    if kind.startswith('Director') or kind.startswith('Owner') or 'significant control' in detail:
        return kind
    return f'{kind}: {detail}'

# ---------- labels shared by pages and data ----------
CRIT = {
    'revenue_visibility': ('Repeat revenue', 'How much of the sales are likely to recur. Read from the accounts for the leading companies; estimated from the type of business for the rest.'),
    'strategy_fit': ('Fits the case', 'How closely the business matches the investment case. Only companies confirmed to trade in the sector are ranked.'),
    'size_fit': ('Right size', 'EBITDA (profit before interest, tax, depreciation and amortisation) in the £2–15m range most mid-market buyers target.'),
    'margin_quality': ('Profit margin', 'How high the EBITDA margin is and, where three or more years of accounts have been read, how steady it has been.'),
    'balance_sheet': ('Balance sheet', 'Net assets, cash and margin headroom, reduced where interest cover is thin or net debt is above 1x EBITDA. A first check, not a full measure of how much a buyer could borrow.'),
}
CCOL = {'revenue_visibility': '#2463C7', 'strategy_fit': '#D9691E', 'size_fit': '#2E8F57', 'margin_quality': '#86563A', 'balance_sheet': '#6F48C4'}
TYPES = {   # deal type: css class, label, short definition
    'Steady compounder': ('t-steady', 'Steady compounder', 'Recurring-type revenue, margin of 10% or more, sales not falling and a steady margin.'),
    'High-growth': ('t-growth', 'High-growth', 'Sales growing 20% a year or more over several years (25% if only one year is known).'),
    'Fixable dip': ('t-dip', 'Fixable dip', 'Falling sales or a thin margin, with a named problem and a fix.'),
    'Under pressure': ('t-pressure', 'Under pressure', 'Falling sales or a thin margin, and no fix identified yet.'),
    'Growth infrastructure': ('t-infra', 'Growth infrastructure', 'Loss-making while building a network, but growing. Not ranked; on the watchlist.'),
    'Between buckets': ('t-between', 'Between types', 'Good on some tests, not others, for the reason given.'),
    'Numbers to check': ('t-between', 'Numbers to check', 'Something in the figures needs checking before the company can be typed.'),
}
ACCESS = {'High': 'Easy', 'Medium': 'Possible', 'Low-Medium': 'Harder', 'Low': 'Hard', 'Check': 'Not yet known'}
def tag_type(t):
    if not t:
        return ''
    c, label, _ = TYPES.get(t, ('t-between', t, ''))
    return f'<span class="type {c}">{e(label)}</span>'
def tag_conf(c):
    return f'<span class="conf c-{e(c)}"><i></i>{e(c)}</span>' if c else ''
def tag_size(z):
    if not z:
        return ''
    c = 'z-big' if 'above' in z else 'z-small' if re.search('below', z, re.I) else 'z-ok'
    return f'<span class="size {c}">{e(z)}</span>'
def score_bar(s):
    return f'<span class="sc"><b>{s:.0f}</b><i style="--w:{s:.0f}%" aria-hidden="true"></i></span>'


class Site:
    def __init__(self, ctx):
        self.x = ctx
        self.U, self.D = ctx['U'], ctx['data']
        self.updated = self.U['date']
        self.pages = []      # (path, title) for the sitemap
        self.companies = [self.company(r) for _, r in ctx['rk'].iterrows()]
        self.by_num = {c['company_number']: c for c in self.companies}
        mp = f'{ROOT}/config/sector_measures.csv'   # sector-specific measures collected so far
        M = pd.read_csv(mp, dtype={'CompanyNumber': str}) if os.path.exists(mp) else pd.DataFrame(columns=['CompanyNumber'])
        for c in self.companies:
            c['sector_measures'] = [{'measure': m.measure, 'value': m.value, 'as_of': str(m.as_of), 'source': m.source}
                                    for m in M[M['CompanyNumber'] == c['company_number']].itertuples()]
        self.by_rank = {c['rank']: c for c in self.companies}
        self.sectors = ctx['sector_stats']
        self.sector_info = {s['id']: s for s in ctx['SECTORS']}
        self.top10 = [self.by_rank[int(t['rank'])] for t in self.U['top10'] if int(t['rank']) in self.by_rank]
        for c in self.top10:
            c['readiness'] = self.readiness(c)

    # ---------- one record per ranked company: drives its page and its JSON ----------
    def company(self, r):
        x, num = self.x, r['CompanyNumber']
        P = x['prof'].get(num, {})
        L = x['lens_by_num'].loc[num] if num in x['lens_by_num'].index else None
        sz = x['SZ'].loc[num] if x['SZ'] is not None and num in x['SZ'].index else None
        sec = x['SECDF'].loc[num] if num in x['SECDF'].index else None
        price = next((v for v in (x['val'] or {}).get('companies', []) if v['CompanyNumber'] == num), None)
        acc = str(r['accessibility'])
        level, _, note = acc.partition(':')
        split = []
        if L is not None and isinstance(L.get('driver_split'), str) and L['driver_split'].strip():
            try:
                split = json.loads(L['driver_split'])
            except ValueError:
                split = []
        sec_id = sec['sector'] if sec is not None and isinstance(sec['sector'], str) else ''
        rec = {
            'rank': int(r['rank']), 'company_number': num, 'name': x['nice'](r['CompanyName']),
            'registered_name': r['CompanyName'], 'what_it_does': x['plain'](r['relevance_reason']),
            'town': str(r['RegAddress.PostTown']).title() if isinstance(r['RegAddress.PostTown'], str) else None,
            'sector': sec_id, 'sector_name': self.sector_name(sec_id),
            'sector_basis': sec['sector_basis'] if sec is not None else None,
            'score': round(float(r['score']), 1),
            'score_parts': {k: round(float(r[f'pts_{k}']), 1) for k in x['weights']},
            'confidence': r['confidence'], 'confidence_reasons': nz(r['confidence_reasons']),
            'deal_type': (L['deal_type'] if L is not None else None), 'deal_type_reason': (L['deal_type_reason'] if L is not None else None),
            'fund_fit': (L['fund_fit'] if L is not None and isinstance(L.get('fund_fit'), str) else None),
            'demand_drivers': split or ([{'driver': L['demand_driver'], 'share': 1.0}] if L is not None and isinstance(L.get('demand_driver'), str) else []),
            'ease_of_buying': ACCESS.get(level.strip(), level.strip()), 'ease_of_buying_note': cap(note.strip()),
            'ownership_type': nz(r['ownership']),
            'likely_deal_size': (sz['size_flag'] if sz is not None else None), 'likely_deal_size_basis': (sz['size_basis'] if sz is not None else None),
            'figures': {
                'currency_reported': r['reported_currency'], 'accounts_filed': nz(r['accounts_filed']),
                'sales_gbp': nz(r['turnover']), 'sales_growth': nz(r['turnover_growth']),
                'ebitda_gbp': nz(r['ebitda']), 'ebitda_margin': nz(r['ebitda_margin']), 'ebitda_basis': nz(r['ebitda_basis']),
                'cash_gbp': nz(r['cash']), 'net_assets_gbp': nz(r['net_assets']), 'employees': nz(r['employees']),
                'source': nz(r['figures_source']), 'repeat_revenue_basis': nz(r['revenue_visibility_basis']),
                'margin_stability_basis': nz(r['margin_stability_basis']),
            },
            'why_on_list': P.get('why') or [], 'check_first': P.get('checks') or [],
            'history': P.get('history') or [], 'revenue_mix': P.get('revenue_mix'), 'revenue_mix_source': P.get('revenue_mix_source'),
            'price_check': self.price_record(price) if price else None,
            'in_top_ten': int(r['rank']) <= 10, 'method_version': r['method_version'], 'scored_on': r['scored_on'],
            'page': f'companies/{num}/', 'json': f'{API}/companies/{num}.json', 'companies_house': CH + num,
        }
        return clean_json(rec)

    def sector_name(self, sid):
        return next((s['name'] for s in self.x['SECTORS'] if s['id'] == sid), '')

    def price_record(self, v):
        keys = ['basis', 'mult_low', 'mult_mid', 'mult_high', 'small_discount', 'ebitda', 'ev_low', 'ev_mid', 'ev_high', 'net_debt',
                'net_debt_to_ebitda', 'accounts_year_end', 'equity_low', 'equity_high', 'cash_conversion', 'fcf_conversion',
                'walk_away_mult', 'walk_away_ev', 'walk_away_equity', 'irr_mid', 'moic_mid', 'irr_exit_plus1', 'irr_exit_minus1',
                'currency', 'balance_note', 'notes']
        return {k: v.get(k) for k in keys}

    def readiness(self, c):
        """Four deal-readiness checks beside the score (none of them changes it)."""
        notes = ' '.join(c['check_first'])
        z = c['likely_deal_size'] or ''
        size = ('none' if re.match(r'^(Probably|Below)', z) else 'half') if re.search('above|below', z, re.I) else 'full' if z else 'half'
        lvl = {'Easy': 'full', 'Possible': 'full', 'Harder': 'half', 'Hard': 'none'}.get(c['ease_of_buying'], 'half')
        why = f"{c['ease_of_buying']}: {c['ease_of_buying_note']}"
        if re.search('carve-out', notes, re.I) and lvl == 'full':
            lvl, why = 'half', 'Only as a carve-out from a larger parent'
        if re.search('unlikely to be sold', notes, re.I):
            lvl, why = 'none', 'Bought recently, so unlikely to be sold for several years'
        p = c['price_check']
        if not p:
            price, pwhy = 'half', 'No price check'
        else:
            price = 'full' if p['walk_away_mult'] >= p['mult_mid'] else 'half' if p['walk_away_mult'] >= p['mult_low'] else 'none'
            pwhy = f"Most a buyer could pay for 20% a year: {p['walk_away_mult']:.1f}x, against a {p['mult_low']:.1f}–{p['mult_high']:.1f}x price range"
        fig = {'High': 'full', 'Medium': 'half', 'Low': 'none'}.get(c['confidence'], 'half')
        fwhy = f"{c['confidence']} confidence" + (f": {c['confidence_reasons']}" if c['confidence_reasons'] else '')
        checks = [('size', size, z or 'Not estimated'), ('buyable', lvl, why), ('price', price, pwhy), ('figures', fig, fwhy)]
        return {'checks': [{'check': k, 'result': {'full': 'passes', 'half': 'partly', 'none': 'fails'}[l], 'why': w} for k, l, w in checks],
                'passes': sum(1 for _, l, _ in checks if l == 'full'), 'fails': sum(1 for _, l, _ in checks if l == 'none')}

    # ---------- page frame ----------
    NAV = [('rankings/', 'Rankings', 'rankings'), ('sectors/', 'Sectors', 'sectors'), ('market/', 'Market intelligence', 'market'),
           ('price-check/', 'Price check', 'price'), ('selection/', 'How we select', 'selection'),
           ('methodology/', 'Methodology', 'method'), ('data/', 'Data & API', 'data')]

    def live(self):
        return f'<span class="live"><i aria-hidden="true"></i>Weekly ranking, updated {fdate(self.updated, True)}</span>'

    def write(self, path, title, desc, body, active='', head=None, crumbs=None, lede=None, meta=None, jsonld=None, page_id=''):
        depth = path.count('/')
        r = '../' * depth if depth else './'
        full_title = f'{title} | {S["name"]}' if title != S['name'] else f'{S["name"]}: {S["tagline"].rstrip(".")}'
        cur = ' aria-current="page"'
        nav = ''.join(f'<li><a href="{r}{p}"{cur if a == active else ""}>{e(l)}</a></li>' for p, l, a in self.NAV)
        phead = ''
        if head is not False:
            cr = ''.join(f'<a href="{r}{p}">{e(l)}</a> / ' for p, l in (crumbs or []))
            phead = f'''<header class="phead"><div class="wrap">{f'<nav class="crumbs" aria-label="Breadcrumb"><a href="{r}">Home</a> / {cr}<span aria-current="page">{e(title)}</span></nav>' if path else ''}
<h1>{e(head or title)}</h1>{f'<p class="lede">{lede}</p>' if lede else ''}{f'<div class="meta">{meta}</div>' if meta else ''}</div></header>'''
        ld = ''.join(f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>' for j in (jsonld or []))
        email = S['contact_email']
        doc = f'''<!DOCTYPE html>
<html lang="en-GB" data-root="{r}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{BASE}{path}">
<link rel="alternate" type="application/json" href="{r}{API}/index.json" title="{S['name']} data (JSON)">
<link rel="stylesheet" href="{r}assets/northing.css">
<link rel="icon" href="{r}assets/favicon.svg" type="image/svg+xml">
<meta property="og:title" content="{e(full_title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:type" content="website"><meta property="og:url" content="{BASE}{path}">
{ld}
</head>
<body data-page="{e(page_id)}">
<a class="skip" href="#main">Skip to content</a>
<div class="top"><div class="wrap">
  <a class="logo" href="{r}" aria-label="{S['name']} home">{self.mark(30)}<span><b>{S['name'].upper()}</b><small>UK infrastructure rankings</small></span></a>
  <button class="menu" id="menu" aria-controls="nav" aria-expanded="false">Menu</button>
  <ul class="nav" id="nav">{nav}</ul>
  {self.live()}
</div></div>
{phead}
<main id="main" tabindex="-1"><div class="wrap">
{body}
</div></main>
<footer class="foot"><div class="wrap">
  <div><a class="logo" href="{r}">{self.mark(26)}<span><b>{S['name'].upper()}</b></span></a>
    <p style="margin-top:12px">{e(S['tagline'])} Covering {e(S['coverage_now'])} today. Rebuilt every Monday from Companies House filings.</p></div>
  <div><h2>Explore</h2><ul><li><a href="{r}rankings/">Rankings</a></li><li><a href="{r}sectors/">Sectors</a></li><li><a href="{r}market/">Market intelligence</a></li><li><a href="{r}price-check/">Price check</a></li></ul></div>
  <div><h2>Method and data</h2><ul><li><a href="{r}selection/">How we select companies</a></li><li><a href="{r}methodology/">Methodology</a></li><li><a href="{r}data/">Data &amp; API</a></li><li><a href="{r}licence/">Data sources and licence</a></li></ul></div>
  <div><h2>About</h2><ul><li><a href="{r}about/">About Northing</a></li><li><a href="{r}terms/">Terms of use</a></li><li><a href="{r}privacy/">Privacy notice</a></li><li><a href="{r}corrections/">Corrections</a></li></ul></div>
  <div class="fine">
    <p>Information and analysis only. Not investment advice, not a recommendation to buy or sell anything, and not a view on any company's prospects. Rankings measure fit with a written investment case.</p>
    <p>Contains public sector information licensed under the <a href="{OGL}">Open Government Licence v3.0</a>, from Companies House. Last updated {fdate(self.updated)}.</p>
  </div>
</div></footer>
<script src="{r}assets/northing.js" defer></script>
</body>
</html>
'''
        out = f'{DOCS}/{path}index.html' if not path.endswith('.html') else f'{DOCS}/{path}'
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'w').write(doc)
        if not path.endswith('.html'):
            self.pages.append(path)
        return r

    @staticmethod
    def mark(size):
        # Northing mark: three rising bars on a grid line (a northing is a grid coordinate)
        return (f'<svg width="{size}" height="{size}" viewBox="0 0 32 32" aria-hidden="true"><rect x="2" y="17" width="7" height="13" fill="#5FC3E4"/>'
                f'<rect x="12.5" y="10" width="7" height="20" fill="#1D8FE1"/><rect x="23" y="2" width="7" height="28" fill="#DCE6F2"/></svg>')

    # ---------- shared fragments ----------
    def funnel_vals(self):
        return [n for _, n in self.D['funnel']]

    def findings(self):
        U, C, V = self.U, self.x['corr'], self.x['val']
        t1 = self.top10[0]
        out = [f"<b>{e(t1['name'])} ranks first</b> with {t1['score']:.0f} out of 100: {e(t1['what_it_does'][:1].lower() + t1['what_it_does'][1:])}, sales of {money(t1['figures']['sales_gbp'])} and a {pct(t1['figures']['ebitda_margin'])} margin. A high score means a close fit with the investment case, not a good price."]
        if C:
            c = C['top_n']
            big = [f"{pct(f['share'])} rests on {e(f['factor'][:1].lower() + f['factor'][1:])}" for f in c['factors'] if f['share'] >= 0.2]
            out.append(f"<b>The ten are really about {c['effective_bets']:.0f} separate bets.</b> Weighting each company by how much of its sales depend on each factor, {', '.join(big)}.")
        if V:
            cs = V['companies']
            ok = sum(1 for v in cs if v['walk_away_mult'] >= v['mult_mid'])
            low = sum(1 for v in cs if v['mult_low'] <= v['walk_away_mult'] < v['mult_mid'])
            w = [v['walk_away_mult'] for v in cs]
            out.append(f"<b>A good company is not automatically a good deal.</b> At typical market prices, {'none' if ok == 0 else ok} of the ten would give a private equity buyer a 20% yearly return{f', and {low} only at the low end of the price range' if low else ''}. The most a buyer could pay ranges from {min(w):.1f} to {max(w):.1f} times EBITDA.")
        big = [c['name'] for c in self.top10 if 'above' in (c['likely_deal_size'] or '')]
        inb = sum(1 for c in self.top10 if c['likely_deal_size'] and not re.search('above|below', c['likely_deal_size'], re.I))
        out.append(f"<b>Deal size:</b> {inb} of the ten look like £10–250m deals." + (f" {e(', '.join(big))} {'is' if len(big) == 1 else 'are'} probably or possibly above £250m, mostly network owners that infrastructure funds price well above service firms." if big else ''))
        ready = [c['name'] for c in self.top10 if c['readiness']['fails'] == 0]
        out.append(f"<b>Deal readiness:</b> none of the ten passes all four checks (size, buyable, price, figures). {e(' and '.join(ready)) if ready else 'None'} {'has' if len(ready) == 1 else 'have'} no outright fail.")
        n = U.get('events_count') or 0
        moves = [m for m in U.get('top10_moves', []) if m['kind'] != 'same']
        out.append(f"<b>{'No change to the top ten this week.' if not moves else e(U['headline']) + '.'}</b> {n} Companies House {'event was' if n == 1 else 'events were'} recorded for the ranked companies since {fdate(U['checked_since'])}.")
        return out

    def readiness_table(self, r, sector_col=True):
        rows = ''
        for c in self.top10:
            rd = c['readiness']
            marks = ''.join(f'<td><i class="mk {dict(passes="full", partly="half", fails="none")[k["result"]]}" role="img" aria-label="{e(cap(k["result"]))}: {e(k["why"])}" title="{e(k["why"])}"></i></td>' for k in rd['checks'])
            sec = f'<small>{e(c["sector_name"])}</small>' if sector_col else ''
            rows += (f'<tr class="{"go" if rd["fails"] == 0 else ""}"><td class="nm"><span>{c["rank"]}</span><a href="{r}{c["page"]}">{e(c["name"])}</a>'
                     f'{sec}</td><td><b>{c["score"]:.0f}</b></td>{marks}<td class="pass">{rd["passes"]} of 4</td></tr>')
        return (f'<div class="tbox"><table class="tbl mx"><caption class="vh">Deal readiness of the top ten</caption><thead><tr><th scope="col">Company</th><th scope="col">Score</th>'
                f'<th scope="col" title="Likely deal size within £10–250m">Size</th><th scope="col" title="Owner able and likely to sell">Buyable</th>'
                f'<th scope="col" title="A buyer could make 20% a year inside the price range">Price</th><th scope="col" title="Confidence in the figures">Figures</th>'
                f'<th scope="col">Passes</th></tr></thead><tbody>{rows}</tbody></table></div>')

    def readiness_key(self):
        return ('<div class="key"><span><i class="mk full"></i> Passes</span><span><i class="mk half"></i> Partly</span><span><i class="mk none"></i> Fails</span>'
                '<span>Hover or focus a mark for the reason. Green rows have no outright fail.</span></div>')

    def ranking_rows(self, r, comps):
        out = ''
        for c in comps:
            f = c['figures']
            out += (f'<tr data-name="{e(c["name"].lower())}" data-sector="{e(c["sector"])}" data-type="{e(c["deal_type"] or "")}" data-confidence="{e(c["confidence"])}" '
                    f'data-size="{e(c["likely_deal_size"] or "")}" data-access="{e(c["ease_of_buying"])}">'
                    f'<td class="rk">{c["rank"]}</td><td><a class="co" href="{r}{c["page"]}">{e(c["name"])}</a><small>{e(c["what_it_does"])}</small></td>'
                    f'<td class="opt">{e(c["sector_name"])}</td><td class="opt">{tag_type(c["deal_type"])}</td><td>{tag_conf(c["confidence"])}</td>'
                    f'<td class="num opt">{money(f["sales_gbp"])}</td><td class="num opt">{pct(f["ebitda_margin"])}</td><td class="opt">{tag_size(c["likely_deal_size"])}</td>'
                    f'<td class="num">{score_bar(c["score"])}</td></tr>')
        return out

    def ranking_table(self, r, comps, caption, tid=''):
        idattr = f' id="{tid}"' if tid else ''
        return (f'<div class="tbox"><table class="tbl"{idattr}><caption class="vh">{e(caption)}</caption><thead><tr>'
                f'<th scope="col">Rank</th><th scope="col">Company</th><th scope="col" class="opt">Sector</th><th scope="col" class="opt">Type of deal</th>'
                f'<th scope="col">Confidence</th><th scope="col" class="num opt">Sales</th><th scope="col" class="num opt">EBITDA margin</th>'
                f'<th scope="col" class="opt">Likely deal size</th><th scope="col" class="num">Score</th></tr></thead><tbody>{self.ranking_rows(r, comps)}</tbody></table></div>')

    def key_box(self):
        types = ''.join(f'<span>{tag_type(k)}</span>' for k in ['Steady compounder', 'High-growth', 'Fixable dip', 'Under pressure', 'Between buckets'])
        return (f'<div class="keybox" aria-label="Key">'
                f'<div class="key"><b>Score</b><span>{score_bar(80)}</span><span>Out of 100, from five weighted factors. Fit with the investment case, not a price.</span></div>'
                f'<div class="key"><b>Type of deal</b>{types}</div>'
                f'<div class="key"><b>Confidence</b>{tag_conf("High")}{tag_conf("Medium")}{tag_conf("Low")}<span>How far the figures can be trusted. Never added to the score.</span></div>'
                f'<div class="key"><b>Likely deal size</b>{tag_size("Within £10–250m")}{tag_size("Could be above £250m")}{tag_size("Could be below £10m")}</div></div>')

    def donut(self):
        A = self.companies
        n = len(A)
        bands = [('80 and above', 80, 101, '#0F4C8A'), ('70–79', 70, 80, '#1D8FE1'), ('60–69', 60, 70, '#6FB6EC'), ('50–59', 50, 60, '#B5D6F3'), ('Below 50', 0, 50, '#CBD5E1')]
        cnt = [sum(1 for c in A if lo <= c['score'] < hi) for _, lo, hi, _ in bands]
        R, Cc, off, arcs = 54, 2 * 3.14159265 * 54, 0.0, ''
        for (lab, lo, hi, col), k in zip(bands, cnt):
            ln = Cc * k / n
            if k:
                arcs += f'<circle cx="70" cy="70" r="{R}" fill="none" stroke="{col}" stroke-width="22" stroke-dasharray="{max(0, ln - 1.5):.2f} {Cc:.2f}" stroke-dashoffset="{-off:.2f}"/>'
            off += ln
        lg = ''.join(f'<div><i style="background:{b[3]}"></i><span>{b[0]}</span><em>{k} ({round(100 * k / n)}%)</em></div>' for b, k in zip(bands, cnt))
        med = sorted(c['score'] for c in A)[n // 2]
        return (f'<div class="donutwrap"><div class="donut"><svg viewBox="0 0 140 140" role="img" aria-label="Score bands of the {n} ranked companies">{arcs}</svg>'
                f'<div><b>{n}</b><span>ranked</span></div></div><div class="lgd">{lg}</div></div>'
                f'<p class="note">Median score {med:.0f}. The tenth-ranked company scores {self.top10[-1]["score"]:.0f}.</p>')

    def factors_table(self):
        W, FA = self.x['weights'], self.D.get('factor_avg', {})
        rows = ''.join(f'<tr><td>{CRIT[k][0]}</td><td>{W[k]}</td><td>{FA[k]["all"]:.1f}</td><td>{FA[k]["top"]:.1f}<span class="pbar"><i style="width:{100 * FA[k]["top"] / W[k]:.0f}%"></i></span></td></tr>' for k in W if k in FA)
        return f'<table class="ptbl"><thead><tr><th>Factor</th><th>Points</th><th>All ranked</th><th>Top ten</th></tr></thead><tbody>{rows}</tbody></table>'

    def mini_funnel(self):
        fv = self.funnel_vals()
        lab = ['On the register', 'Full accounts, 3+ years old', 'Sales of £10–250m', 'Passed checks', 'Profitable', 'Ranked']
        col = ['#0A1F3C', '#123866', '#1B5491', '#1D72BE', '#1D8FE1', '#5FB4EC']
        return '<div class="ofun">' + ''.join(f'<div><i style="width:{100 - i * 13}%;background:{col[i]}">{v:,}</i><span>{lab[i]}</span></div>' for i, v in enumerate(fv)) + '</div>'

    def sectors_list(self, r):
        mx = max([1] + [s['ranked'] for s in self.sectors])
        rows = ''
        for s in self.sectors:
            med = '–' if s['median_score'] is None else f"{s['median_score']:.0f}"
            if s['status'] == 'planned':
                rows += f'<a href="{r}sectors/{s["id"]}/"><b>{e(s["name"])}</b><span>Not yet screened</span><em></em><em>–</em></a>'
            else:
                rows += (f'<a href="{r}sectors/{s["id"]}/"><b>{e(s["name"])}</b><span class="b2"><i style="width:{100 * s["ranked"] / mx:.1f}%"></i></span>'
                         f'<em>{s["ranked"]}</em><em>{med}</em></a>')
        return f'<div class="osec"><a class="hd" aria-hidden="true" tabindex="-1"><span>Sector</span><span>Ranked</span><em></em><em title="Median score">Median</em></a>{rows}</div>'

    def week_feed(self):
        U = self.U
        items = [('ok', '✓', 'Ranking rebuilt', f"{U['companies_checked']} ranked companies checked for new filings since {fdate(U['checked_since'])}")]
        evs = U.get('events') or []
        kinds = {}
        for ev in evs:
            kinds[ev['event']] = kinds.get(ev['event'], 0) + 1
        if kinds:
            items.append(('', '•', f"{len(evs)} Companies House events for ranked companies", ', '.join(f'{v} {k.lower()}' for k, v in sorted(kinds.items(), key=lambda z: -z[1]))))
        moves = [m for m in U.get('top10_moves', []) if m['kind'] != 'same']
        items.append(('', '•', 'Top ten unchanged' if not moves else U['headline'], 'No company moved in or out, and the order is the same' if not moves else ''))
        sig = self.x.get('signals') or []
        if sig:
            items.append(('', '!', f"{len(sig)} possible exit or refinancing {'signal' if len(sig) == 1 else 'signals'}", 'See Market intelligence'))
        return '<ul class="feed">' + ''.join(f'<li><span class="fi {c}" aria-hidden="true">{i}</span><div>{e(t)}{f"<small>{e(s)}</small>" if s else ""}</div><time datetime="{U["date"]}">{fdate(U["date"], True)}</time></li>' for c, i, t, s in items) + '</ul>'

    def quality_strip(self):
        Q, fv = self.D.get('quality', {}), self.funnel_vals()
        by = lambda k: sum(1 for c in self.companies if c['confidence'] == k)
        h, m, l = by('High'), by('Medium'), by('Low')
        n = h + m + l
        cb = f'<div class="cbar"><i class="h" style="width:{100 * h / n:.1f}%"></i><i class="m" style="width:{100 * m / n:.1f}%"></i><i class="l" style="width:{100 * l / n:.1f}%"></i></div>'
        cells = [(f'{fv[1]:,}', 'Filings read', 'full accounts, three or more years old'),
                 (f"{self.D['scanned_ocr']:,}", 'Scanned accounts read by OCR', f"{self.D['scanned']:,} still unread"),
                 (str(Q.get('checked_against_filing', 0)), 'Companies checked against the filing', f"{Q.get('corrected_filings', 0)} filings corrected by hand"),
                 (f"{Q.get('sector_checked', 0)} of {Q.get('sector_placed', 0)}", 'Sector placed from a checked description', 'the rest by industry code only'),
                 (f'{h} / {m} / {l}', 'Confidence of ranked figures', 'high / medium / low' + cb)]
        return '<div class="dq">' + ''.join(f'<div><b>{v}</b><span>{lab}</span><small>{sm}</small></div>' for v, lab, sm in cells) + '</div>'

    # ---------- pages ----------
    def home(self):
        r = './'
        fv, n = self.funnel_vals(), len(self.companies)
        inb = sum(1 for c in self.top10 if c['likely_deal_size'] and not re.search('above|below', c['likely_deal_size'], re.I))
        top5 = ''.join(f'<li><span class="rk">{c["rank"]}</span><div><a href="{c["page"]}">{e(c["name"])}</a><p>{e(c["what_it_does"])}. {e(c["sector_name"])}.</p></div>{score_bar(c["score"])}</li>' for c in self.top10[:5])
        cards = ''
        for s in self.sectors:
            if s['status'] == 'planned':
                cards += f'<a class="card planned" href="sectors/{s["id"]}/"><h3>{e(s["name"])} <span class="badge">Planned</span></h3><p>{e(s["covers"])}</p><div class="cm"><span>Not yet screened</span></div></a>'
            else:
                best = s['best']
                bst = f'<span><b>#{best["rank"]}</b>best: {e(best["company"])}</span>' if best else ''
                cards += (f'<a class="card" href="sectors/{s["id"]}/"><h3>{e(s["name"])}</h3><p>{e(s["covers"])}</p><div class="cm">'
                          f'<span><b>{s["ranked"]}</b>ranked</span><span><b>{s["in_band"]}</b>in the sales band</span>{bst}</div></a>')
        body = f'''
<div class="bigstats">
  <a href="selection/"><b>{fv[0]:,}</b><span>Companies on the register</span><small>under six digital-infrastructure industry codes</small></a>
  <a href="selection/#step-3"><b>{fv[2]:,}</b><span>In the £10–250m sales band</span><small>the size most mid-market investors buy</small></a>
  <a href="rankings/#full"><b>{n}</b><span>Companies ranked</span><small>each with its own profile page</small></a>
  <a href="rankings/#readiness"><b>{inb} of 10</b><span>Top ten likely priced £10–250m</span><small>with four deal-readiness checks</small></a>
</div>

<section class="section g12" aria-label="This week">
  <div class="panel s7"><div class="ph"><h2>Top of the ranking</h2><a href="rankings/">Full ranking</a></div>
    <p class="desc">The five highest scores this week. Each name opens the company's profile: figures, score breakdown, ownership and what to check first.</p>
    <ol class="toplist">{top5}</ol></div>
  <div class="panel s5"><div class="ph"><h2>This week's findings</h2><a href="market/">Market intelligence</a></div>
    <ul class="findings">{''.join(f'<li>{x}</li>' for x in self.findings())}</ul></div>
</section>

<section class="section" aria-labelledby="h-sectors">
  <div class="shead"><div><h2 id="h-sectors">The sectors we cover</h2><p>UK digital infrastructure, split into sectors by each company's main activity. {e(S['coverage_next'])}</p></div><a href="sectors/">Compare sectors</a></div>
  <div class="cards">{cards}</div>
</section>

<section class="section" aria-labelledby="h-how">
  <div class="shead"><div><h2 id="h-how">How the ranking is built</h2><p>Every filter comes from a written investment case, and every company removed is logged with a reason.</p></div><a href="selection/">How we select companies</a></div>
  <ol class="steps3">
    <li><b>Find</b><p>Every UK company registered under six digital-infrastructure industry codes, from the Companies House register: {fv[0]:,} records.</p></li>
    <li><b>Filter</b><p>Keep active private companies with full accounts and £10–250m of sales; remove foreign-owned subsidiaries, duplicates and firms outside the sector. <a href="selection/">See each step</a>.</p></li>
    <li><b>Rank</b><p>Score the {n} that remain on five factors, then show price, deal size, confidence and deal readiness beside the score. <a href="methodology/">Read the method</a>.</p></li>
  </ol>
</section>

<section class="section g12">
  <div class="panel s6"><h2>For investors</h2><p class="desc" style="margin-top:6px">Start with the <a href="rankings/">rankings</a> and the <a href="rankings/#readiness">deal-readiness checks</a>, then open a company's page. The <a href="price-check/">price check</a> shows what the top ten would cost and whether a buyer could make a 20% yearly return. <a href="market/">Market intelligence</a> shows how concentrated the list is and what changed this week.</p></div>
  <div class="panel s6"><h2>For AI agents and developers</h2><p class="desc" style="margin-top:6px">Everything on the site is also published as open data: <a href="{API}/rankings.json">rankings.json</a>, <a href="{API}/rankings.csv">rankings.csv</a>, one JSON file per company, sectors, method and funnel. Start at <a href="data/">Data &amp; API</a> or <a href="llms.txt">llms.txt</a>.</p></div>
</section>'''
        hero = f'''<section class="hero"><div class="wrap">
  <p class="brand">{S['name'].upper()}</p>
  <p class="line">{e(S['tagline'])}</p>
  <p class="sub">Every private UK digital-infrastructure company with £10–250m of sales, found in Companies House filings and ranked each week against a written investment case. {e(S['coverage_next'])}</p>
  <div class="cta"><a class="btn primary" href="rankings/">See the rankings</a><a class="btn ghost" href="selection/">How companies are selected</a></div>
  {self.live()}
</div></section>'''
        jl = [{'@context': 'https://schema.org', '@type': 'WebSite', 'name': S['name'], 'url': BASE, 'description': S['tagline']},
              {'@context': 'https://schema.org', '@type': 'Dataset', 'name': f"{S['name']}: UK digital infrastructure company rankings",
               'description': 'Weekly ranking of private UK digital-infrastructure companies with £10–250m of sales, built from Companies House filings and scored against a written investment case.',
               'url': BASE + 'data/', 'dateModified': self.updated, 'creator': {'@type': 'Person', 'name': S['operator']},
               'isAccessibleForFree': True, 'spatialCoverage': 'United Kingdom',
               'distribution': [{'@type': 'DataDownload', 'encodingFormat': 'application/json', 'contentUrl': BASE + f'{API}/rankings.json'},
                                {'@type': 'DataDownload', 'encodingFormat': 'text/csv', 'contentUrl': BASE + f'{API}/rankings.csv'}]}]
        self.write('', S['name'], f"{S['tagline']} Weekly rankings of UK digital-infrastructure companies from Companies House filings, with open data for investors and AI agents.",
                   hero.replace('<section class="hero">', '<section class="hero">') + '\n<div class="wrap" style="padding:0">' + body + '</div>', head=False, jsonld=jl, page_id='home')
        # the hero sits outside the main wrap: move it before <main>
        p = f'{DOCS}/index.html'
        d = open(p).read()
        d = d.replace('<main id="main" tabindex="-1"><div class="wrap">\n' + hero, hero + '\n<main id="main" tabindex="-1"><div class="wrap">')
        open(p, 'w').write(d)

    def rankings(self):
        r = '../'
        A = self.companies
        sel = lambda key, vals, lab=lambda v: v: f'<select data-filter="{key}" id="f-{key}"><option value="">All</option>' + ''.join(f'<option value="{e(v)}">{e(lab(v))}</option>' for v in vals) + '</select>'
        sec_opts = [s['id'] for s in self.sectors if s['ranked']]
        body = f'''
{self.key_box()}
<section class="section" id="readiness" aria-labelledby="h-ready">
  <div class="shead"><div><h2 id="h-ready">Top ten and deal readiness</h2><p>A high score means a good fit with the investment case. Four checks say whether it is also a deal a mid-market buyer could do now: a likely price of £10–250m, an owner able to sell, a price that allows a 20% yearly return, and figures that can be trusted.</p></div><a href="{r}methodology/#readiness">How the checks work</a></div>
  {self.readiness_table(r)}
  <div style="margin-top:12px">{self.readiness_key()}</div>
</section>

<section class="section g12" aria-label="Distribution">
  <div class="panel s4"><div class="ph"><h2>Score distribution</h2></div><p class="desc">How the {len(A)} ranked companies spread across score bands.</p>{self.donut()}</div>
  <div class="panel s4"><div class="ph"><h2>Scoring factors</h2><a href="{r}methodology/#score">How the score works</a></div><p class="desc">Average points scored on each factor against the points available.</p>{self.factors_table()}<p class="note">Confidence in the figures is rated separately and never adds to the score.</p></div>
  <div class="panel s4"><div class="ph"><h2>Selection funnel</h2><a href="{r}selection/">Each step explained</a></div><p class="desc">From the register to the ranking. Step widths are not to scale.</p>{self.mini_funnel()}</div>
</section>

<section class="section g12" aria-label="Sectors and this week">
  <div class="panel s6"><div class="ph"><h2>Sectors</h2><a href="{r}sectors/">All sectors</a></div><p class="desc">Ranked companies per sector and their median score.</p>{self.sectors_list(r)}</div>
  <div class="panel s6"><div class="ph"><h2>This week</h2><a href="{r}market/#changes">What changed</a></div><p class="desc">What the Monday update found.</p>{self.week_feed()}</div>
</section>

<section class="section"><div class="panel"><div class="ph"><h2>Data quality</h2><a href="{r}methodology/#limits">Limits</a></div><p class="desc">How the figures behind the ranking were read and checked.</p>{self.quality_strip()}</div></section>

<section class="section" id="full" aria-labelledby="h-full">
  <div class="shead"><div><h2 id="h-full">Full ranking: all {len(A)} companies</h2><p>Every company that passed the filters and the sector check, ranked by score. Choose a company for its profile. {self.D['sector_check']} more are waiting for a check that they really trade in the sector.</p></div><span style="font-size:15px">Download <a href="{r}{API}/rankings.csv">CSV</a> or <a href="{r}{API}/rankings.json">JSON</a></span></div>
  <form class="filters" role="search" onsubmit="return false">
    <label>Search<input id="f-search" type="search" placeholder="Company name"></label>
    <label>Sector{sel('sector', sec_opts, self.sector_name)}</label>
    <label>Type of deal{sel('type', [k for k in TYPES if any(c['deal_type'] == k for c in A)], lambda v: TYPES[v][1])}</label>
    <label>Confidence{sel('confidence', ['High', 'Medium', 'Low'])}</label>
    <label>Likely deal size{sel('size', sorted({c['likely_deal_size'] for c in A if c['likely_deal_size']}))}</label>
    <label>Ease of buying{sel('access', [v for v in ['Easy', 'Possible', 'Harder', 'Hard', 'Not yet known'] if any(c['ease_of_buying'] == v for c in A)])}</label>
    <span class="count" id="f-count" aria-live="polite">{len(A)} of {len(A)} shown</span>
  </form>
  {self.ranking_table(r, A, 'All ranked companies', 'ranking')}
  <p id="f-empty" class="note" hidden>No companies match these filters. Clear one to see more.</p>
</section>'''
        meta = f'<span>Updated {fdate(self.updated)}</span><span>Scoring method {e(self.U["method_version"])}</span><span>{len(A)} companies ranked</span>'
        self.write('rankings/', 'Rankings', f'Weekly ranking of {len(A)} UK digital-infrastructure companies, with deal-readiness checks for the top ten.', body, 'rankings',
                   lede='The weekly ranking of UK digital-infrastructure companies with £10–250m of sales, scored out of 100 against a written investment case. Price, deal size and confidence sit beside the score and never change it.', meta=meta,
                   jsonld=[{'@context': 'https://schema.org', '@type': 'ItemList', 'name': 'Northing ranking: UK digital infrastructure', 'numberOfItems': len(A),
                            'itemListElement': [{'@type': 'ListItem', 'position': c['rank'], 'name': c['name'], 'url': BASE + c['page']} for c in A]}])

    def company_page(self, c):
        r = '../../'
        f, W = c['figures'], self.x['weights']
        bars = ''.join(f'<div class="bar"><span>{CRIT[k][0]}</span><span class="track"><i style="width:{100 * c["score_parts"][k] / W[k]:.0f}%;background:{CCOL[k]}"></i></span><em>{c["score_parts"][k]:.0f} / {W[k]}</em></div>' for k in W)
        figs = [(money(f['sales_gbp']), 'Sales, latest year'), (pct(f['sales_growth']) if isnum(f['sales_growth']) else '–', 'Sales growth on the year'),
                (money(f['ebitda_gbp']), 'EBITDA'), (pct(f['ebitda_margin']), 'EBITDA margin'), (fdate(f['accounts_filed'], True) if f['accounts_filed'] else '–', 'Latest accounts filed')]
        hist = ''
        if c['history']:
            h = c['history']
            yrs = ''.join(f'<th>{x["year"]}</th>' for x in h)
            sal = ''.join(f'<td>{money(x.get("sales"))}</td>' for x in h)
            mar = ''.join(f'<td>{pct(x.get("margin"))}</td>' for x in h)
            mlab = 'Operating margin' if h[-1].get('basis') == 'Operating profit' else 'Pre-tax margin'
            hist = (f'<div class="tbox" style="border:0"><table class="hist"><thead><tr><th>Year</th>{yrs}</tr></thead><tbody>'
                    f'<tr><td>Sales</td>{sal}</tr><tr><td>{mlab}</td>{mar}</tr></tbody></table></div>')
        facts = [('What it does', e(c['what_it_does']) + (f". Registered in {e(c['town'])}." if c['town'] else '.')),
                 ('Sector', f'<a href="{r}sectors/{c["sector"]}/">{e(c["sector_name"])}</a>' + (f'<br><span class="small">{e(c["sector_basis"])}</span>' if c['sector_basis'] else '')),
                 ('Type of deal', (tag_type(c['deal_type']) + (f' {e(cap(c["deal_type_reason"]))}.' if c['deal_type_reason'] else '') + (f' Suits: {e(c["fund_fit"])}.' if c['fund_fit'] else '')) if c['deal_type'] else '–'),
                 ('Sales depend on', e(', '.join(f"{d['driver']}{'' if d['share'] >= 0.999 else ' ' + pct(d['share'])}" for d in c['demand_drivers'])) or '–'),
                 ('Ease of buying', f"{e(c['ease_of_buying'])}. {e(c['ease_of_buying_note'].rstrip('.'))}." + (f' Ownership: {e(c["ownership_type"])}.' if c['ownership_type'] else '')),
                 ('Likely deal size', (tag_size(c['likely_deal_size']) + f' {e(c["likely_deal_size_basis"] or "")}') if c['likely_deal_size'] else '–'),
                 ('Confidence', f"{tag_conf(c['confidence'])} {e(cap(c['confidence_reasons'] or 'figures tagged in the filing, three or more years read'))}."),
                 ('Where the figures come from', e(f['source'] or '–') + (f". EBITDA: {e(f['ebitda_basis'])}." if f['ebitda_basis'] else '') + (f" Reported in {e(f['currency_reported'])}, converted to pounds." if f['currency_reported'] and f['currency_reported'] != 'GBP' else ''))]
        if c['revenue_mix']:
            facts.insert(4, ('Where sales come from', f"{e(c['revenue_mix'])} <span class='small'>Source: {e(c['revenue_mix_source'])}.</span>"))
        p = c['price_check']
        price = ''
        if p:
            nd = eq = ''
            if p['net_debt'] is not None:
                lev = f" ({p['net_debt_to_ebitda']:.1f}x EBITDA)" if p['net_debt'] > 0 and p['net_debt_to_ebitda'] is not None else ''
                nd = f'<div><dt>{"Net cash" if p["net_debt"] <= 0 else "Net debt"}</dt><dd>{money(abs(p["net_debt"]))} at {fdate(p["accounts_year_end"])}{lev}</dd></div>'
            if p['equity_low'] is not None:
                lo = 'Nil' if p['equity_low'] <= 0 else money(p['equity_low'])
                eqv = 'Nil: debts exceed the price range' if p['equity_high'] <= 0 else f'{lo}–{money(p["equity_high"])}'
                eq = f'<div><dt>Price for the shares</dt><dd>{eqv}</dd></div>'
            price = f'''<section class="section panel" aria-labelledby="h-price"><div class="ph"><h2 id="h-price">Price check</h2><a href="{r}price-check/">All ten</a></div>
<p class="desc">A first view of price from listed peers and recent deals, and whether a private equity buyer could make a 20% yearly return. Illustrative only.</p>
<dl class="facts">
<div><dt>Price for the business</dt><dd>{money(p['ev_low'])}–{money(p['ev_high'])} ({p['mult_low']:.1f}–{p['mult_high']:.1f}x EBITDA of {money(p['ebitda'])}). {e(p['basis'])}{' (small-size discount)' if p['small_discount'] else ''}.</dd></div>
{nd}{eq}
<div><dt>Cash conversion</dt><dd>{f"{pct(p['cash_conversion'])} of EBITDA arrived as cash before tax; {pct(p['fcf_conversion'])} after capital spending" if p['cash_conversion'] is not None else 'Not shown: the filing has no cash flow statement'}</dd></div>
<div><dt>Most a buyer could pay</dt><dd>{p['walk_away_mult']:.1f}x, or {money(p['walk_away_ev'])} for the business, for a 20% yearly return</dd></div>
<div><dt>At the middle price</dt><dd>{pct(p['irr_mid'])} a year, {p['moic_mid']:.1f} times the money. One turn more or less at exit moves this to {pct(p['irr_exit_plus1'])} or {pct(p['irr_exit_minus1'])}.</dd></div>
{f"<div><dt>From the accounts</dt><dd>{e(p['balance_note'])}</dd></div>" if p['balance_note'] else ''}
{f"<div><dt>Market note</dt><dd>{e(p['notes'])}</dd></div>" if p['notes'] else ''}
</dl></section>'''
        ready = ''
        if c.get('readiness'):
            rd = c['readiness']
            names = {'size': 'Likely deal size', 'buyable': 'Owner able to sell', 'price': '20% return in the price range', 'figures': 'Figures can be trusted'}
            ready = ('<section class="section panel" aria-labelledby="h-rd"><div class="ph"><h2 id="h-rd">Deal readiness</h2><a href="' + r + 'methodology/#readiness">About the checks</a></div>'
                     f'<p class="desc">Passes {rd["passes"]} of 4 checks.</p><dl class="facts">' +
                     ''.join(f'<div><dt><i class="mk {dict(passes="full", partly="half", fails="none")[k["result"]]}" aria-hidden="true"></i> {names[k["check"]]}</dt><dd><b>{cap(k["result"])}.</b> {e(k["why"])}</dd></div>' for k in rd['checks']) + '</dl></section>')
        measures = ''
        if c['sector_measures']:
            src = lambda m: f'<a href="{e(m["source"])}">source</a>' if str(m['source']).startswith('http') else e(m['source'])
            measures = ('<section class="section panel" aria-labelledby="h-ms"><h2 id="h-ms">Sector measures</h2><p class="desc" style="margin-top:6px">Measures investors use for this sector, collected from public sources. Not part of the score.</p><dl class="facts">'
                        + ''.join(f'<div><dt>{e(m["measure"])}</dt><dd>{e(m["value"])} <span class="small">({e(m["as_of"])}, {src(m)})</span></dd></div>' for m in c['sector_measures']) + '</dl></section>')
        why = ''.join(f'<li>{e(w)}</li>' for w in c['why_on_list'])
        chk = ''.join(f'<li>{e(w)}</li>' for w in c['check_first'])
        prev = self.by_rank.get(c['rank'] - 1)
        nxt = self.by_rank.get(c['rank'] + 1)
        body = f'''
<div class="figs">{''.join(f'<div><b>{v}</b><span>{l}</span></div>' for v, l in figs)}</div>
<div class="section g12">
  <div class="s7">
    <section class="panel" aria-labelledby="h-facts"><h2 id="h-facts">Key facts</h2><dl class="facts" style="margin-top:8px">{''.join(f'<div><dt>{k}</dt><dd>{v}</dd></div>' for k, v in facts)}</dl></section>
    {f'<section class="section panel" aria-labelledby="h-why"><h2 id="h-why">Why it is on the list</h2><ul class="list" style="margin-top:12px">{why}</ul></section>' if why else ''}
    {f'<section class="section panel" aria-labelledby="h-chk"><h2 id="h-chk">Check first</h2><ul class="list" style="margin-top:12px">{chk}</ul></section>' if chk else ''}
  </div>
  <div class="s5">
    <section class="panel" aria-labelledby="h-score"><div class="ph"><h2 id="h-score">How the {c['score']:.0f} is made up</h2><a href="{r}methodology/#score">Method</a></div><p class="desc">Points on each of the five factors.</p><div class="bars">{bars}</div></section>
    <section class="section panel" aria-labelledby="h-hist"><h2 id="h-hist">Results by year</h2>{hist or f'<p class="desc" style="margin-top:8px">Latest year only: sales {money(f["sales_gbp"])}, EBITDA margin {pct(f["ebitda_margin"])}.</p>'}</section>
    {ready}
    {price}
    {measures}
    <section class="section panel" aria-labelledby="h-src"><h2 id="h-src">Sources and data</h2><div class="srcs" style="margin-top:8px"><a href="{CH}{c['company_number']}">Companies House record</a><a href="{CH}{c['company_number']}/filing-history">Filing history</a><a href="{r}{c['json']}">This company as JSON</a></div>
    <p class="note">Company number {e(c['company_number'])}. Scored on {fdate(c['scored_on'])} with method {e(c['method_version'])}. Spotted an error? <a href="{r}corrections/">Ask for a correction</a>.</p></section>
  </div>
</div>
<nav class="section srcs" aria-label="Neighbouring companies">{f'<a href="{r}{prev["page"]}">Previous: {prev["rank"]}. {e(prev["name"])}</a>' if prev else ''}{f'<a href="{r}{nxt["page"]}">Next: {nxt["rank"]}. {e(nxt["name"])}</a>' if nxt else ''}<a href="{r}rankings/#full">Back to the full ranking</a></nav>'''
        head = f'''<div class="cohead"><div class="bigrank">{c['rank']}<small>rank</small></div><div><h1>{e(c['name'])}</h1>
<div class="tags">{tag_type(c['deal_type'])}{tag_conf(c['confidence'])}{tag_size(c['likely_deal_size'])}<span class="badge">{e(c['sector_name'])}</span>{'<span class="badge blue">Top ten</span>' if c['in_top_ten'] else ''}</div></div>
<div class="scorebox"><b>{c['score']:.0f}</b><span>score out of 100</span></div></div>'''
        jl = [{'@context': 'https://schema.org', '@type': 'Organization', 'name': c['registered_name'], 'alternateName': c['name'], 'identifier': c['company_number'],
               'description': c['what_it_does'], 'url': BASE + c['page'], 'sameAs': CH + c['company_number'],
               **({'address': {'@type': 'PostalAddress', 'addressLocality': c['town'], 'addressCountry': 'GB'}} if c['town'] else {})}]
        self.write(c['page'], c['name'], f"{c['name']}: rank {c['rank']} of {len(self.companies)} in UK digital infrastructure, score {c['score']:.0f}. {c['what_it_does']}.",
                   body, 'rankings', crumbs=[('rankings/', 'Rankings')], jsonld=jl, page_id='company')
        # put the rich company header in place of the plain h1
        p = f"{DOCS}/{c['page']}index.html"
        d = open(p).read()
        d = re.sub(r'<h1>[^<]*</h1>', head, d, count=1)
        open(p, 'w').write(d)

    def sectors_pages(self):
        r = '../'
        rows = ''
        for s in self.sectors:
            if s['status'] == 'planned':
                rows += f'<tr><td><a class="co" href="{s["id"]}/">{e(s["name"])}</a><small>Not yet screened</small></td>' + '<td class="num opt">–</td>' * 2 + '<td class="num">–</td><td class="num">–</td><td class="opt">–</td><td class="num">–</td><td class="opt">–</td></tr>'
                continue
            c = s['conf']
            n = sum(c.values())
            cb = f'<div class="cbar"><i class="h" style="width:{100 * c["High"] / n:.1f}%"></i><i class="m" style="width:{100 * c["Medium"] / n:.1f}%"></i><i class="l" style="width:{100 * c["Low"] / n:.1f}%"></i></div><small>{c["High"]} high, {c["Medium"]} medium, {c["Low"]} low</small>' if n else '–'
            best = s['best']
            bl = f'<a href="{r}companies/{self.num_for_rank(best["rank"])}/">{e(best["company"])}</a> <small style="display:inline">#{best["rank"]}</small>' if best else '–'
            med = '–' if s['median_score'] is None else f"{s['median_score']:.0f}"
            rows += (f'<tr><td><a class="co" href="{s["id"]}/">{e(s["name"])}</a></td><td class="num opt">{s["in_band"]}</td><td class="num opt">{s["forward"]}</td><td class="num">{s["ranked"]}</td>'
                     f'<td class="num">{s["in_top10"]}</td><td class="opt">{bl}</td><td class="num">{med}</td><td class="opt">{cb}</td></tr>')
        defcards = ''
        for s in self.sectors:
            exc = f'<p><b>Not included:</b> {e(s["excludes"])}</p>' if s['excludes'] else ''
            pl = ' planned' if s['status'] == 'planned' else ''
            defcards += f'<a class="card{pl}" href="{s["id"]}/"><h3>{e(s["name"])}</h3><p>{e(s["covers"])}</p>{exc}</a>'
        live = [s for s in self.sectors if s['status'] != 'planned']
        chk = sum(s['checked'] for s in live)
        allp = sum(s['in_band'] for s in live)
        body = f'''<div class="tbox"><table class="tbl"><caption class="vh">Sectors</caption><thead><tr><th scope="col">Sector</th><th scope="col" class="num opt">In the sales band</th><th scope="col" class="num opt">Passed checks</th><th scope="col" class="num">Ranked</th><th scope="col" class="num">In top ten</th><th scope="col" class="opt">Best ranked</th><th scope="col" class="num">Median score</th><th scope="col" class="opt">Confidence in figures</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="note">Ranked companies are placed by their checked main activity. The other {allp - chk} companies in the sales band are placed by their industry code only, so those counts are a first cut. Sectors marked not yet screened are planned: the search has not covered them, so an empty sector does not mean there are no targets.</p>
<section class="section" aria-labelledby="h-def"><h2 id="h-def">What each sector covers</h2><div class="cards" style="margin-top:16px">{defcards}</div></section>'''
        self.write('sectors/', 'Sectors', 'UK digital-infrastructure sectors: how many companies each holds, how they rank and how far their figures can be trusted.', body, 'sectors',
                   lede='Every company sits in one sector, chosen by its main activity rather than its registered industry code. Choose a sector to see its ranked companies.')
        for s in self.sectors:
            rr = '../../'
            comps = [c for c in self.companies if c['sector'] == s['id']]
            scope = f'<p><b>Covers:</b> {e(s["covers"])}</p>' + (f'<p style="margin-top:8px"><b>Not included:</b> {e(s["excludes"])}</p>' if s['excludes'] else '')
            if s['status'] == 'planned' or not comps:
                msg = ('Not yet screened. The search has not covered this sector yet, so nothing here should be read as an absence of targets.' if s['status'] == 'planned'
                       else f"No company in this sector is ranked yet. {s['in_band']} companies are in the sales band and {s['forward']} passed the ownership and quality checks.")
                body = f'<div class="panel prose">{scope}<p style="margin-top:16px">{msg}</p></div>'
            else:
                st = [(s['ranked'], 'ranked'), (s['in_top10'], 'in the top ten'), (f"{s['median_score']:.0f}", 'median score'), (money(s['median_sales']), 'median sales'),
                      (pct(s['median_margin']), 'median EBITDA margin')]
                body = (f'<div class="panel prose">{scope}</div><div class="figs section">{"".join(f"<div><b>{v}</b><span>{l}</span></div>" for v, l in st)}</div>'
                        f'<section class="section" aria-labelledby="h-sc"><div class="shead"><div><h2 id="h-sc">Ranked companies in this sector</h2><p>{s["in_band"]} companies in the sales band, {s["forward"]} passed ownership and quality checks, {s["ranked"]} ranked.</p></div></div>'
                        f'{self.ranking_table(rr, comps, s["name"])}</section>'
                        + self.sector_measures_table(rr, comps) +
                        f'<section class="section panel"><h2>Sector measures</h2><p class="desc" style="margin-top:8px">Measures investors use here: {e(", ".join(s["measures_to_add"] or []) or "none listed")}. They are being collected company by company and are not part of the score, so companies can be compared across sectors on the same five factors.</p></section>')
            self.write(f'sectors/{s["id"]}/', s['name'], f"{s['name']} in the UK: {s['covers']}", body, 'sectors', crumbs=[('sectors/', 'Sectors')],
                       lede=('Planned sector, not yet screened.' if s['status'] == 'planned' else f"{s['ranked']} ranked companies."))

    def co_link(self, r, num, fallback):
        c = self.by_num.get(num)
        return f'<a class="co" href="{r}{c["page"]}">{e(c["name"])}</a>' if c else e(fallback)

    def sector_measures_table(self, r, comps):
        rows = ''.join(f'<tr><td><a class="co" href="{r}{c["page"]}">{e(c["name"])}</a></td><td>{e(m["measure"])}</td><td>{e(m["value"])}</td><td class="opt">{e(m["as_of"])}</td></tr>'
                       for c in comps for m in c.get('sector_measures', []))
        if not rows:
            return ''
        return ('<section class="section" aria-labelledby="h-msr"><div class="shead"><div><h2 id="h-msr">Sector measures collected so far</h2><p>From accounts and public announcements; sources on each company page. Not part of the score.</p></div></div>'
                f'<div class="tbox"><table class="tbl"><thead><tr><th>Company</th><th>Measure</th><th>Value</th><th class="opt">As of</th></tr></thead><tbody>{rows}</tbody></table></div></section>')

    def num_for_rank(self, rank):
        return self.by_rank[rank]['company_number']

    def price_page(self):
        r = '../'
        V = self.x['val']
        if not V:
            return
        A2 = V['assumptions']
        ok = sum(1 for v in V['companies'] if v['walk_away_mult'] >= v['mult_low'])
        verdict = (f"{ok} of {len(V['companies'])} {'clears' if ok == 1 else 'clear'} a 20% buyout return somewhere in {'its' if ok == 1 else 'their'} price range. For the rest, a buyer would need to pay less than the market usually asks, or count on growth and a higher exit price."
                   if ok else f"None of the {len(V['companies'])} clears a 20% buyout return inside its price range. A buyer would need to pay less than the market usually asks, or count on growth and a higher exit price.")
        res = lambda v: ('res-ok', 'Yes, at a typical price') if v['walk_away_mult'] >= v['mult_mid'] else ('res-mid', 'Only at the low end') if v['walk_away_mult'] >= v['mult_low'] else ('res-no', 'No')
        nd = lambda v: '–' if v is None else money(-v) if v <= 0 else f'({money(v)})'
        eq = lambda lo, hi: '–' if lo is None else 'Nil' if hi <= 0 else f"{'Nil' if lo <= 0 else money(lo)}–{money(hi)}"
        rows = ''
        for v in V['companies']:
            c = self.by_num.get(v['CompanyNumber'])
            cls, txt = res(v)
            cur = f'. Accounts in {v["currency"]}, converted to pounds' if v['currency'] != 'GBP' else ''
            nts = f'<small>{e(v["notes"])}</small>' if v['notes'] else ''
            rows += (f'<tr><td class="rk">{v["rank"]}</td><td><a class="co" href="{r}{c["page"]}">{e(c["name"])}</a><small>{e(v["basis"])}, {v["mult_low"]:.1f}–{v["mult_high"]:.1f}x EBITDA{" (small-size discount)" if v["small_discount"] else ""}{cur}</small>{nts}</td>'
                     f'<td class="num">{money(v["ebitda"])}</td><td class="num opt">{pct(v["cash_conversion"]) if v["cash_conversion"] is not None else "<small>not shown</small>"}</td>'
                     f'<td class="num">{money(v["ev_low"])}–{money(v["ev_high"])}</td><td class="num opt">{nd(v["net_debt"])}</td><td class="num opt"><b>{eq(v["equity_low"], v["equity_high"])}</b></td>'
                     f'<td class="num">{v["walk_away_mult"]:.1f}x<small>{money(v["walk_away_ev"])}</small></td><td class="{cls}">{txt}</td></tr>')
        B = V['benchmarks']
        item = lambda title, rs: f'<section class="section"><h3>{title}</h3><ul class="list" style="margin-top:8px">' + ''.join(f'<li><a href="{e(x.get("source", ""))}">{e(x["name"])}</a>{", " + e(x["what"][:1].lower() + x["what"][1:]) if x.get("what") else ""}: {e(x.get("multiple") or x.get("fact") or "")}.{" " + e(x["detail"]) + "." if x.get("detail") else ""}{" " + e(x["use"]) + "." if x.get("use") else ""}{" " + e(x["read"]) if x.get("read") else ""}</li>' for x in rs) + '</ul></section>'
        mr = A2['multiple_ranges']
        body = f'''<p class="verdict">{e(verdict)}</p>
<div class="tbox"><table class="tbl"><caption class="vh">Price check for the top ten</caption><thead><tr><th scope="col">Rank</th><th scope="col">Company</th><th scope="col" class="num">EBITDA</th><th scope="col" class="num opt">Cash conversion</th><th scope="col" class="num">Price for the business</th><th scope="col" class="num opt">Net cash or (debt)</th><th scope="col" class="num opt">Price for the shares</th><th scope="col" class="num">Most a buyer could pay</th><th scope="col">20% return in range?</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="keybox section"><div class="key"><b>How to read it</b><span>Price for the business applies multiples that listed companies and recent deals point to. Taking away debt and adding back cash gives the price for the shares. Cash conversion is how much of the year's EBITDA arrived as cash. The last two columns show the most a private equity buyer could pay and still make a 20% yearly return.</span></div></div>
<section class="section panel prose" aria-labelledby="h-set"><h2 id="h-set" style="margin-top:0">How the prices were set</h2>
<p>Repeat-revenue businesses: {mr['recurring_services']['low']}–{mr['recurring_services']['high']}x EBITDA. {e(mr['recurring_services']['why'])}</p>
<p>Project contractors: {mr['project_contractors']['low']}–{mr['project_contractors']['high']}x. {e(mr['project_contractors']['why'])} Companies with EBITDA under £{mr['small_ebitda_threshold_gbp'] / 1e6:.0f}m take {mr['small_ebitda_discount']}x off.</p>
<p>Buyer's case: borrow {A2['debt_turns_recurring']}x EBITDA ({A2['debt_turns_contractor']}x for contractors) at {A2['interest_rate'] * 100:.1f}% interest, grow at half the historic rate (capped at {A2['growth_cap'] * 100:.0f}% a year), use spare cash to repay debt, and sell after {A2['hold_years']} years at the same multiple paid. Where a filing has a cash flow statement, the case uses that company's actual capital spending and cash conversion. Debt and cash are as at each company's latest year end. Prices as of {fdate(V['as_of'])}.</p>
{item('Listed peers', B['listed_peers'])}{item('Deals', B['deals'])}{item('Listed infrastructure funds', B['listed_infrastructure_funds'])}
</section>'''
        self.write('price-check/', 'Price check', 'What the top ten UK digital-infrastructure companies would cost, and whether a private equity buyer could make a 20% yearly return.', body, 'price',
                   lede='What the top ten would cost, and whether a private equity buyer could make a 20% yearly return. A first view from public information; not a valuation.',
                   meta=f'<span>Prices as of {fdate(V["as_of"])}</span><a href="{r}{API}/price-check.json">Price check as JSON</a>')

    def market_page(self):
        r = '../'
        C, U = self.x['corr'], self.U
        cols = ['#2463C7', '#D9691E', '#2E8F57', '#86563A', '#6F48C4', '#0F7C8C']
        bets = ''
        if C:
            c = C['top_n']
            flag = {'green': 'No single factor dominates.', 'amber': 'Worth knowing, but no single factor dominates.'}.get(c['flag'], 'One factor dominates the list.')
            groups = ''.join(f'<div class="group" style="--c:{cols[i % len(cols)]}"><p class="n">{pct(f["share"])} of the ten</p><h3>{e(f["factor"])}</h3><ul>{"".join(f"<li>{e(n)}</li>" for n in f["companies"])}</ul><p>{e(f.get("explain", ""))}</p></div>' for i, f in enumerate(c['factors']))
            th = C['thresholds']
            bets = f'''<section class="section" aria-labelledby="h-bets"><div class="shead"><div><h2 id="h-bets">Ten companies, but how many separate bets?</h2><p>Companies that depend on the same thing would struggle at the same time, so the ten are grouped by what their sales depend on, split where a company has more than one source.</p></div></div>
<p class="verdict">The top ten is about {c['effective_bets']:.0f} separate bets, not ten. {flag}</p><div class="groups">{groups}</div>
<p class="note">The list is flagged when {th['amber_share'] * 100:.0f}% or more of the ten depends on one thing, and treated as a serious concentration at {th['red_share'] * 100:.0f}%. Each company counts once, spread across the things its sales depend on (for example 70% maritime, 30% public sector). Splits are estimated from the accounts and are open to review.</p></section>'''
        sig = self.x.get('signals') or []
        sigs = ''
        if sig:
            sigs = ('<section class="section" id="signals" aria-labelledby="h-sig"><div class="shead"><div><h2 id="h-sig">Exit and refinancing signals</h2><p>Filings that often come before or with a sale or a new debt package. A signal is a reason to look, not proof that anything has happened.</p></div></div><div class="tbox"><table class="tbl"><thead><tr><th>Company</th><th>Signal</th><th>What was filed</th><th class="opt">Date</th></tr></thead><tbody>'
                    + ''.join(f'<tr><td>{self.co_link(r, s["number"], s["company"])}</td><td><b>{e(s["signal"])}</b><small>{e(s["why"])}</small></td><td>{e(s["evidence"])}</td><td class="opt">{fdate(s["date"], True)}</td></tr>' for s in sig)
                    + '</tbody></table></div></section>')
        moves = [m for m in U.get('top10_moves', []) if m['kind'] != 'same']
        lab = lambda m: {'up': f"Up to {m['to']}", 'down': f"Down to {m['to']}", 'new': f"New at {m['to']}", 'out': 'Out of the ten'}.get(m['kind'], '')
        evs = U.get('events') or []
        ev_rows = ''.join(f'<tr><td>{self.co_link(r, ev["CompanyNumber"], ev["CompanyName"])}</td><td>{e(event_text(ev))}</td><td class="opt">{fdate(ev["date"], True)}</td></tr>' for ev in evs)
        changes = f'''<section class="section" id="changes" aria-labelledby="h-chg"><div class="shead"><div><h2 id="h-chg">What changed this week</h2><p>Compared with the ranking of {fdate(U['previous_scored_on'])}. Filings since {fdate(U['checked_since'])}.</p></div></div>
<div class="panel"><p>{'No company moved in or out of the top ten, and the order is unchanged.' if not moves else ''.join(f'<b>{e(m["company"])}</b>: {lab(m)}. ' for m in moves)}</p></div>
{f'<div class="tbox section"><table class="tbl"><caption class="vh">Companies House events for ranked companies</caption><thead><tr><th>Company</th><th>Event</th><th class="opt">Date</th></tr></thead><tbody>{ev_rows}</tbody></table></div><p class="note">Names of directors and owners are left out: they are people, and the company record holds them.</p>' if ev_rows else ''}</section>'''
        g = self.D.get('growth_infra') or []
        watch = ''
        if g:
            watch = (f'<section class="section" aria-labelledby="h-gi"><div class="shead"><div><h2 id="h-gi">Growth infrastructure watchlist</h2><p>Loss-making companies that are still growing, often because they are building networks. Not ranked, since a buyout needs profits to borrow against, but a growth infrastructure fund might look at them.</p></div></div>'
                     f'<div class="tbox"><table class="tbl"><thead><tr><th>Company</th><th class="num">Sales</th><th>Why it is here</th></tr></thead><tbody>'
                     + ''.join(f'<tr><td><b>{e(x["company"])}</b><small>{e(x["what"])}</small></td><td class="num">{money(x["sales"])}</td><td>{e(cap(x["reason"]))}.</td></tr>' for x in g) + '</tbody></table></div></section>')
        self.write('market/', 'Market intelligence', 'How concentrated the top UK digital-infrastructure companies are on a few demand drivers, exit and refinancing signals, and what changed this week.',
                   bets + sigs + changes + watch, 'market', lede='How concentrated the top ten are on a few demand drivers, the filings that hint at a sale or new debt, this week\'s changes, and the loss-making network builders worth watching.')

    def selection_page(self):
        r = '../'
        fv = self.funnel_vals()
        ex = self.x['excluded']
        cat = ex['excluded_reason'].astype(str).str.extract(r'^(Foreign-owned|Not digital infrastructure|Duplicate|Part of a much larger group)')[0].fillna('Other')
        bd = cat.value_counts()
        nice_cat = {'Not digital infrastructure': ('Outside the sector', 'Software, payments, energy, equipment sellers and other businesses that registered under a telecoms code but do not run or build networks.'),
                    'Foreign-owned': ('Foreign-owned subsidiaries', 'Owned by an overseas group, so not buyable on their own.'),
                    'Duplicate': ('Duplicates', 'Subsidiaries of a group that is already counted, so the group is assessed once.'),
                    'Part of a much larger group': ('Part of a much larger group', 'UK divisions of large groups that would not be sold separately.'),
                    'Other': ('Other reasons', 'Logged individually.')}
        breakdown = '<table class="breakdown"><tbody>' + ''.join(f'<tr><td><b>{nice_cat[k][0]}</b><br><span class="small">{nice_cat[k][1]}</span></td><td class="num">{v}</td></tr>' for k, v in bd.items()) + '</tbody></table>'
        cl = self.x['clean']
        gf = cl[cl['goes_forward']]
        st = gf['status'].value_counts()
        codes = ', '.join(f'{k} ({v.lower()})' for k, v in self.x['C']['segments'].items())
        steps = [
            ('On the register', fv[0], None, 'Every company in the Companies House register with one of six industry codes used by digital-infrastructure businesses.',
             f'Industry codes: {codes}. Codes are self-chosen by each company, so this step casts a wide net that later steps narrow.'),
            ('Active, private, full accounts, three or more years old', fv[1], fv[0] - fv[1], 'Keeps companies a buyer could actually acquire and analyse.',
             'Active companies only; private or unlisted public limited companies; accounts filed as full, group or medium-sized (small and micro accounts do not show sales); incorporated at least three years ago, so there is a track record.'),
            ('Sales between £10m and £250m', fv[2], fv[1] - fv[2], 'The size range mid-market private equity and infrastructure investors buy.',
             f"Sales come from each company's latest filed accounts. Figures for {self.D['scanned_ocr']:,} companies that file scanned accounts were read by text recognition (OCR); {self.D['scanned']:,} could not be read and may be missing."),
            ('Passed ownership and quality checks', fv[3], fv[2] - fv[3], 'Removes companies that cannot be bought on their own or are not really in the sector.',
             'Owners are traced through the register of people with significant control and checked against the accounts and public sources. Each removal is logged with its reason:' + breakdown),
            ('Profitable', fv[4], fv[3] - fv[4], 'A buyout needs profit to borrow against.',
             f"EBITDA must be positive in the latest accounts. Of the {fv[3]} that passed the checks, {int(st.get('Watchlist (loss-making)', 0))} are loss-making (growing network builders among them go to the <a href='{r}market/'>growth infrastructure watchlist</a>) and {int(st.get('In band, EBITDA unknown', 0))} have no EBITDA that could be read."),
            ('Confirmed to trade in the sector, and ranked', fv[5], fv[4] - fv[5], 'An industry code is not enough: each company is checked against what it actually does.',
             f"Each profitable company is checked from its accounts, website and news. Only companies confirmed as in the sector or adjacent to it are ranked; {self.D['sector_check']} are still waiting for that check. The ranked companies are then <a href='{r}methodology/#score'>scored</a>."),
        ]
        items = ''
        for i, (t, n, drop, why, how) in enumerate(steps, 1):
            dropt = 'starting point' if drop is None else f'<span class="drop">−{drop:,}</span> removed'
            items += (f'<li class="fstep" id="step-{i}"><div class="n">{n:,}<small>{dropt}</small></div>'
                      f'<div><h3>Step {i}. {e(t)}</h3><p><b>Why:</b> {e(why)}</p><p><b>How:</b> {how}</p><div class="fbar" aria-hidden="true"><i style="width:{max(1.0, (n / fv[0]) ** 0.5 * 100):.1f}%"></i></div></div></li>')
        body = f'''<div class="keybox"><div class="key"><b>Read this page as</b><span>Each step keeps fewer companies. The large number is how many are left after the step; the red number is how many it removed. Bars use a square-root scale so the small steps stay visible.</span></div></div>
<ol class="fsteps section">{items}</ol>
<section class="section panel prose"><h2 style="margin-top:0">After selection</h2><p>The {fv[5]} ranked companies are scored on five factors and given a confidence rating, a type of deal, a likely deal size and, for the top ten, a price check and four deal-readiness checks. See the <a href="{r}methodology/">methodology</a>. The whole process reruns every Monday; companies move in and out as new accounts are filed.</p>
<p>The funnel as data: <a href="{r}{API}/funnel.json">funnel.json</a>.</p></section>'''
        self.write('selection/', 'How we select companies', 'Step by step: how 48,467 Companies House records become a ranked list of UK digital-infrastructure companies, and why each filter exists.', body, 'selection',
                   lede=f'From {fv[0]:,} Companies House records to {fv[5]} ranked companies, in six steps. Every filter comes from a written investment case, and every company removed is logged with a reason.')

    def method_page(self):
        r = '../'
        W = self.x['weights']
        T = json.load(open(f'{ROOT}/config/demand_drivers.json'))['deal_types']
        crit = ''.join(f'<div class="card"><h3><span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:{CCOL[k]};margin-right:8px"></span>{CRIT[k][0]} <span class="badge">up to {W[k]} points</span></h3><p>{e(CRIT[k][1])}</p></div>' for k in W)
        types = ''.join(f'<div><dt>{tag_type(k)}</dt><dd>{e(v[2])} Suits: {e(T["fund_fit"].get(k, "–"))}.</dd></div>' for k, v in TYPES.items())
        lim = [
            ('Price check is a first pass', 'Ranges come from listed peers and deal averages, not from deals in each company\'s niche. Debt and cash are read from each top-ten company\'s latest accounts, which can be up to two years old, and debt held by owners\' holding companies is not visible.'),
            ('Deal size is an estimate', 'EBITDA times a multiple range, or a public deal value where one exists. Network owners are priced on a higher range because infrastructure funds pay more for them.'),
            ('Repeat revenue is partly read, partly estimated', 'For the leading companies it is read from the accounts (sales split, income paid in advance, contracts described), which rarely give renewal rates. For the rest it is judged from the type of business.'),
            ('Balance sheet, not debt capacity', 'Net assets, cash, margin and interest cover where known. True debt capacity needs net debt, capital spending and cash conversion, which are read only for the top ten.'),
            ('Some scanned accounts not read', f"Figures for {self.D['scanned_ocr']:,} companies that file scanned accounts were read by text recognition (OCR) and are labelled \"OCR, check\". {self.D['scanned']:,} of the {self.D['universe']:,} companies ({self.D['scanned'] / self.D['universe'] * 100:.0f}%) still have scanned accounts that could not be read, so good companies may be missing."),
            ('Sector check pending for some companies', f"{self.D['sector_check']} profitable companies are waiting for a check that they really trade in the sector. An industry code alone is not enough to be ranked."),
            ('Demand splits are estimates', 'For the top ten, each company\'s sales are split across what they depend on, estimated from the accounts and public contracts; filings rarely give the split directly. Further down the list, a company with two named sources is assumed 70/30.'),
            ('Accounts are historic', 'Companies House accounts are filed up to nine months after the year end, so the latest figures can be more than a year old. The ranking is rebuilt weekly, but the numbers change only when new accounts are filed.'),
            ('Not a view on any company', 'Rankings measure fit with one written investment case for a mid-market buyer. A low rank says nothing about a company\'s quality, management or prospects.'),
        ]
        acc = ''.join(f'<details class="acc"><summary>{e(t)}</summary><div class="body"><p>{e(d)}</p></div></details>' for t, d in lim)
        mr = (self.x['val'] or {}).get('assumptions', {}).get('multiple_ranges', {})
        body = f'''<div class="g12">
<nav class="s3" aria-label="On this page"><div class="panel" style="position:sticky;top:96px"><h2 style="font-size:16px">On this page</h2><ul class="list" style="list-style:none;padding:0;margin-top:8px">
<li><a href="#case">The investment case</a></li><li><a href="#score">The score</a></li><li><a href="#confidence">Confidence</a></li><li><a href="#types">Types of deal</a></li><li><a href="#readiness">Deal readiness</a></li><li><a href="#size">Deal size and price</a></li><li><a href="#sectors">Sector placement</a></li><li><a href="#updates">Weekly updates</a></li><li><a href="#limits">Limits</a></li></ul></div></nav>
<div class="s9">
<section id="case" class="panel prose"><h2 style="margin-top:0">The investment case</h2><p>The ranking starts from a written view of what a good mid-market investment in UK digital infrastructure looks like: a private business with £10–250m of sales and £2–15m of EBITDA, recurring revenue, healthy and steady margins, a balance sheet that can carry some debt, and an owner who could sell. Every filter and every point in the score comes from that case. Changing the case changes the ranking, which is why the method is published.</p></section>
<section id="score" class="section"><div class="shead"><div><h2>The score</h2><p>Five factors, each worth a set number of points, add up to 100. How reliable the figures are is rated separately, so a company is not ranked higher just because its accounts are easier to read.</p></div></div><div class="cards">{crit}</div></section>
<section id="confidence" class="section panel prose"><h2 style="margin-top:0">Confidence in the figures</h2><p>{tag_conf('High')} figures tagged in the filing and three or more years read. {tag_conf('Medium')} one weakness, such as fewer years read or an estimated input. {tag_conf('Low')} figures read from the text of the accounts or by OCR, estimated inputs, or fewer than three years. Each company page lists the exact reasons. Confidence is shown beside the score and never added to it.</p><p>{self.D['quality'].get('checked_against_filing', 0)} ranked companies have had their figures checked against the filing by hand, and {self.D['quality'].get('corrected_filings', 0)} filings were corrected where the automatic reading was wrong.</p></section>
<section id="types" class="section panel"><h2>Types of deal</h2><p class="desc" style="margin-top:6px">Which kind of fund each company suits. Applied in order, the first match wins. The type sits beside the score and never changes it.</p><dl class="facts">{types}</dl></section>
<section id="readiness" class="section panel"><h2>Deal readiness</h2><p class="desc" style="margin-top:6px">Four checks for the top ten, shown as passes, partly or fails. They say whether a well-scored company is also a deal a mid-market buyer could do now.</p>
<dl class="facts"><div><dt>Size</dt><dd>Likely deal size within £10–250m: passes inside the band, partly if it could be above or below, fails if probably outside it.</dd></div>
<div><dt>Buyable</dt><dd>An owner able and likely to sell: fails if bought recently, partly if only possible as a carve-out from a larger parent.</dd></div>
<div><dt>Price</dt><dd>Passes if a buyer could make 20% a year at the middle of the price range, partly if only at the low end, fails if not at all.</dd></div>
<div><dt>Figures</dt><dd>Passes with high confidence, partly with medium, fails with low.</dd></div></dl></section>
<section id="size" class="section panel prose"><h2 style="margin-top:0">Deal size and price</h2><p>Likely deal size is EBITDA times a multiple range: {mr.get('recurring_services', {}).get('low', 6)}–{mr.get('recurring_services', {}).get('high', 8)}x for repeat-revenue services, {mr.get('project_contractors', {}).get('low', 5)}–{mr.get('project_contractors', {}).get('high', 7)}x for contractors, and a higher range for network owners such as towers and fibre, which infrastructure funds price well above service firms. Where a public deal value exists it is used instead. The <a href="{r}price-check/">price check</a> adds net debt, cash conversion and a buyer's 20% return test for the top ten.</p></section>
<section id="sectors" class="section panel prose"><h2 style="margin-top:0">Sector placement</h2><p>Each company sits in one <a href="{r}sectors/">sector</a> by its main activity. Ranked companies are placed from a checked description of what they do; the rest by their industry code only, and marked so. Contractors that build networks for others form their own sector, because they are valued differently from network owners.</p></section>
<section id="updates" class="section panel prose"><h2 style="margin-top:0">Weekly updates</h2><p>Every Monday the ranked companies are checked for new Companies House filings: accounts, charges (security for loans), changes of directors and owners. New accounts are read and the ranking rebuilt. Charges and ownership changes are flagged on the <a href="{r}market/#signals">market intelligence</a> page as possible exit or refinancing signals. Current method: {e(self.U['method_version'])}.</p></section>
<section id="limits" class="section"><div class="shead"><div><h2>Limits</h2><p>The ranking points to where to look and gives a first view on price. It is not a valuation and not advice. Open each limit for detail.</p></div></div>{acc}</section>
</div></div>'''
        self.write('methodology/', 'Methodology', 'How Northing scores, types, sizes and prices UK digital-infrastructure companies, and the limits of the method.', body, 'method',
                   lede='How companies are scored, typed, sized and priced, and where the method falls short. The method as data: ' + f'<a href="{r}{API}/method.json">method.json</a>.')

    def data_page(self):
        r = '../'
        ep = [('index.json', 'List of every file below, with what it holds'), ('meta.json', 'Name, update date, method version, licence and attribution'),
              ('rankings.json', 'All ranked companies: rank, score, sector, type, confidence, size and key figures'), ('rankings.csv', 'The same as a spreadsheet'),
              ('companies/{company_number}.json', 'Everything on a company page: figures, score breakdown, ownership type, checks, history and price check'),
              ('sectors.json', 'Each sector: what it covers, counts and median figures'), ('funnel.json', 'The selection steps and how many companies each keeps'),
              ('method.json', 'Score weights, factor definitions, deal types, readiness checks and limits'), ('price-check.json', 'Price check for the top ten, assumptions and benchmarks'),
              ('market.json', 'Concentration of the top ten, signals and this week\'s changes')]
        ex_num = self.top10[0]['company_number']
        rows = ''
        for p, d in ep:
            link = f'<a href="{r}{API}/{p}">Open</a>' if '{' not in p else f'<a href="{r}{API}/companies/{ex_num}.json">Example</a>'
            rows += f'<tr><td><code>{e(p)}</code></td><td>{e(d)}</td><td>{link}</td></tr>'
        ex = json.dumps({k: self.companies[0][k] for k in ['rank', 'company_number', 'name', 'sector', 'score', 'confidence', 'deal_type', 'likely_deal_size', 'page', 'json']}, indent=2, ensure_ascii=False)
        body = f'''<div class="g12"><div class="s8">
<section class="panel prose"><h2 style="margin-top:0">Open data, free to read</h2><p>Everything on this site is also published as plain files that people and programs can read: JSON for programs and AI agents, CSV for spreadsheets. There is no key, sign-up or rate limit; the files are static and rebuilt every Monday with the site. The base address is:</p>
<pre><code>{BASE}{API}/</code></pre>
<p>AI agents can start from <a href="{r}llms.txt">llms.txt</a>, a short guide to the site and its data in plain text.</p></section>
<section class="section"><h2>Files</h2><div class="tbox" style="margin-top:16px"><table class="tbl"><thead><tr><th>File</th><th>What it holds</th><th></th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="section panel prose"><h2 style="margin-top:0">Example</h2><p>One entry from <code>rankings.json</code>:</p><pre><code>{e(ex)}</code></pre>
<p>Fetch it from the command line:</p><pre><code>curl {BASE}{API}/rankings.json</code></pre></section>
<section class="section panel prose"><h2 style="margin-top:0">Fields to know</h2><ul>
<li><code>score</code>: out of 100, the sum of <code>score_parts</code>. Fit with the investment case, not a price.</li>
<li><code>confidence</code>: High, Medium or Low, with <code>confidence_reasons</code>. Never added to the score.</li>
<li><code>likely_deal_size</code>: an estimate from EBITDA and a multiple range; see <code>likely_deal_size_basis</code>.</li>
<li>Money is in pounds (GBP) as plain numbers, converted where the accounts are in another currency. Margins and growth are fractions (0.25 means 25%).</li>
<li>Dates are ISO 8601 (YYYY-MM-DD). <code>company_number</code> is the Companies House number and links to the official record.</li></ul></section></div>
<div class="s4"><section class="panel prose"><h2 style="margin-top:0;font-size:18px">Use and attribution</h2><p>You may read, quote and reuse the data, including in other tools and AI systems, if you credit "{S['name']}" with a link to {BASE}. Companies House material is under the <a href="{OGL}">Open Government Licence v3.0</a>. The data is information, not advice; see the <a href="{r}terms/">terms of use</a>.</p></section>
<section class="section panel prose"><h2 style="margin-top:0;font-size:18px">Updates</h2><p>Last update {fdate(self.updated)}. Files are replaced each Monday; <code>meta.json</code> carries the date and method version so you can tell when something changed.</p></section>
<section class="section panel prose"><h2 style="margin-top:0;font-size:18px">Not included</h2><p>Names of directors and owners are left out, because they are people. The official company record has them.</p></section></div></div>'''
        self.write('data/', 'Data & API', 'Open data from Northing: rankings, company profiles, sectors and method as JSON and CSV, free to read, for people, programs and AI agents.', body, 'data',
                   lede='The rankings, every company profile, the sectors and the method, as JSON and CSV. Free to read, no key needed.')

    def policy_pages(self):
        r = '../'
        email = S['contact_email']
        contact = f'<a href="mailto:{e(email)}">{e(email)}</a>' if email else f'opening an issue on <a href="{S["issues_url"]}">GitHub</a> (public; do not include personal details there)'
        upd = f'<span>Last updated {fdate(S["policies_updated"])}</span>'
        pages = {
            'about/': ('About Northing', 'What Northing is, who runs it and how it is built.', f'''
<p>{S['name']} ranks private UK infrastructure companies for investors. It starts with {e(S['coverage_now'])}: every company with £10–250m of sales that a mid-market private equity or infrastructure investor could buy. {e(S['coverage_next'])}</p>
<h2>Why it exists</h2><p>Mid-market investors spend weeks finding companies before they come to market. Most company databases list who exists; {S['name']} tries to say which companies deserve attention, why, and roughly what they might cost, with every step written down so it can be checked.</p>
<h2>Who runs it</h2><p>{S['name']} is run by {e(S['operator'])}, independently. No company pays to be included or to change its position, and no company has endorsed the ranking.</p>
<h2>How it is built</h2><p>The data comes from Companies House: the public register and each company's filed accounts. A pipeline written in Python reads the accounts, applies the filters and scores each company; it runs every Monday on GitHub Actions and rebuilds this site. It was built with help from Claude, an AI assistant. The method and code are public on <a href="{S['repo_url']}">GitHub</a>.</p>
<h2>Accessibility</h2><p>The site aims to meet WCAG 2.2 AA: text contrast, keyboard navigation, visible focus, and pages that work without JavaScript. If something is hard to use, please report it through the <a href="{r}corrections/">corrections</a> page.</p>'''),
            'terms/': ('Terms of use', 'Terms for using the Northing website and data.', f'''
<p>These terms apply to the {S['name']} website and its data files. By using them you accept these terms.</p>
<h2>Information, not advice</h2><p>{S['name']} provides general information and analysis from public sources. It is not investment, financial, legal or tax advice, and it is not a recommendation or invitation to buy, sell or invest in any company or security. {S['name']} is not authorised or regulated by the Financial Conduct Authority. Do your own research and take professional advice before making any decision.</p>
<h2>What a ranking means</h2><p>A ranking measures how closely a company fits one written investment case for a mid-market buyer. It is not a rating of the company's quality, management, solvency or prospects, and a low position is not a criticism. Companies have not been contacted and have not endorsed their inclusion.</p>
<h2>Accuracy</h2><p>Figures are read automatically from filed accounts, some by text recognition, and some inputs are estimates; each is labelled. Accounts can be more than a year old. Errors are possible. {S['name']} does not guarantee that anything on the site is accurate, complete or current, and you should check important figures against the filing.</p>
<h2>Liability</h2><p>To the extent the law allows, {S['name']} and its operator accept no liability for any loss arising from use of, or reliance on, the website or data. Nothing in these terms limits liability that cannot be limited by law.</p>
<h2>Using the data</h2><p>You may read, quote and reuse the rankings and data, including in other tools and AI systems, if you credit "{S['name']}" with a link to {BASE}. Do not present the data as your own or suggest that {S['name']} endorses your product. Companies House material remains under the <a href="{OGL}">Open Government Licence v3.0</a>. The site design, text and code are not licensed for reuse except as above.</p>
<h2>Changes and law</h2><p>These terms may change; the date above shows the latest version. They are governed by the law of England and Wales.</p>'''),
            'privacy/': ('Privacy notice', 'How Northing handles personal data, including information about people in public company records.', f'''
<p>This notice explains what personal data {S['name']} handles and your rights. {S['name']} is run by {e(S['operator'])}, who is the data controller. Contact: {contact}.</p>
<h2>Visitors to the site</h2><p>The site sets no cookies, runs no analytics and loads nothing from other companies' servers: fonts and scripts are served with the site. The site is hosted on GitHub Pages; GitHub may record visitors' IP addresses in its server logs for security, under <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>.</p>
<h2>People in company records</h2><p>The analysis uses Companies House records, which include the names of directors and of people with significant control (owners). This is personal data even though it is public. {S['name']} uses it only to understand who owns a company and whether it could be sold, and to notice changes such as an owner leaving. Names of individuals are not published on the site or in the data files; pages describe ownership in general terms (for example "founder-owned"). Some descriptions draw on company websites and news reports.</p>
<h2>Lawful basis and retention</h2><p>The lawful basis is legitimate interests: analysing companies for investment research, using information the law already makes public, with names kept out of what is published. Working data is kept while a company is covered and deleted within twelve months after it is removed.</p>
<h2>Your rights</h2><p>You can ask for a copy of personal data held about you, ask for it to be corrected or deleted, or object to its use, by contacting {contact}. You can also complain to the Information Commissioner's Office at <a href="https://ico.org.uk/make-a-complaint/">ico.org.uk</a>.</p>'''),
            'licence/': ('Data sources and licence', 'Where Northing data comes from and how it may be reused.', f'''
<h2>Companies House</h2><p>Company details, accounts, charges, officers and people with significant control come from Companies House. Contains public sector information licensed under the <a href="{OGL}">Open Government Licence v3.0</a>. Companies House does not endorse {S['name']}.</p>
<h2>Other sources</h2><p>Descriptions of what companies do, ownership checks and deal status draw on company websites and news reports, cited on each company page or in the data where used. Price multiples come from published reports and announcements by listed companies and deals, linked on the <a href="{r}price-check/">price check</a> page.</p>
<h2>What is {S['name']}'s own</h2><p>The selection, scoring, sector placement, deal types, readiness checks and price checks are {S['name']}'s analysis. You may reuse them with credit and a link, as set out in the <a href="{r}terms/">terms of use</a>.</p>
<h2>Fonts</h2><p>IBM Plex Sans, used under the SIL Open Font License 1.1, served with the site.</p>'''),
            'corrections/': ('Corrections', 'How to report an error in Northing data or ask for a change.', f'''
<p>If a figure, description, sector or ownership note is wrong, please say so. Corrections make the ranking better for everyone.</p>
<h2>How to ask</h2><p>Contact {contact}. Include the company name or number, what is wrong, and where the right information can be checked (for example a filed accounts page or an announcement).</p>
<h2>What happens next</h2><p>Each request is checked against the source. Where the site is wrong, the figure is corrected in a record of hand corrections, the change is noted, and the site is rebuilt, usually within a week. If a request is not accepted, the reply says why.</p>
<h2>Companies</h2><p>Companies cannot pay to be included, excluded or moved. A company that believes it is misdescribed can ask for a correction like anyone else.</p>'''),
        }
        for path, (title, desc, html_) in pages.items():
            self.write(path, title, desc, f'<div class="panel prose" style="max-width:900px">{html_}</div>', '', lede=None, meta=upd if path != 'about/' else None)
        # 404
        self.write('404.html', 'Page not found', 'Page not found.', f'<div class="panel prose"><p>That page does not exist. Try the <a href="{BASE}">home page</a>, the <a href="{BASE}rankings/">rankings</a> or the <a href="{BASE}data/">data</a>.</p></div>', '')

    # ---------- data files ----------
    def api(self):
        d = f'{DOCS}/{API}'
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(f'{d}/companies')
        dump = lambda name, obj: json.dump(clean_json(obj), open(f'{d}/{name}', 'w'), ensure_ascii=False, indent=1)
        meta = {'name': S['name'], 'description': S['tagline'], 'coverage': S['coverage_now'], 'updated': self.updated, 'method_version': self.U['method_version'],
                'companies_ranked': len(self.companies), 'site': BASE, 'licence': f'Free to reuse with credit to {S["name"]} and a link to {BASE}. See {BASE}terms/',
                'attribution': 'Contains public sector information licensed under the Open Government Licence v3.0, from Companies House.',
                'disclaimer': 'Information and analysis only; not investment advice. Rankings measure fit with a written investment case, not company quality.',
                'personal_data': 'Names of individuals (directors, owners) are not included.'}
        dump('meta.json', meta)
        keys = ['rank', 'company_number', 'name', 'what_it_does', 'sector', 'sector_name', 'score', 'score_parts', 'confidence', 'deal_type', 'likely_deal_size',
                'ease_of_buying', 'in_top_ten', 'page', 'json', 'companies_house']
        rows = []
        for c in self.companies:
            row = {k: c[k] for k in keys}
            row.update({'sales_gbp': c['figures']['sales_gbp'], 'ebitda_gbp': c['figures']['ebitda_gbp'], 'ebitda_margin': c['figures']['ebitda_margin'],
                        'accounts_filed': c['figures']['accounts_filed']})
            row['page'], row['json'] = BASE + row['page'], BASE + row['json']
            if c.get('readiness'):
                row['readiness_passes'] = c['readiness']['passes']
            rows.append(row)
        dump('rankings.json', {'updated': self.updated, 'method_version': self.U['method_version'], 'count': len(rows), 'companies': rows})
        flat = pd.DataFrame([{**{k: v for k, v in r_.items() if k != 'score_parts'}, **{f'points_{k}': v for k, v in r_['score_parts'].items()}} for r_ in rows])
        flat.to_csv(f'{d}/rankings.csv', index=False)
        for c in self.companies:
            dump(f"companies/{c['company_number']}.json", {**c, 'page': BASE + c['page'], 'json': BASE + c['json'], 'updated': self.updated})
        dump('sectors.json', {'updated': self.updated, 'sectors': [{**s, 'page': BASE + f"sectors/{s['id']}/"} for s in self.sectors]})
        dump('funnel.json', {'updated': self.updated, 'steps': [{'step': i + 1, 'label': l, 'companies': n} for i, (l, n) in enumerate(self.D['funnel'])], 'page': BASE + 'selection/'})
        T = json.load(open(f'{ROOT}/config/demand_drivers.json'))['deal_types']
        dump('method.json', {'method_version': self.U['method_version'], 'score_weights': self.x['weights'],
                             'factors': {k: {'label': v[0], 'definition': v[1]} for k, v in CRIT.items()},
                             'confidence': 'High, Medium or Low: how far the figures can be trusted. Shown beside the score, never added to it.',
                             'deal_types': {k: {'label': v[1], 'definition': v[2], 'suits': T['fund_fit'].get(k)} for k, v in TYPES.items()},
                             'readiness_checks': {'size': 'Likely deal size within £10–250m', 'buyable': 'Owner able and likely to sell', 'price': 'A buyer could make 20% a year inside the price range', 'figures': 'Confidence in the figures'},
                             'page': BASE + 'methodology/'})
        V = self.x['val']
        if V:
            dump('price-check.json', {'as_of': V['as_of'], 'assumptions': V['assumptions'], 'benchmarks': V['benchmarks'],
                                      'companies': [{'rank': v['rank'], 'company_number': v['CompanyNumber'], 'name': self.by_num[v['CompanyNumber']]['name'], **self.price_record(v)} for v in V['companies']]})
        C = self.x['corr']
        dump('market.json', {'updated': self.updated, 'concentration': C['top_n'] if C else None, 'signals': self.x.get('signals') or [],
                             'top10_moves': [{k: m[k] for k in ('company', 'number', 'kind', 'from', 'to')} for m in self.U.get('top10_moves', [])],
                             'events': [{'company_number': ev['CompanyNumber'], 'event': event_text(ev), 'date': ev['date']} for ev in self.U.get('events') or []],
                             'growth_infrastructure_watchlist': self.D.get('growth_infra') or []})
        files = ['meta.json', 'rankings.json', 'rankings.csv', 'sectors.json', 'funnel.json', 'method.json', 'price-check.json', 'market.json']
        dump('index.json', {'name': S['name'], 'updated': self.updated, 'base': BASE + API + '/', 'files': {f: BASE + f'{API}/{f}' for f in files},
                            'companies': BASE + f'{API}/companies/{{company_number}}.json', 'docs': BASE + 'data/', 'llms_txt': BASE + 'llms.txt'})

    def crawl_files(self):
        fv = self.funnel_vals()
        top = '\n'.join(f"- [{c['rank']}. {c['name']}]({BASE}{c['page']}): {c['what_it_does']}. Score {c['score']:.0f}. JSON: {BASE}{c['json']}" for c in self.top10)
        sec = '\n'.join(f"- [{s['name']}]({BASE}sectors/{s['id']}/): {s['covers']}" for s in self.sectors)
        llms = f'''# {S['name']}

> {S['tagline']} Weekly ranking of private {S['coverage_now']} companies with £10–250m of sales, built from Companies House filings and scored out of 100 against a written investment case. Information only, not investment advice.

Last updated {self.updated}. Method {self.U['method_version']}. {len(self.companies)} companies ranked from {fv[0]:,} on the register.

## Key pages
- [Rankings]({BASE}rankings/): the full ranking with deal-readiness checks for the top ten
- [How we select companies]({BASE}selection/): the six selection steps
- [Methodology]({BASE}methodology/): score factors, confidence, deal types, readiness checks, limits
- [Sectors]({BASE}sectors/): sector definitions and counts
- [Price check]({BASE}price-check/): what the top ten would cost and the 20% return test
- [Market intelligence]({BASE}market/): concentration, exit and refinancing signals, weekly changes

## Data (JSON and CSV, no key needed)
- [Index of files]({BASE}{API}/index.json)
- [Rankings JSON]({BASE}{API}/rankings.json) and [CSV]({BASE}{API}/rankings.csv)
- One file per company: {BASE}{API}/companies/{{company_number}}.json
- [Sectors]({BASE}{API}/sectors.json), [Method]({BASE}{API}/method.json), [Funnel]({BASE}{API}/funnel.json), [Price check]({BASE}{API}/price-check.json), [Market]({BASE}{API}/market.json)

## Top ten this week
{top}

## Sectors
{sec}

## Notes for agents
- Scores measure fit with one investment case, not company quality. Quote the confidence rating with any figure.
- Money is in GBP; margins and growth are fractions. Accounts can be more than a year old: check accounts_filed.
- Credit "{S['name']}" with a link to {BASE} when reusing. Terms: {BASE}terms/
'''
        open(f'{DOCS}/llms.txt', 'w').write(llms)
        open(f'{DOCS}/robots.txt', 'w').write(f'User-agent: *\nAllow: /\n\nSitemap: {BASE}sitemap.xml\n')
        urls = ''.join(f'<url><loc>{BASE}{p}</loc><lastmod>{self.updated}</lastmod></url>' for p in self.pages)
        open(f'{DOCS}/sitemap.xml', 'w').write(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')

    def assets(self):
        a = f'{DOCS}/assets'
        os.makedirs(a, exist_ok=True)
        shutil.copy(f'{HERE}/northing.css', f'{a}/northing.css')
        shutil.copy(f'{HERE}/northing.js', f'{a}/northing.js')
        open(f'{a}/favicon.svg', 'w').write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#0A1F3C"/><rect x="5" y="18" width="6" height="9" fill="#5FC3E4"/><rect x="13" y="12" width="6" height="15" fill="#1D8FE1"/><rect x="21" y="5" width="6" height="22" fill="#DCE6F2"/></svg>')

    def build(self):
        for sub in ['rankings', 'companies', 'sectors', 'market', 'price-check', 'selection', 'methodology', 'data', 'about', 'terms', 'privacy', 'licence', 'corrections']:
            p = f'{DOCS}/{sub}'
            if os.path.exists(p):
                shutil.rmtree(p)
        self.assets()
        self.home()
        self.rankings()
        for c in self.companies:
            self.company_page(c)
        self.sectors_pages()
        self.price_page()
        self.market_page()
        self.selection_page()
        self.method_page()
        self.data_page()
        self.policy_pages()
        self.api()
        self.crawl_files()
        open(f'{DOCS}/.nojekyll', 'w').write('')
        return len(self.pages)


def build(ctx):
    n = Site(ctx).build()
    print(f'Built {n} pages and the data files in docs/')
