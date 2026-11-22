"""Workbook part 2: Assumptions, Valuation (DCF + LBO per company), Notes."""
from part1 import *

# Valuation companies: inputs from the deep dive (data/deep_dive), £ unless stated. Sources in comments.
COS = [
    dict(name='VEA Group', rev=32.561, rev_prior=21.059, ebitda=9.954, qoe=round(0.22*32.561-9.954,3), da=0.152, capex=0.064, cash=12.689, debt=0.003,
         growth=0.10, margin=0.22, capex_pct=0.010, da_pct=0.005, nwc=0.05, fx=1.0, fy='FY Feb 2026',
         src='VEA Group Ltd accounts FY Feb 2026 (filed 30 Jun 2026): turnover £32.56m, operating profit £9.80m, depreciation £0.15m, capex £0.06m, cash £12.69m.',
         note='Margin jumped from 16% to 31% in one year. Adjustment normalises EBITDA to a 22% margin (average of the last two years); the deal is priced on that.'),
    dict(name='The Networking People', rev=18.099, rev_prior=15.519, ebitda=2.305, qoe=0.0, da=0.173, capex=0.875, cash=1.781, debt=0.055,
         growth=0.10, margin=0.127, capex_pct=0.025, da_pct=0.010, nwc=0.05, fx=1.0, fy='FY Mar 2026',
         src='TNP Ltd accounts FY Mar 2026 (filed 16 Oct 2026): turnover £18.10m, operating profit £2.13m, D&A £0.17m, capex £0.88m, cash £1.78m, finance leases £0.06m.',
         note='Bought by YFM Equity Partners in 2025; growth 10-17% a year over three years.'),
    dict(name='Satcom Global', rev=36.305, rev_prior=34.740, ebitda=6.272, qoe=0.0, da=1.276, capex=2.359, cash=1.056, debt=21.231,
         growth=0.03, margin=0.17, capex_pct=0.050, da_pct=0.035, nwc=0.05, fx=1.26, fy='FY Jun 2024',
         src='Satcom Global Ltd accounts FY Jun 2024 (filed 13 Mar 2025), in US$: turnover $36.31m, operating profit $5.00m, depreciation $0.27m, amortisation $1.00m, additions $2.36m, cash $1.06m, bank borrowings $21.23m. Converted at $1.26/£ (FY average, assumption).',
         note='Reports in US dollars; prior year restated (sales credit notes); latest accounts are for June 2024.'),
    dict(name='Clarus Networks', rev=26.681, rev_prior=18.308, ebitda=4.294, qoe=-1.223, da=0.241, capex=0.157, cash=3.151, debt=0.206,
         growth=0.08, margin=0.115, capex_pct=0.008, da_pct=0.009, nwc=0.05, fx=1.0, fy='FY Dec 2025',
         src='Clarus Networks Ltd accounts FY Dec 2025 (filed 30 Sep 2026): turnover £26.68m, operating profit £4.05m incl. other operating income £1.22m (2024: £0.04m), D&A £0.24m, capex £0.16m, cash £3.15m, borrowings £0.21m.',
         note='Other operating income of £1.22m treated as one-off and removed (quality-of-earnings adjustment).'),
    dict(name='MAP Group (UK)', rev=75.597, rev_prior=74.397, ebitda=18.110, qoe=round(0.20*75.597-18.110,3), da=0.391, capex=0.242, cash=5.469, debt=0.0,
         growth=0.02, margin=0.20, capex_pct=0.004, da_pct=0.005, nwc=0.05, fx=1.0, fy='FY Sep 2025',
         src='MAP Group (UK) Ltd accounts FY Sep 2025 (filed 26 Jun 2026): turnover £75.60m, operating profit £17.72m, depreciation £0.39m, capex £0.24m, cash £5.47m, no bank debt.',
         note='Margin rose from 16.9% to 23.4% in one year. Adjustment normalises EBITDA to a 20% margin. Employee-owned (EOT); net assets fell from £28.3m to £10.6m as the EOT purchase was funded.'),
]
YEARS = 5

