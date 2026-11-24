# UK Digital Infrastructure Screen

**Live site: https://pe-project-wm.github.io/infra-deal-scanner/**

A thesis-led deal screen for UK digital infrastructure (fibre, wireless, data centres, satellite, network build and maintenance). It turns a written investment thesis into a ranked list of companies using only public Companies House data, then checks for changes every week and explains every move in the ranking.

Built by William Mikollovci with Python, GitHub Actions and Claude.

## What it does

| Step | What happens | Code |
|---|---|---|
| 1. Thesis | A testable claim about the sector, with kill criteria, turned into a criteria file: industry codes, £10–250m turnover, hard stops, scoring weights | `config/criteria_digital_infra.json` |
| 2. Universe | Companies House bulk data: 48,467 companies in the six industry codes → 1,209 active, private, full-accounts filers | notebook (Colab) |
| 3. Accounts | Latest accounts read for every company: digital (iXBRL) tags first, the accounts text as a backup, plus a currency check | `scripts/accounts.py` |
| 4. Clean | Implausible numbers flagged, owners traced through parent companies (PSC register), duplicates merged, off-thesis firms removed with a logged reason | `scripts/clean.py` |
| 5. Score | Five weighted criteria out of 100 (method v3, 24 Nov 2026, after an analyst review): repeat revenue (provisional estimate), fit, EBITDA size, margin level and multi-year stability, balance sheet resilience. Only companies confirmed to trade in the sector are ranked. Accessibility and a confidence rating are shown beside the score, never blended in | `scripts/history.py`, `scripts/score.py` |
| 6. Weekly update | New accounts, owners, charges, directors and status changes; re-rank and explain each move from the points that changed | `scripts/monitor.py`, `scripts/compare.py` |
| 6b. Deal types and correlation (Version 2) | Each company labelled Steady compounder, Fixable dip or High-growth (which kind of fund it suits) and tagged with its main demand driver; the top 10 is tested for hidden concentration on one macro factor (amber at 30%, red at 50%) | `scripts/lenses.py`, `config/demand_drivers.json`, `config/demand_driver_overrides.csv` |
| 6c. Profiles | Why each company is on the list and what to check first (ownership, interest cover, margin swings, estimated figures, growth source) | `scripts/profiles.py`, `config/company_notes.csv` |
| 6d. Price check | Indicative price range from listed peers and deal multiples, plus a sponsor returns check (walk-away multiple for a 20% IRR, exit flat to entry, debt fixed in pounds). Kept separate from the score | `scripts/valuation.py`, `config/valuation.json` |
| 7. Website | Rebuilt from the latest run and published with GitHub Pages | `scripts/site.py` + `scripts/site_template.html` → `docs/` |

The weekly run is `.github/workflows/weekly.yml` (Mondays, 05:30 UTC). Each run commits its results to `data/` and opens an issue with the update.

## Outputs

- `data/outputs/ranking_latest.csv`: the current ranking, with points per criterion
- `data/outputs/rankings/`: a dated copy of every ranking
- `data/outputs/excluded_log.csv`: every company removed, with the reason
- `data/outputs/lenses_latest.csv`: deal type, demand driver and macro factor for every ranked and watchlist company
- `data/outputs/correlation_report.md`: the top-10 correlation test (also added to each weekly issue)
- `data/updates/`: each week's "what changed and why", as Markdown and JSON

## Known limits

- 842 of the 1,209 companies file scanned PDF accounts that are not read yet (OCR is planned).
- The price check is a first pass: ranges come from listed peers and deal averages, and net debt is mostly unknown.
- 41 profitable companies await a check that they really trade in the sector (`data/outputs/sector_check.csv`).
- Repeat revenue is estimated from business type; balance sheet resilience is a proxy, not true debt capacity; figures read from the accounts text are labelled and should be checked against the filing.
- Ownership comes from the register of people with significant control (from April 2016), corrected by web checks and the accounts where noted.

## Data and terms

Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), from Companies House.

Illustrative analysis from public information only. Not investment advice, and not a view on any company's prospects.

© 2026 William Mikollovci. All rights reserved. The code is shared for viewing; please ask before reusing it.
