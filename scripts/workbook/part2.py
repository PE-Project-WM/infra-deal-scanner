"""Workbook part 2: Assumptions, Valuation (DCF + LBO per company), Notes."""
from part1 import *

# Valuation companies: inputs from the deep dive (data/deep_dive), £ unless stated. Sources in comments.
# The three companies are built from the pipeline's own outputs, so the workbook always matches the live ranking:
# turnover, reported and rule-based EBITDA (data/outputs/ranking_latest.csv, normalise.py), business type, its price
# range and debt (config/thesis/<sector>.json), and cash, debt, D&A and capex from config/balance_sheet.csv where checked.
import os as _os, sys as _sys, json as _json
import pandas as _pd
_REPO = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_sys.path.insert(0, _os.path.join(_REPO, 'scripts'))
from settings import TYPES as _TYPES
_R = _pd.read_csv(f'{_REPO}/data/outputs/ranking_latest.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber')
_BS = _pd.read_csv(f'{_REPO}/config/balance_sheet.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber')
_H = _pd.read_csv(f'{_REPO}/data/outputs/history.csv', dtype={'CompanyNumber': str})

PICK = [   # company number, short name, financial year, extra note on the accounts
    ('13433533', 'VEA Group', 'FY Feb 2026', 'VEA Group Ltd accounts FY Feb 2026 (filed 30 Jun 2026).',
     'Margin jumped from about 17% to 31% in one year. Rule R3 prices the deal on the two-year average margin (23%) until a second year shows it holds, so the quality-of-earnings line takes EBITDA from £9.95m to £7.60m. Set it to 0 to price on the reported figure.'),
    ('SC492820', 'Clarus Networks', 'FY Dec 2025', 'Clarus Networks Ltd accounts FY Dec 2025 (filed 30 Sep 2026); bank loans £0.18m, leases £0.04m.',
     'Rule R1: £1.22m of R&D expenditure credit (RDEC) in other operating income is taken out as not trading EBITDA (2024: £0.04m).'),
    ('04186486', 'Beacon Communication Services', 'FY Apr 2025', 'Beacon Communication Services Ltd accounts FY Apr 2025 (filed 27 Dec 2025, read by OCR and checked).',
     'Holds £21.3m of other investments and property outside the trading business (bought £9.6m in the year) and owes the director £3.5m on current account: a buyer would carve these out, so they are left out of the price.'),
]
BEACON_BS = dict(cash=3.427, debt=2.387, da=0.339, capex=0.464)   # from the accounts (not yet in config/balance_sheet.csv)


def _company(num, name, fy, src, note):
    r = _R.loc[num]
    t = _TYPES[r['business_type']]
    rev, e_rep, e_norm = r['turnover'] / 1e6, r['ebitda_reported'] / 1e6, r['ebitda'] / 1e6
    h = _H[_H['CompanyNumber'] == num].sort_values('fy')
    rev_prior = h['sales'].iloc[-2] / 1e6 if len(h) >= 2 else rev
    if num in _BS.index:
        b = _BS.loc[num].fillna(0)
        cash, debt = b['cash'] / 1e6, (b['bank_debt'] + b['leases_hp'] + b['shareholder_or_group_loans']) / 1e6
        capex = b['capex'] / 1e6
    else:
        cash, debt, capex = BEACON_BS['cash'], BEACON_BS['debt'], BEACON_BS['capex']
    da = {'13433533': 0.152, 'SC492820': 0.241, '04186486': BEACON_BS['da']}[num]   # depreciation in the same accounts
    lo, mid, hi = t['price_range']['low'], t['price_range']['mid'], t['price_range']['high']
    return dict(name=name, rev=round(rev, 3), rev_prior=round(rev_prior, 3), ebitda=round(e_rep, 3), qoe=round(e_norm - e_rep, 3),
                da=da, capex=round(capex, 3), cash=round(cash, 3), debt=round(debt, 3),
                growth=0.06, margin=round(e_norm / rev, 3), capex_pct=round(max(capex / rev, 0.002), 3), da_pct=round(da / rev, 3),
                nwc=0.05, fx=1.0, fy=fy, mult=(lo, mid, hi), lev=t['debt_turns'], kind=t['label'],
                src=f"{src} Turnover £{rev:.2f}m, reported EBITDA £{e_rep:.2f}m, cash £{cash:.2f}m, borrowings and leases £{debt:.2f}m. "
                    f"Live rank {int(r['rank'])} of the ranking; business type {t['label'].lower()} (price range {lo:.0f}-{hi:.0f}x, debt {t['debt_turns']:.1f}x).",
                note=note)


