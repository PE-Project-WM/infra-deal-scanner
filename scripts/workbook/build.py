import sys
from part2 import *

def build_notes(wb):
    ws = wb.create_sheet('Notes')
    title(ws, 'Notes: method, sources and known limits', 'Read this before relying on any number in the workbook.')
    blocks = [
        ('What this is', [
            'A screen of UK digital-infrastructure companies built from public Companies House data, ranked against a written investment thesis (UK Digital Infrastructure, Nov 2026).',
            'Funnel: 48,467 companies with the six industry codes > 1,209 active, private, full accounts, 3+ years > 211 inside £10-250m turnover > 105 after cleaning > 74 scored.',
            'Built by William Mikollovci with Claude, Python and GitHub Actions. Skills used: thesis-development, market-map-and-sourcing, deal-screening, dcf-model, irr-moic-calculator, debt-schedule.']),
        ('How the score works', [
            'Six criteria scored 0-1 and weighted (Scorecard row 5): revenue visibility 25, strategy fit 20, size fit 15, margin quality 15, data completeness 15, debt capacity 10.',
            'Revenue visibility is an ESTIMATE from business type (accounts do not split recurring revenue). Debt capacity is a PROXY from net assets, cash and margin.',
            'Accessibility (who owns it and whether it could be sold) is shown separately and never blended into the score, so an available company cannot outrank a better fit.']),
        ('Valuation method', [
            'Price range uses sector benchmarks, not company-specific comparables: 6.5x (listed telecom services, Damodaran Jan 2026), 8.0x base, 9.0x walk-away (UK TMT deals under £100m at 8.9x LTM to Sep 2026, MarktoMarket via Alinea).',
            'DCF: five-year projection from simple growth and margin assumptions, discounted at the WACC on the Assumptions sheet, with an exit value at the base multiple held flat.',
            'Buyout check: buy at the base multiple with 3.5x EBITDA of senior debt, sweep spare cash to repay debt, exit after five years at the same multiple. IRR and MOIC are before management equity and interim dividends.']),
        ('Red flags found in the filings', [
            'VEA Group: subsidiary of VEA Group Holdings (Pty), South Africa; a deal would be a carve-out. Margin rose from 16% to 31% in one year; a fibre build and maintenance contractor diversifying into facilities management and highways.',
            'The Networking People: bought by YFM Equity Partners in 2025, so an early sale is unlikely. Paid £1.27m dividends in FY2026.',
            'Satcom Global: reports in US dollars (converted at $1.26/£, assumption); prior year restated for sales credit notes; latest accounts are for June 2024; bank borrowings of about $21m and large intra-group balances.',
            'Clarus Networks: FY2025 operating profit includes £1.22m of other operating income (2024: £0.04m), removed as one-off.',
            'MAP Group: employee-owned since 2023 (EOT), so rarely for sale; net assets fell from £28.3m to £10.6m as the EOT purchase was funded.']),
        ('Known limits', [
            '842 of 1,209 companies (70%) file scanned PDF accounts that were not read; the screen is therefore biased to companies that file digitally.',
            'Figures marked "FROM TEXT, check" were read from the accounts text, not digital tags. The pipeline assumes pounds sterling; Satcom Global was found to report in US dollars only by reading its accounts.',
            'Ownership comes from the register of people with significant control (from April 2016), corrected by web checks and the accounts where noted. "Owner since 2016" usually means 2016 or earlier.',
            'Illustrative analysis from public information only. Not investment advice.']),
        ('Sources', [
            'Companies House: bulk company data (snapshot 1 Nov 2026), filing history and document APIs, PSC register.',
            'Alinea, Seasonal M&A Review Autumn 2026 (MarktoMarket data): https://www.alineacf.co.uk/the-library/autumn2026',
            'Hardman & Co, Private company valuations in 2026 (MarktoMarket): https://hardmanandco.com/saaspocalypse-private-company-valuations-in-2026/',
            'Damodaran telecom services multiple via mergersandacquisitions.net: https://mergersandacquisitions.net/insights/technology-media-telecom-mergers-and-acquisitions',
            'Code and run history: github.com/PE-Project-WM/infra-deal-scanner (private).']),
    ]
    r = 4
    for head, lines in blocks:
        ws.cell(row=r, column=1, value=head).font = font(bold=True, color=TEAL, size=11); r += 1
        for t in lines:
            c = ws.cell(row=r, column=1, value=t); c.font = font(); c.alignment = Alignment(wrap_text=True, vertical='top')
            ws.row_dimensions[r].height = 28 if len(t) > 140 else 15
            r += 1
        r += 1
    ws.column_dimensions['A'].width = 160
    ws['A1'].alignment = Alignment(wrap_text=False)

R, C = load()
wb = Workbook(); wb.remove(wb.active)
first, last = build_scorecard(wb, R, C)
build_shortlist(wb, R, first, last)
build_assumptions(wb)
out = build_models(wb)
build_valuation(wb, out)
build_notes(wb)
order = ['Shortlist', 'Valuation', 'Scorecard', 'Assumptions', 'Models', 'Notes', 'Data']
wb._sheets = [wb[n] for n in order]
for ws in wb.worksheets:
    ws.sheet_view.showGridLines = False
wb.active = 0
path = sys.argv[1]
wb.save(path); print('saved', path)
