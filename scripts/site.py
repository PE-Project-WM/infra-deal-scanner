"""Build the public website (docs/index.html, served by GitHub Pages) from the latest update."""
import os, json, html
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U = json.load(open(f'{ROOT}/data/updates/latest.json'))
C = json.load(open(f'{ROOT}/config/criteria_digital_infra.json'))
fin = pd.read_csv(f'{ROOT}/data/inputs/financials_all.csv', dtype={'CompanyNumber': str})
clean = pd.read_csv(f'{ROOT}/data/outputs/candidates_clean.csv', dtype={'CompanyNumber': str})
IN_BAND = ['Shortlist', 'Watchlist (loss-making)', 'In band, EBITDA unknown']
funnel = [
    ('Companies registered under the six digital-infrastructure industry codes', 48467),
    ('Active, private, filing full accounts, three or more years old', len(fin)),
    ('Turnover between £10m and £250m', int(fin['status'].isin(IN_BAND).sum())),
    ('Left after ownership checks, duplicates and the thesis test', int(clean['goes_forward'].sum())),
    ('Profitable and scored', U['ranked']),
]
weights = C['scoring_weights']
corr_path = f'{ROOT}/data/outputs/correlation_latest.json'   # Version 2 lenses (scripts/lenses.py)
corr = json.load(open(corr_path)) if os.path.exists(corr_path) else None
if corr:
    by_rank = {t['rank']: t for t in corr['top10']}
    for t in U['top10']:
        t['lens'] = by_rank.get(t['rank'])
data = {'update': U, 'funnel': funnel, 'weights': weights, 'corr': corr}
payload = json.dumps(data, default=str).replace('</', '<\\/')