def build_assumptions(wb):
    ws = wb.create_sheet('Assumptions')
    title(ws, 'Valuation assumptions (blue = input, yellow = key lever)', 'Change any blue cell and the Valuation sheet recalculates. Every figure has a source or a stated reason.')
    rows = [
        ('Price range (EV / EBITDA)', None, None, None),
        ('Entry multiple: low', 6.5, '0.0"x"', 'Listed telecom services trade at about 6.5x (Damodaran, Jan 2026). Illustrative floor.'),
        ('Entry multiple: base', 8.0, '0.0"x"', 'Below the 8.9x median for UK deals under £100m in TMT, LTM to Sep 2026 (MarktoMarket via Alinea, Autumn 2026).'),
        ('Walk-away multiple', 9.0, '0.0"x"', 'Thesis price discipline: above ~9x a bolt-on costs platform money and the buy-and-build arbitrage disappears.'),
        ('Discount rate (WACC build)', None, None, None),
        ('Risk-free rate', 0.045, PCT, 'UK 10-year gilt, approximate (assumption; check current yield).'),
        ('Equity risk premium', 0.055, PCT, 'Assumption: common UK range 5-6%.'),
        ('Beta', 1.10, '0.00', 'Assumption: telecom services / contracting.'),
        ('Small-company premium', 0.030, PCT, 'Assumption for unlisted firms with £10-80m turnover.'),
        ('Cost of equity', '=C9+C11*C10+C12', PCT, 'CAPM plus small-company premium.'),
        ('Pre-tax cost of debt', 0.080, PCT, 'Assumption: senior lending to small private firms.'),
        ('Tax rate', 0.25, PCT, 'UK main rate of corporation tax.'),
        ('Debt weight', 0.35, PCT, 'Assumption: target capital structure.'),
        ('WACC', '=(1-C16)*C13+C16*C14*(1-C15)', PCT, 'Weighted average cost of capital.'),
        ('Terminal growth (Gordon cross-check)', 0.02, PCT, 'Assumption: long-run UK nominal growth, conservative.'),
        ('Exit multiple (held flat to base entry)', '=C6', '0.0"x"', 'Thesis rule: exit held flat to entry; any expansion is upside.'),
        ('Buyout (LBO) structure', None, None, None),
        ('Senior debt at entry (x EBITDA)', 3.5, '0.0"x"', 'Assumption: typical for contracted UK lower mid-market; test against the debt cover check.'),
        ('Interest rate on debt', 0.09, PCT, 'Assumption: SONIA plus margin for small private credit.'),
        ('Transaction fees (% of EV)', 0.03, PCT, 'Assumption.'),
        ('Hold period (years)', 5, '0', 'Fixed at 5 years in this model.'),
        ('Target IRR (hurdle)', 0.20, PCT, 'Assumption: typical lower mid-market buyout hurdle.'),
        ('Minimum interest cover', 2.5, '0.0"x"', 'Assumption: (EBITDA - capex - tax) / interest; below this lenders push back.'),
    ]
    for i, (lab, val, fmt, why) in enumerate(rows, 4):
        a = ws.cell(row=i, column=2, value=lab)
        if val is None:
            a.font = font(bold=True, color=TEAL); continue
        a.font = font()
        c = ws.cell(row=i, column=3, value=val)
        is_input = not (isinstance(val, str) and val.startswith('='))
        c.font = font(BLUE if is_input else BLACK, bold=lab in ('Entry multiple: base', 'Walk-away multiple', 'WACC'))
        if lab in ('Entry multiple: base', 'Walk-away multiple', 'Senior debt at entry (x EBITDA)', 'Target IRR (hurdle)'):
            c.fill = PatternFill('solid', fgColor=YELLOW)
        c.number_format = fmt
        ws.cell(row=i, column=4, value=why).font = font(size=9, color='595959', italic=True)
    ws.column_dimensions['A'].width = 2; ws.column_dimensions['B'].width = 38; ws.column_dimensions['C'].width = 11; ws.column_dimensions['D'].width = 110
    return ws

# Assumption cell addresses
A = dict(low='Assumptions!$C$5', base='Assumptions!$C$6', walk='Assumptions!$C$7', wacc='Assumptions!$C$17', tax='Assumptions!$C$15',
         g='Assumptions!$C$18', exitm='Assumptions!$C$19', lev='Assumptions!$C$21', rate='Assumptions!$C$22', fees='Assumptions!$C$23',
         hurdle='Assumptions!$C$25', mincov='Assumptions!$C$26')

