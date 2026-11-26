"""Workbook part 1: styles, Shortlist and Scorecard sheets."""
import json, pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment

import os
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
F = 'Arial'
BLUE, BLACK, GREEN = '0000FF', '000000', '008000'
NAVY, TEAL, GREY = '13203A', '0E7C74', 'F2F2F2'
YELLOW = 'FFFF00'
thin = Side(style='thin', color='D9D9D9')
BOX = Border(bottom=thin)

def font(color=BLACK, bold=False, size=10, italic=False):
    return Font(name=F, color=color, bold=bold, size=size, italic=italic)

def header_row(ws, row, labels, start_col=1):
    for i, lab in enumerate(labels):
        c = ws.cell(row=row, column=start_col + i, value=lab)
        c.font = Font(name=F, bold=True, color='FFFFFF', size=10)
        c.fill = PatternFill('solid', fgColor=NAVY)
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[row].height = 30

def title(ws, text, sub):
    ws['A1'] = text; ws['A1'].font = Font(name=F, bold=True, size=14, color=NAVY)
    ws['A2'] = sub; ws['A2'].font = font(color='595959', italic=True, size=9)

def load():
    R = pd.read_csv(f'{REPO}/data/outputs/ranking_latest.csv', dtype={'CompanyNumber': str})
    C = json.load(open(f'{REPO}/config/thesis/' + os.environ.get('SECTOR', 'digital') + '.json'))
    return R, C

GBP_M = '£#,##0.0,,"m";(£#,##0.0,,"m");-'
PCT = '0.0%;(0.0%);-'

def build_scorecard(wb, R, C):
    """All scored companies: points per criterion as inputs, total as formula, weights at the top."""
    ws = wb.create_sheet('Scorecard')
    title(ws, 'Scorecard: points per criterion', 'Each criterion scored 0-1 by scripts/score.py, then multiplied by its weight. Change a weight (yellow) and the totals and ranks update.')
    W = C['scoring_weights']; keys = list(W)
    ws['A4'] = 'Weights (out of 100)'; ws['A4'].font = font(bold=True)
    for i, k in enumerate(keys):
        col = 4 + i
        ws.cell(row=4, column=col, value=k.replace('_', ' ').capitalize()).font = font(bold=True, size=9)
        ws.cell(row=4, column=col).alignment = Alignment(wrap_text=True, horizontal='center')
        c = ws.cell(row=5, column=col, value=W[k]); c.font = font(BLUE, bold=True); c.fill = PatternFill('solid', fgColor=YELLOW)
        c.alignment = Alignment(horizontal='center')
        c.comment = Comment(f'Source: config/thesis/digital.json. {C["scoring_notes"][k]}', 'Screener')
    ws.cell(row=5, column=4 + len(keys), value='=SUM(D5:I5)').font = font(bold=True)
    ws.cell(row=4, column=4 + len(keys), value='Total').font = font(bold=True, size=9)
    ws['A5'] = 'Edit the yellow cells to re-weight'; ws['A5'].font = font(color='595959', italic=True, size=9)
    hdr = ['Company', 'Company no.', 'Fit'] + [f'{k.replace("_", " ").capitalize()} (0-1)' for k in keys] + ['Score /100', 'Rank', 'Accessibility', 'Revenue visibility basis']
    header_row(ws, 7, hdr)
    first = 8
    for i, r in R.reset_index(drop=True).iterrows():
        row = first + i
        ws.cell(row=row, column=1, value=r['CompanyName'].title())
        ws.cell(row=row, column=2, value=r['CompanyNumber'])
        ws.cell(row=row, column=3, value=r['relevance'])
        for j, k in enumerate(keys):
            c = ws.cell(row=row, column=4 + j, value=round(float(r[f'pts_{k}']) / W[k], 3) if W[k] else 0)
            c.font = font(BLUE); c.number_format = '0.00'
        ws.cell(row=row, column=10, value=f'=SUMPRODUCT(D{row}:I{row},$D$5:$I$5)').number_format = '0.0'
        ws.cell(row=row, column=11, value=f'=RANK(J{row},$J${first}:$J${first + len(R) - 1})')
        ws.cell(row=row, column=12, value=r['accessibility'])
        ws.cell(row=row, column=13, value=r['revenue_visibility_basis'])
        for col in range(1, 14):
            ws.cell(row=row, column=col).border = BOX
            if ws.cell(row=row, column=col).font.color is None or ws.cell(row=row, column=col).font.color.rgb in (None, 'FF000000'):
                ws.cell(row=row, column=col).font = font(BLUE if 4 <= col <= 9 else BLACK)
    last = first + len(R) - 1
    widths = [34, 11, 10, 11, 11, 11, 11, 11, 11, 10, 7, 46, 30]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'B8'
    return first, last