page = r'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UK Digital Infrastructure Screen</title>
<meta name="description" content="A weekly, thesis-led screen of UK digital-infrastructure companies built from public Companies House filings.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#eef1f4; --sheet:#ffffff; --ink:#18212d; --ink2:#4b5664; --mute:#7c8794; --rule:#d5dbe2;
  --blue:#2463c7; --orange:#e2742a; --green:#2e9a57; --brown:#86563a; --slate:#64707e; --violet:#7a4fd0;
  --up:#2e9a57; --down:#c2412d;
}
*{box-sizing:border-box;margin:0;padding:0}
html{background:var(--paper)}
body{font-family:Archivo,system-ui,sans-serif;font-variation-settings:"wdth" 100;color:var(--ink);background:var(--paper);line-height:1.5;font-size:16px;-webkit-font-smoothing:antialiased}
a{color:var(--blue);text-underline-offset:2px}
a:focus-visible,summary:focus-visible,button:focus-visible{outline:2px solid var(--blue);outline-offset:3px;border-radius:2px}
.wrap{max-width:1120px;margin:0 auto;padding:0 28px}
header.top{padding:56px 0 28px}
.byline{font-size:14px;color:var(--ink2);margin-bottom:28px;display:flex;flex-wrap:wrap;gap:6px 18px}
.byline span{white-space:nowrap}
h1{font-weight:800;font-variation-settings:"wdth" 118;font-size:clamp(34px,5.4vw,62px);line-height:1.02;letter-spacing:-.015em;max-width:15ch}
.intro{margin-top:20px;font-size:18px;color:var(--ink2);max-width:62ch}
.week{margin-top:30px;display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;padding:16px 0;border-top:2px solid var(--ink);border-bottom:1px solid var(--rule)}
.week b{font-variation-settings:"wdth" 112;font-weight:700;font-size:19px}
.week span{color:var(--ink2);font-size:15px}
section{padding:44px 0}
h2{font-weight:750;font-variation-settings:"wdth" 112;font-size:26px;letter-spacing:-.01em;margin-bottom:6px}
.sub{color:var(--ink2);max-width:66ch;margin-bottom:22px}
/* legend */
.legend{display:flex;flex-wrap:wrap;gap:8px 20px;margin:0 0 18px;font-size:14px;color:var(--ink2)}
.legend i{display:inline-block;width:22px;height:6px;border-radius:3px;margin-right:7px;vertical-align:middle}
/* ranking */
ol.rank{list-style:none;background:var(--sheet);border:1px solid var(--rule);border-radius:10px;overflow:hidden}
ol.rank>li{border-top:1px solid var(--rule)}
ol.rank>li:first-child{border-top:none}
details>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:44px minmax(180px,1.15fr) 2fr 64px 150px;align-items:center;gap:18px;padding:16px 22px}
details>summary::-webkit-details-marker{display:none}
details>summary:hover{background:#f7f9fb}
.pos{font-variation-settings:"wdth" 125;font-weight:800;font-size:26px;color:var(--ink);font-feature-settings:"tnum"}
.name{font-weight:650;font-size:17px;line-height:1.25}
.name small{display:block;font-weight:400;font-size:13.5px;color:var(--mute);margin-top:2px}
.bundle{display:flex;height:14px;border-radius:7px;overflow:hidden;background:#e4e8ed}
.bundle span{height:100%;border-right:2px solid var(--sheet)}
.bundle span:last-child{border-right:none}
.score{font-variation-settings:"wdth" 118;font-weight:750;font-size:22px;text-align:right;font-feature-settings:"tnum"}
.access{font-size:13.5px;line-height:1.3;color:var(--ink2);display:flex;gap:8px;align-items:center}
.dot{flex:none;width:10px;height:10px;border-radius:50%;border:2px solid currentColor}
.a-High{color:var(--green)} .a-Medium{color:var(--orange)} .a-Low-Medium{color:var(--orange)} .a-Low{color:var(--down)} .a-Check{color:var(--slate)}
.a-High .dot{background:var(--green)} .a-Medium .dot{background:var(--orange)}
.access b{color:var(--ink);font-weight:600}
.detail{padding:4px 22px 22px 84px;display:grid;grid-template-columns:1.1fr 1fr;gap:28px;font-size:14.5px;color:var(--ink2)}
.detail table{border-collapse:collapse;width:100%}
.detail td{padding:5px 0;border-bottom:1px solid #edf0f3}
.detail td:last-child{text-align:right;font-feature-settings:"tnum";color:var(--ink);font-weight:600}
.detail td i{display:inline-block;width:14px;height:5px;border-radius:3px;margin-right:8px;vertical-align:middle}
.facts p{margin-bottom:6px}.facts b{color:var(--ink);font-weight:600}
/* lenses */
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.tag{font-size:12px;font-weight:600;line-height:1;padding:4px 8px;border-radius:20px;background:#eef1f4;color:var(--ink2);white-space:nowrap}
.tag.t-Steady{background:#e3f3ea;color:#1f6e3e} .tag.t-High-growth{background:#e5edfa;color:#1d4f9f} .tag.t-Fixable{background:#fbeee3;color:#9a4c17} .tag.t-Between,.tag.t-Numbers{background:#eceff2;color:var(--slate)}
.corr{background:var(--sheet);border:1px solid var(--rule);border-radius:10px;padding:22px}
.corr .flag{display:inline-block;font-weight:700;font-size:13px;letter-spacing:.04em;padding:4px 10px;border-radius:4px;margin-bottom:12px}
.flag.green{background:#e3f3ea;color:#1f6e3e}.flag.amber{background:#fdf0dc;color:#94580a}.flag.red{background:#fbe4e0;color:#a3301f}
.corr h3{font-size:19px;font-weight:700;margin-bottom:16px;max-width:60ch}
.cbar{display:flex;height:34px;border-radius:6px;overflow:hidden;margin-bottom:16px}
.cbar span{display:flex;align-items:center;padding-left:10px;color:#fff;font-size:13px;font-weight:600;border-right:2px solid var(--sheet);white-space:nowrap;overflow:hidden}
.cbar span:last-child{border-right:none}
.clist{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px 24px;font-size:14px;color:var(--ink2)}
.clist b{display:block;color:var(--ink);font-size:15px}
.clist i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:7px;vertical-align:-1px}
.buckets{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:22px}
.bucket{border-top:3px solid var(--ink);padding-top:10px;font-size:14px;color:var(--ink2)}
.bucket b{display:block;color:var(--ink);font-size:15.5px}
@media (max-width:860px){.buckets{grid-template-columns:1fr}.cbar span{font-size:0;padding:0}}
/* bucket key above the ranking */
.bkey{display:grid;grid-template-columns:repeat(4,1fr);gap:10px 18px;margin:0 0 18px;font-size:13.5px;color:var(--ink2);line-height:1.4}
.bkey .tag{display:inline-block;margin:0 0 5px}
.bkey>span{display:flex;flex-direction:column;align-items:flex-start}
@media (max-width:860px){.bkey{grid-template-columns:1fr 1fr}}
/* changes */
.changes{display:grid;gap:12px}
.chg{display:grid;grid-template-columns:118px 1fr;gap:18px;padding:14px 0;border-bottom:1px solid var(--rule)}
.move{font-variation-settings:"wdth" 118;font-weight:750;font-size:18px;font-feature-settings:"tnum"}
.move.up{color:var(--up)} .move.down,.move.out{color:var(--down)} .move.new{color:var(--blue)} .move.same{color:var(--mute)}
.chg h3{font-size:16.5px;font-weight:650;margin-bottom:3px}
.chg p{font-size:15px;color:var(--ink2)}
.chg ul{margin-top:6px;padding-left:18px;font-size:14px;color:var(--ink2)}
/* funnel */
.funnel{display:grid;gap:10px;max-width:880px}
.fstep{display:grid;grid-template-columns:110px 1fr;align-items:center;gap:18px}
.fnum{font-variation-settings:"wdth" 125;font-weight:800;font-size:28px;text-align:right;font-feature-settings:"tnum"}
.fbar{position:relative;height:38px;display:flex;align-items:center}
.fbar::before{content:"";position:absolute;left:0;top:0;bottom:0;width:var(--w);background:linear-gradient(90deg,var(--blue),#5b8ee0);border-radius:6px;min-width:6px}
.fbar span{position:relative;padding-left:14px;font-size:14.5px;color:var(--ink)}
.fbar.narrow span{padding-left:calc(var(--w) + 14px)}
.fbar:not(.narrow) span{color:#fff}
/* steps */
.steps{list-style:none;counter-reset:s;display:grid;grid-template-columns:repeat(5,1fr);gap:20px}
.steps li{counter-increment:s;border-top:3px solid var(--ink);padding-top:12px;font-size:14.5px;color:var(--ink2)}
.steps li::before{content:counter(s);font-variation-settings:"wdth" 125;font-weight:800;font-size:22px;color:var(--ink);display:block;margin-bottom:4px}
.steps b{display:block;color:var(--ink);font-size:15.5px;margin-bottom:4px}
footer{padding:40px 0 60px;border-top:1px solid var(--rule);font-size:14px;color:var(--mute)}
footer p{max-width:80ch;margin-bottom:8px}
@media (max-width:860px){
  details>summary{grid-template-columns:34px 1fr 56px;gap:10px 14px;padding:14px 16px}
  .bundle{grid-column:2/4;grid-row:2}
  .access{grid-column:2/4;grid-row:3}
  .pos{font-size:22px}.score{font-size:19px}
  .detail{grid-template-columns:1fr;padding:0 16px 18px 16px}
  .chg{grid-template-columns:1fr;gap:4px}
  .steps{grid-template-columns:1fr 1fr}
  .fstep{grid-template-columns:80px 1fr}.fnum{font-size:21px}
  .wrap{padding:0 16px}
}
@media (prefers-reduced-motion:no-preference){
  .bundle span{transform-origin:left;animation:lay .9s cubic-bezier(.2,.7,.2,1) both;animation-delay:calc(var(--i) * 60ms)}
  @keyframes lay{from{transform:scaleX(0)}to{transform:scaleX(1)}}
}
</style></head>
<body>
<header class="top"><div class="wrap">
  <div class="byline"><span>By William Mikollovci</span><span id="asof"></span><span>Updated automatically every Monday</span></div>
  <h1>UK digital infrastructure: the ten best-fit companies</h1>
  <p class="intro">A screen of every UK fibre, wireless, data-centre and network-services company that files full accounts, ranked against a written investment thesis. It reads public Companies House filings each week and explains every change in the ranking.</p>
  <div class="week"><b id="headline"></b><span id="checked"></span></div>
</div></header>

<main>
<section><div class="wrap">
  <h2>The top ten</h2>
  <p class="sub">Each bar is a bundle of six strands, one per scoring criterion, so you can see why a company ranks where it does. How easy a company would be to buy is shown separately and never added to the score. Select a company for its numbers.</p>
  <div class="legend" id="legend"></div>
  <div class="bkey" id="bkey" hidden>
    <span><span class="tag t-Steady">Steady compounder</span>Recurring revenue, stable margins. Suits core infrastructure funds.</span>
    <span><span class="tag t-Fixable">Fixable dip</span>Falling or thin results with a possible fix. Suits value-add funds.</span>
    <span><span class="tag t-High-growth">High-growth</span>Turnover up 25%+ in a year, lumpier profit. Suits growth PE.</span>
    <span><span class="tag t-Between">Between buckets</span>Fits none cleanly; the reason is in each company's detail.</span>
  </div>
  <ol class="rank" id="rank"></ol>
</div></section>

<section id="corr-section" hidden><div class="wrap">
  <h2>Is the top ten really ten bets?</h2>
  <p class="sub">Each company is tagged with what its revenue mainly depends on. Companies that depend on the same thing would fall together, so they count as one bet. The tags are judgement calls from each company's business description and are shown for review.</p>
  <div class="corr" id="corr"></div>
  <div class="buckets">
    <div class="bucket"><b>Steady compounder</b>Recurring-type revenue and stable margins. Suits core and core-plus infrastructure funds.</div>
    <div class="bucket"><b>Fixable dip</b>A falling or thin result with a possible fix still to be confirmed. Suits value-add funds.</div>
    <div class="bucket"><b>High-growth</b>Turnover up 25% or more in a year, with lumpier profit. Suits growth and mid-market PE.</div>
  </div>
</div></section>

<section><div class="wrap">
  <h2>What changed</h2>
  <p class="sub" id="changes-sub"></p>
  <div class="changes" id="changes"></div>
</div></section>

<section><div class="wrap">
  <h2>From 48,467 companies to ten</h2>
  <p class="sub">Each filter comes from the thesis. Every company removed is logged with a reason in the repository.</p>
  <div class="funnel" id="funnel"></div>
</div></section>

<section><div class="wrap">
  <h2>How it works</h2>
  <p class="sub">Five steps, run on GitHub's servers with Python. The ranking and this page rebuild themselves every week.</p>
  <ol class="steps">
    <li><b>Write the thesis</b>A testable claim about the sector, with kill criteria, turned into a criteria file.</li>
    <li><b>Pull the register</b>Companies House bulk data filtered by industry code, status and accounts type.</li>
    <li><b>Read the accounts</b>Digital tags first, the text of the accounts as a backup, with a currency check.</li>
    <li><b>Clean and check</b>Owners traced through parent companies, duplicates merged, off-thesis firms removed.</li>
    <li><b>Score and explain</b>Six weighted criteria; each week's moves explained from the points that changed.</li>
  </ol>
</div></section>
</main>

<footer><div class="wrap">
  <p>Contains public sector information licensed under the <a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/">Open Government Licence v3.0</a>, from Companies House.</p>
  <p>Illustrative analysis from public information only. Not investment advice, and not a view on any company's prospects. Revenue visibility and debt capacity scores are estimates; figures read from the text of accounts should be checked against the filing.</p>
  <p>Built with Python, GitHub Actions and Claude. <a href="https://github.com/PE-Project-WM/infra-deal-scanner">Method and code</a>.</p>
</div></footer>

<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const U = D.update, W = D.weights;
const COLORS = {revenue_visibility:'var(--blue)', strategy_fit:'var(--orange)', size_fit:'var(--green)', margin_quality:'var(--brown)', data_completeness:'var(--slate)', debt_capacity:'var(--violet)'};
const LABEL = k => k.replace(/_/g,' ').replace(/^./, c => c.toUpperCase());
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmtDate = d => new Date(d + 'T12:00:00').toLocaleDateString('en-GB', {day:'numeric', month:'long', year:'numeric'});
const money = v => '£' + (v/1e6).toFixed(1) + 'm';
const SEG = {'Fibre and wired telecoms networks':'Fibre networks','Wireless networks, towers and fixed wireless':'Wireless','Satellite networks':'Satellite','Other telecoms networks':'Telecoms services','Data centres, data processing and hosting':'Data centres and hosting','Building and maintaining telecoms and utility networks':'Network build and maintenance'};

document.getElementById('asof').textContent = 'Last run ' + fmtDate(U.date);
document.getElementById('headline').textContent = U.headline + '.';
document.getElementById('checked').textContent = `${U.companies_checked} ranked companies checked; ${U.events_count} Companies House ${U.events_count === 1 ? 'event' : 'events'}.`;
document.getElementById('legend').innerHTML = Object.keys(W).map(k => `<span><i style="background:${COLORS[k]}"></i>${LABEL(k)} (${W[k]})</span>`).join('');

document.getElementById('rank').innerHTML = U.top10.map((t, idx) => {
  const strands = Object.keys(W).map((k, i) => `<span style="width:${t.pts[k]}%;background:${COLORS[k]};--i:${idx*6+i}" title="${LABEL(k)}: ${t.pts[k].toFixed(1)} of ${W[k]}"></span>`).join('');
  const rows = Object.keys(W).map(k => `<tr><td><i style="background:${COLORS[k]}"></i>${LABEL(k)}</td><td>${t.pts[k].toFixed(1)} / ${W[k]}</td></tr>`).join('');
  const acc = t.access.replace(/\s+/g,'');
  return `<li><details><summary>
    <span class="pos">${t.rank}</span>
    <span class="name">${esc(t.company)}<small>${esc(SEG[t.segment] || t.segment)}${t.town ? ', ' + esc(t.town) : ''}</small>${t.lens ? `<span class="tags"><span class="tag t-${t.lens.deal_type.split(' ')[0]}">${esc(t.lens.deal_type)}</span><span class="tag">${esc(t.lens.demand_driver)}</span></span>` : ''}</span>
    <span class="bundle" role="img" aria-label="Score ${t.score.toFixed(1)} out of 100">${strands}</span>
    <span class="score">${t.score.toFixed(1)}</span>
    <span class="access a-${acc}"><span class="dot"></span><span><b>${esc(t.access)}</b> access</span></span>
  </summary>
  <div class="detail"><table>${rows}</table>
    <div class="facts"><p><b>Turnover</b> ${money(t.turnover)}${t.margin != null ? ` &nbsp; <b>EBITDA margin</b> ${Math.round(t.margin*100)}%` : ''}</p>
    <p><b>Thesis fit</b> ${esc(t.fit)}</p><p><b>Accessibility</b> ${esc(t.access_note)}</p>
    ${t.lens ? `<p><b>Deal type</b> ${esc(t.lens.deal_type)}: ${esc(t.lens.deal_type_reason)}. ${esc(t.lens.fund_fit)}.</p>
    <p><b>Demand driver</b> ${esc(t.lens.demand_driver)}${t.lens.second_driver ? ', then ' + esc(t.lens.second_driver) : ''} (${esc(t.lens.driver_basis)}).</p>` : ''}</div></div>
  </details></li>`;
}).join('');

if (D.corr) {
  const c = D.corr.top_n, PAL = ['#2463c7','#e2742a','#2e9a57','#86563a','#7a4fd0','#64707e','#c2412d','#1d8a8a'];
  document.getElementById('corr-section').hidden = false;
  document.getElementById('bkey').hidden = false;
  document.getElementById('corr').innerHTML = `<span class="flag ${c.flag}">${c.flag.toUpperCase()}</span>
    <h3>${esc(D.corr.headline)}.</h3>
    <div class="cbar" role="img" aria-label="Top ten split by macro factor">${c.factors.map((f, i) => `<span style="width:${f.share*100}%;background:${PAL[i % PAL.length]}" title="${esc(f.factor)}: ${f.count}">${f.count}</span>`).join('')}</div>
    <div class="clist">${c.factors.map((f, i) => `<div><b><i style="background:${PAL[i % PAL.length]}"></i>${esc(f.factor)}</b>${f.count} of ${c.n}: ${f.companies.map(esc).join(', ')}</div>`).join('')}</div>
    <p class="sub" style="margin:16px 0 0;font-size:13.5px">Amber when ${Math.round(D.corr.thresholds.amber_share*100)}% or more of the top ten share one factor, red at ${Math.round(D.corr.thresholds.red_share*100)}%. Across the top twenty it is about ${D.corr.top_20.effective_bets.toFixed(0)} independent bets.</p>`;
}

const moves = U.top10_moves;
document.getElementById('changes-sub').textContent = U.previous_scored_on
  ? `Compared with the ranking of ${fmtDate(U.previous_scored_on)}. Each reason comes from the score points that moved and the filings behind them.`
  : 'The first weekly comparison will appear here.';
const label = m => ({up:`${m.from} → ${m.to}`, down:`${m.from} → ${m.to}`, new:`New at ${m.to}`, out:`${m.from} → out`, same:`Stays ${m.to}`})[m.kind];
document.getElementById('changes').innerHTML = moves.length ? moves.map(m => `<div class="chg">
  <span class="move ${m.kind}">${label(m)}</span>
  <div><h3>${esc(m.company)}</h3><p>${esc(m.reasons.join('; '))}.</p>
  ${m.events.length ? `<ul>${m.events.map(e => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}</div></div>`).join('')
  : '<p class="sub">No changes to the top ten in this run.</p>';

const maxN = D.funnel[0][1];
document.getElementById('funnel').innerHTML = D.funnel.map(([lab, n]) => {
  const w = Math.max(1.2, Math.sqrt(n / maxN) * 100);
  return `<div class="fstep"><span class="fnum">${n.toLocaleString('en-GB')}</span><div class="fbar ${w < 45 ? 'narrow' : ''}" style="--w:${w.toFixed(1)}%"><span>${esc(lab)}</span></div></div>`;
}).join('') + `<p class="sub" style="margin-top:8px;font-size:14px">Bar widths use a square-root scale so the small steps stay visible. 842 of the 1,209 companies file scanned PDF accounts that this version cannot read yet.</p>`;
</script>
</body></html>'''
open(f'{ROOT}/docs/index.html', 'w').write(page.replace('__DATA__', payload))
open(f'{ROOT}/docs/.nojekyll', 'w').write('')
print('Built docs/index.html')