def build_models(wb):
    """One block per company: inputs, 5-year projection, DCF, LBO."""
    ws = wb.create_sheet('Models')
    title(ws, 'Company models: projection, DCF and buyout check (£m)', 'One block per company. Blue = input from the filed accounts or a stated assumption; black = formula; green = link to Assumptions.')
    out = {}
    r0 = 4
    for co in COS:
        r = r0
        ws.cell(row=r, column=1, value=co['name']).font = Font(name=F, bold=True, size=12, color=NAVY)
        ws.cell(row=r, column=3, value=co['fy']).font = font(italic=True, color='595959')
        r += 1
        inputs = [
            ('Turnover, latest year', co['rev'] / co['fx'], 'rev'),
            ('Turnover, prior year', co['rev_prior'] / co['fx'], 'revp'),
            ('Reported EBITDA (operating profit + D&A)', co['ebitda'] / co['fx'], 'ebitda'),
            ('Quality-of-earnings adjustment', co['qoe'] / co['fx'], 'qoe'),
            ('Cash', co['cash'] / co['fx'], 'cash'),
            ('Debt (bank borrowings and leases)', co['debt'] / co['fx'], 'debt'),
            ('Revenue growth, forecast', co['growth'], 'g'),
            ('D&A, % of turnover', co['da_pct'], 'da'),
            ('Capex, % of turnover', co['capex_pct'], 'cx'),
            ('Working capital, % of turnover', co['nwc'], 'nwc'),
        ]
        cell = {}
        for lab, val, key in inputs:
            ws.cell(row=r, column=2, value=lab).font = font()
            c = ws.cell(row=r, column=3, value=round(val, 4)); c.font = font(BLUE)
            c.number_format = PCT if key in ('g', 'm', 'da', 'cx', 'nwc') else '#,##0.00;(#,##0.00);-'
            if key == 'rev':
                c.comment = Comment(co['src'], 'Screener')
            if key == 'qoe' and co['qoe']:
                c.comment = Comment(co['note'], 'Screener')
            cell[key] = f'$C${r}'
            r += 1
        ws.cell(row=r, column=2, value='Adjusted EBITDA').font = font(bold=True)
        c = ws.cell(row=r, column=3, value=f"={cell['ebitda']}+{cell['qoe']}"); c.font = font(bold=True); c.number_format = '#,##0.00'
        cell['adj'] = f'$C${r}'; r += 1
        ws.cell(row=r, column=2, value='Adjusted EBITDA margin (held flat in the forecast)').font = font()
        c = ws.cell(row=r, column=3, value=f"={cell['adj']}/{cell['rev']}"); c.number_format = PCT
        c.comment = Comment(co['note'], 'Screener'); cell['m'] = f'$C${r}'; r += 1
        ws.cell(row=r, column=2, value='Net debt (negative = net cash)').font = font()
        c = ws.cell(row=r, column=3, value=f"={cell['debt']}-{cell['cash']}"); c.number_format = '#,##0.00;(#,##0.00);-'
        cell['nd'] = f'$C${r}'; r += 2

        # projection header
        hdr_r = r
        ws.cell(row=r, column=2, value='£m').font = font(bold=True)
        for y in range(YEARS + 1):
            h = ws.cell(row=r, column=3 + y, value=f'Year {y}' if y else 'Latest')
            h.font = Font(name=F, bold=True, color='FFFFFF'); h.fill = PatternFill('solid', fgColor=NAVY); h.alignment = Alignment(horizontal='center')
        r += 1
        col = lambda y: get_column_letter(3 + y)
        rows = {}
        def line(label, key, f0, fn, fmt='#,##0.00;(#,##0.00);-', bold=False):
            nonlocal r
            ws.cell(row=r, column=2, value=label).font = font(bold=bold)
            for y in range(YEARS + 1):
                f = f0 if y == 0 else fn(y)
                if f is None:
                    continue
                c = ws.cell(row=r, column=3 + y, value=f); c.number_format = fmt; c.font = font(bold=bold)
            rows[key] = r; r += 1
        line('Turnover', 'rev', f"={cell['rev']}", lambda y: f"={col(y-1)}{r}*(1+{cell['g']})")
        line('EBITDA', 'ebitda', f"={cell['adj']}", lambda y: f"={col(y)}{rows['rev']}*{cell['m']}", bold=True)
        line('D&A', 'da', None, lambda y: f"={col(y)}{rows['rev']}*{cell['da']}")
        line('EBIT', 'ebit', None, lambda y: f"={col(y)}{rows['ebitda']}-{col(y)}{rows['da']}")
        line('Tax on EBIT', 'tax', None, lambda y: f"=-MAX(0,{col(y)}{rows['ebit']})*{A['tax']}")
        line('Capex', 'cx', None, lambda y: f"=-{col(y)}{rows['rev']}*{cell['cx']}")
        line('Change in working capital', 'dnwc', None, lambda y: f"=-({col(y)}{rows['rev']}-{col(y-1)}{rows['rev']})*{cell['nwc']}")
        line('Unlevered free cash flow', 'fcf', None, lambda y: f"={col(y)}{rows['ebitda']}+{col(y)}{rows['tax']}+{col(y)}{rows['cx']}+{col(y)}{rows['dnwc']}", bold=True)
        line('Discount factor', 'df', None, lambda y: f"=1/(1+{A['wacc']})^{y}", fmt='0.000')
        line('PV of free cash flow', 'pv', None, lambda y: f"={col(y)}{rows['fcf']}*{col(y)}{rows['df']}")
        r += 1
        # DCF summary
        def kv(label, formula, fmt, key, bold=False):
            nonlocal r
            ws.cell(row=r, column=2, value=label).font = font(bold=bold)
            c = ws.cell(row=r, column=3, value=formula); c.number_format = fmt; c.font = font(bold=bold)
            cell[key] = f'$C${r}'; r += 1
        Y = col(YEARS)
        kv('Sum of PV of free cash flow', f"=SUM(D{rows['pv']}:{Y}{rows['pv']})", '#,##0.00', 'sumpv')
        kv('Terminal value (exit multiple)', f"={Y}{rows['ebitda']}*{A['exitm']}", '#,##0.00', 'tv')
        kv('PV of terminal value', f"={cell['tv']}*{Y}{rows['df']}", '#,##0.00', 'pvtv')
        kv('DCF enterprise value', f"={cell['sumpv']}+{cell['pvtv']}", '#,##0.00', 'dcf', bold=True)
        kv('Implied EV / EBITDA', f"=IFERROR({cell['dcf']}/{cell['adj']},0)", '0.0"x"', 'dcfm')
        kv('Terminal value share of DCF EV', f"=IFERROR({cell['pvtv']}/{cell['dcf']},0)", PCT, 'tvshare')
        kv('Gordon cross-check EV', f"={cell['sumpv']}+{Y}{rows['fcf']}*(1+{A['g']})/({A['wacc']}-{A['g']})*{Y}{rows['df']}", '#,##0.00', 'gordon')
        r += 1
        # LBO
        ws.cell(row=r, column=2, value='Buyout check at base entry multiple').font = font(bold=True, color=TEAL); r += 1
        kv('Entry EV (base multiple x adjusted EBITDA)', f"={cell['adj']}*{A['base']}", '#,##0.00', 'ev0')
        kv('Senior debt raised', f"={cell['adj']}*{A['lev']}", '#,##0.00', 'd0')
        kv('Sponsor equity (EV + fees - debt; cash-free, debt-free)', f"={cell['ev0']}*(1+{A['fees']})-{cell['d0']}", '#,##0.00', 'eq0')
        lbo_hdr = r
        for y in range(YEARS + 1):
            h = ws.cell(row=r, column=3 + y, value=f'Year {y}' if y else 'Entry')
            h.font = Font(name=F, bold=True, color='FFFFFF'); h.fill = PatternFill('solid', fgColor=TEAL); h.alignment = Alignment(horizontal='center')
        r += 1
        line('Debt, opening', 'dopen', None, lambda y: f"={cell['d0']}" if y == 1 else f"={col(y-1)}{r+3}")
        line('Interest', 'int', None, lambda y: f"={col(y)}{rows['dopen']}*{A['rate']}")
        line('Cash available to repay debt (FCF - interest)', 'avail', None, lambda y: f"={col(y)}{rows['fcf']}-{col(y)}{rows['int']}")
        line('Debt, closing (cash sweep)', 'dclose', f"={cell['d0']}", lambda y: f"=MAX(0,{col(y)}{rows['dopen']}-MAX(0,{col(y)}{rows['avail']}))")
        line('Leverage (closing debt / EBITDA)', 'levx', f"=IFERROR(C{r}/C{rows['ebitda']},0)".replace(f'C{r}/', f"C{r-1}/"), lambda y: f"=IFERROR({col(y)}{rows['dclose']}/{col(y)}{rows['ebitda']},0)", fmt='0.0"x"')
        line('Interest cover ((EBITDA - capex - tax) / interest)', 'cov', None, lambda y: f"=IFERROR(({col(y)}{rows['ebitda']}+{col(y)}{rows['cx']}+{col(y)}{rows['tax']})/{col(y)}{rows['int']},99)", fmt='0.0"x"')
        r += 1
        kv('Exit EV (exit multiple x Year 5 EBITDA)', f"={Y}{rows['ebitda']}*{A['exitm']}", '#,##0.00', 'ev5')
        kv('Exit equity (EV - debt + 0 cash)', f"={cell['ev5']}-{Y}{rows['dclose']}", '#,##0.00', 'eq5')
        kv('MOIC', f"=IFERROR({cell['eq5']}/{cell['eq0']},0)", '0.00"x"', 'moic', bold=True)
        kv('IRR (5-year hold, no interim dividends)', f"=IFERROR({cell['moic']}^(1/5)-1,0)", PCT, 'irr', bold=True)
        kv('Lowest interest cover over the hold', f"=MIN(D{rows['cov']}:{Y}{rows['cov']})", '0.0"x"', 'mincov')
        kv('Highest entry price that still clears the hurdle (EV/EBITDA)',
           f"=IFERROR(({cell['eq5']}/(1+{A['hurdle']})^5+{cell['d0']})/({cell['adj']}*(1+{A['fees']})),0)", '0.0"x"', 'maxm', bold=True)
        cell['revcell'] = cell['rev']
        out[co['name']] = cell
        r0 = r + 2
    ws.column_dimensions['A'].width = 2; ws.column_dimensions['B'].width = 52
    for c in 'CDEFGH':
        ws.column_dimensions[c].width = 12
    return out