COS = [_company(*p) for p in PICK]
YEARS = 5

def build_assumptions(wb):
    ws = wb.create_sheet('Assumptions')
    title(ws, 'Valuation assumptions (blue = input, yellow = key lever)', 'Change any blue cell and the Valuation sheet recalculates. Every figure has a source or a stated reason.')
    rows = [
        ('Price range (EV / EBITDA)', None, None, None),
        ('Default price range: low', 6.0, '0.0"x"', 'Repeat-revenue services: Gamma traded at about 6x before its bid; UK private deals under £250m median 6.2x (H1 2025). Each company has its own range on the Models sheet.'),
        ('Default price range: middle', 7.0, '0.0"x"', 'Between Gamma before its bid (about 6x) and the Epiris take-private (about 7.6x, Sept 2026).'),
        ('Default price range: high', 8.0, '0.0"x"', 'SPIE trades at about 8x; above this the buy-and-build arbitrage disappears.'),
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
        ('Default senior debt at entry (x EBITDA)', 3.0, '0.0"x"', 'As in the website price check (2.5x for project contractors); each company has its own on the Models sheet.'),
        ('Interest rate on debt', 0.085, PCT, 'As in the website price check: SONIA plus a margin for small private credit.'),
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
        c.font = font(BLUE if is_input else BLACK, bold=lab in ('WACC',))
        if lab in ('Target IRR (hurdle)',):
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
            ('Price range: low (x EBITDA)', co['mult'][0], 'ml'),
            ('Price range: middle, used to buy and to sell (x EBITDA)', co['mult'][1], 'mm'),
            ('Price range: high (x EBITDA)', co['mult'][2], 'mh'),
            ('Senior debt at entry (x EBITDA)', co['lev'], 'lev'),
        ]
        cell = {}
        for lab, val, key in inputs:
            ws.cell(row=r, column=2, value=lab).font = font()
            c = ws.cell(row=r, column=3, value=round(val, 4)); c.font = font(BLUE)
            c.number_format = PCT if key in ('g', 'm', 'da', 'cx', 'nwc') else '0.0"x"' if key in ('ml', 'mm', 'mh', 'lev') else '#,##0.00;(#,##0.00);-'
            if key in ('mm', 'lev'):
                c.fill = PatternFill('solid', fgColor=YELLOW)
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
        kv('Terminal value (exit at the middle multiple, held flat)', f"={Y}{rows['ebitda']}*{cell['mm']}", '#,##0.00', 'tv')
        kv('PV of terminal value', f"={cell['tv']}*{Y}{rows['df']}", '#,##0.00', 'pvtv')
        kv('DCF enterprise value', f"={cell['sumpv']}+{cell['pvtv']}", '#,##0.00', 'dcf', bold=True)
        kv('Implied EV / EBITDA', f"=IFERROR({cell['dcf']}/{cell['adj']},0)", '0.0"x"', 'dcfm')
        kv('Terminal value share of DCF EV', f"=IFERROR({cell['pvtv']}/{cell['dcf']},0)", PCT, 'tvshare')
        kv('Gordon cross-check EV', f"={cell['sumpv']}+{Y}{rows['fcf']}*(1+{A['g']})/({A['wacc']}-{A['g']})*{Y}{rows['df']}", '#,##0.00', 'gordon')
        r += 1
        # LBO
        ws.cell(row=r, column=2, value='Buyout check: buy at the middle multiple, sell at the same multiple after 5 years').font = font(bold=True, color=TEAL); r += 1
        kv('Entry EV (middle multiple x adjusted EBITDA)', f"={cell['adj']}*{cell['mm']}", '#,##0.00', 'ev0')
        kv('Senior debt raised', f"={cell['adj']}*{cell['lev']}", '#,##0.00', 'd0')
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
        line('Cash built up once debt is repaid', 'cash', '=0', lambda y: f"={col(y-1)}{r}+MAX(0,{col(y)}{rows['avail']}-{col(y)}{rows['dopen']})")
        r += 1
        kv('Exit EV (middle multiple x Year 5 EBITDA)', f"={Y}{rows['ebitda']}*{cell['mm']}", '#,##0.00', 'ev5')
        kv('Exit equity (EV - debt + cash built up, as in the website price check)', f"={cell['ev5']}-{Y}{rows['dclose']}+{Y}{rows['cash']}", '#,##0.00', 'eq5')
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
    title(ws, 'Valuation check: the three realistic mid-market targets (illustrative)', 'VEA, Clarus and Beacon: the top-ten companies a mid-market buyer could approach today. Price range, DCF and a buyout (LBO) check, in £m. Links to Models and Assumptions; nothing is typed in here.')
    hdr = ['Company', 'Turnover (£m)', 'Adj. EBITDA (£m)', 'Adj. margin', 'Net debt (£m)', 'EV at low (£m)', 'EV at middle (£m)', 'EV at high (£m)',
           'DCF EV (£m)', 'DCF EV / EBITDA', 'Buyout IRR', 'Buyout MOIC', 'Lowest interest cover', 'Max entry multiple for hurdle', 'Verdict']
    header_row(ws, 4, hdr)
    for i, co in enumerate(COS):
        r = 5 + i; c = out[co['name']]; M = lambda k: f"=Models!{c[k]}"
        vals = [co['name'], M('rev'), M('adj'), f"=Models!{c['adj']}/Models!{c['rev']}", M('nd'),
                f"=Models!{c['adj']}*Models!{c['ml']}", f"=Models!{c['adj']}*Models!{c['mm']}", f"=Models!{c['adj']}*Models!{c['mh']}",
                M('dcf'), M('dcfm'), M('irr'), M('moic'), M('mincov'), M('maxm')]
        fmts = [None, '#,##0.0', '#,##0.0', PCT, '#,##0.0;(#,##0.0);-', '#,##0.0', '#,##0.0', '#,##0.0', '#,##0.0', '0.0"x"', PCT, '0.00"x"', '0.0"x"', '0.0"x"']
        for j, (v, fmt) in enumerate(zip(vals, fmts), 1):
            cl = ws.cell(row=r, column=j, value=v); cl.font = font(GREEN if j > 1 else BLACK, bold=j == 1)
            if fmt: cl.number_format = fmt
            cl.border = BOX
        ws.cell(row=r, column=15, value=f'=IF(AND(K{r}>={A["hurdle"]},M{r}>={A["mincov"]}),"Clears hurdle at base price",IF(K{r}>={A["hurdle"]},"Returns OK, debt too heavy","Below hurdle at base price"))').border = BOX
    ws['A10'] = 'How to read this'; ws['A10'].font = font(bold=True, color=TEAL)
    notes = ['EV = enterprise value (price for the whole business, before debt). Low / middle / high use each company\'s price range on the Models sheet, set by its business type as on the website: contractors 5-7x (VEA, Beacon), recurring services 6-8x (Clarus).',
             'DCF EV values five years of cash flow plus an exit value at the middle multiple (held flat, as the thesis requires).',
             'Buyout IRR and MOIC: buy at the middle multiple with senior debt (2.5x EBITDA for contractors, 3.0x for services), repay debt from cash flow, sell after 5 years at the same multiple.',
             'Max entry multiple for hurdle: the highest price (EV / EBITDA) at which the buyout still earns the target IRR. Compare it with the price range.',
             'Illustrative only: projections are simple percentage assumptions, not management forecasts. Public data only; not investment advice.']
    for i, t in enumerate(notes, 11):
        ws.cell(row=i, column=1, value=t).font = font(size=9, color='595959')
    for i, w in enumerate([24, 11, 11, 10, 11, 11, 11, 13, 11, 11, 10, 10, 12, 14, 28], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'B5'