def build_shortlist(wb, R, first, last):
    """Top 20: pulled live from the Scorecard by rank, with key facts."""
    ws = wb.create_sheet('Shortlist', 0)
    title(ws, 'Top 20 shortlist: UK digital infrastructure', 'Ranked by the Scorecard (changes there flow through). Fit and accessibility are shown side by side and never blended. Public data only; illustrative.')
    hdr = ['Rank', 'Company', 'Score /100', 'Fit', 'Segment', 'Turnover', 'Turnover growth', 'EBITDA', 'EBITDA margin', 'EBITDA basis', 'Figures source', 'Accessibility', 'Owner chain', 'Town']
    header_row(ws, 4, hdr)
    facts = R.set_index('CompanyNumber')
    # facts block (static data) on a hidden helper sheet for lookups
    hs = wb.create_sheet('Data')
    cols = ['CompanyNumber', 'CompanyName', 'segment', 'turnover', 'turnover_growth', 'ebitda', 'ebitda_margin', 'ebitda_basis', 'figures_source', 'owner_chain', 'RegAddress.PostTown']
    for j, cname in enumerate(cols, 1):
        hs.cell(row=1, column=j, value=cname).font = font(bold=True)
    for i, (_, r) in enumerate(R.iterrows(), 2):
        for j, cname in enumerate(cols, 1):
            v = r[cname]
            hs.cell(row=i, column=j, value=None if pd.isna(v) else (v.title() if cname in ('CompanyName',) else v)).font = font(BLUE)
    hs['M1'] = 'Source: data/outputs/ranking_latest.csv (Companies House filings, parsed by scripts 03-05)'; hs['M1'].font = font(italic=True, size=9)
    n = len(R) + 1
    for k in range(1, 21):
        row = 4 + k
        ws.cell(row=row, column=1, value=k)
        # find company number with rank k on Scorecard
        m = f'MATCH({k},Scorecard!$K${first}:$K${last},0)'
        ws.cell(row=row, column=2, value=f'=INDEX(Scorecard!$A${first}:$A${last},{m})').font = font(GREEN)
        ws.cell(row=row, column=3, value=f'=INDEX(Scorecard!$J${first}:$J${last},{m})').font = font(GREEN)
        ws.cell(row=row, column=3).number_format = '0.0'
        ws.cell(row=row, column=4, value=f'=INDEX(Scorecard!$C${first}:$C${last},{m})').font = font(GREEN)
        key = f'INDEX(Scorecard!$B${first}:$B${last},{m})'
        lk = lambda col: f'=INDEX(Data!${col}$2:${col}${n},MATCH({key},Data!$A$2:$A${n},0))'
        spec = [(5, 'C', None), (6, 'D', GBP_M), (7, 'E', PCT), (8, 'F', GBP_M), (9, 'G', PCT), (10, 'H', None), (11, 'I', None)]
        for col, dcol, fmt in spec:
            c = ws.cell(row=row, column=col, value=lk(dcol)); c.font = font(GREEN)
            if fmt: c.number_format = fmt
        ws.cell(row=row, column=12, value=f'=INDEX(Scorecard!$L${first}:$L${last},{m})').font = font(GREEN)
        ws.cell(row=row, column=13, value=lk('J')).font = font(GREEN)
        ws.cell(row=row, column=14, value=lk('K')).font = font(GREEN)
        for col in range(1, 15):
            ws.cell(row=row, column=col).border = BOX
            ws.cell(row=row, column=col).alignment = Alignment(vertical='top', wrap_text=col in (2, 10, 12, 13))
    for i, w in enumerate([6, 32, 9, 10, 26, 11, 10, 11, 10, 22, 16, 34, 40, 14], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws['A26'] = 'Note: turnover and EBITDA are shown in £m. "FROM TEXT, check" means the figure was read from the accounts text, not a digital tag. Revenue visibility and debt capacity points are estimates (see Notes).'
    ws['A26'].font = font(italic=True, size=9, color='595959')
    ws.freeze_panes = 'C5'
    hs.sheet_state = 'hidden'