def build_valuation(wb, out):
    ws = wb.create_sheet('Valuation', 1)
    title(ws, 'Valuation check: top 5 (illustrative)', 'Price range, DCF and a buyout (LBO) check for each company. All values in £m. Links to Models and Assumptions; nothing is typed in here.')
    hdr = ['Company', 'Turnover (£m)', 'Adj. EBITDA (£m)', 'Adj. margin', 'Net debt (£m)', 'EV at low (£m)', 'EV at base (£m)', 'EV at walk-away (£m)',
           'DCF EV (£m)', 'DCF EV / EBITDA', 'Buyout IRR', 'Buyout MOIC', 'Lowest interest cover', 'Max entry multiple for hurdle', 'Verdict']
    header_row(ws, 4, hdr)
    for i, co in enumerate(COS):
        r = 5 + i; c = out[co['name']]; M = lambda k: f"=Models!{c[k]}"
        vals = [co['name'], M('rev'), M('adj'), f"=Models!{c['adj']}/Models!{c['rev']}", M('nd'),
                f"=Models!{c['adj']}*{A['low']}", f"=Models!{c['adj']}*{A['base']}", f"=Models!{c['adj']}*{A['walk']}",
                M('dcf'), M('dcfm'), M('irr'), M('moic'), M('mincov'), M('maxm')]
        fmts = [None, '#,##0.0', '#,##0.0', PCT, '#,##0.0;(#,##0.0);-', '#,##0.0', '#,##0.0', '#,##0.0', '#,##0.0', '0.0"x"', PCT, '0.00"x"', '0.0"x"', '0.0"x"']
        for j, (v, fmt) in enumerate(zip(vals, fmts), 1):
            cl = ws.cell(row=r, column=j, value=v); cl.font = font(GREEN if j > 1 else BLACK, bold=j == 1)
            if fmt: cl.number_format = fmt
            cl.border = BOX
        ws.cell(row=r, column=15, value=f'=IF(AND(K{r}>={A["hurdle"]},M{r}>={A["mincov"]}),"Clears hurdle at base price",IF(K{r}>={A["hurdle"]},"Returns OK, debt too heavy","Below hurdle at base price"))').border = BOX
    ws['A11'] = 'How to read this'; ws['A11'].font = font(bold=True, color=TEAL)
    notes = ['EV = enterprise value (price for the whole business, before debt). Low / base / walk-away use the multiples on the Assumptions sheet.',
             'DCF EV values five years of cash flow plus an exit value at the base multiple (held flat, as the thesis requires).',
             'Buyout IRR and MOIC: buy at the base multiple with senior debt, repay debt from cash flow, sell after 5 years at the same multiple.',
             'Max entry multiple for hurdle: the highest price (EV / EBITDA) at which the buyout still earns the target IRR. Compare it with the walk-away multiple.',
             'Illustrative only: projections are simple percentage assumptions, not management forecasts. Public data only; not investment advice.']
    for i, t in enumerate(notes, 12):
        ws.cell(row=i, column=1, value=t).font = font(size=9, color='595959')
    for i, w in enumerate([24, 11, 11, 10, 11, 11, 11, 13, 11, 11, 10, 10, 12, 14, 28], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'B5'
