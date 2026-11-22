# Infra Deal Scanner

A screening tool that turns a private equity fund's investment thesis into a ranked list of UK companies, using only public data (Companies House).

**Current sub-sector:** UK digital infrastructure (fibre, wireless, data centres, satellite, network build and maintenance), £10m–£250m turnover, privately owned.

## How it works

| Step | What it does | Where |
|---|---|---|
| 01 Criteria | Thesis turned into a criteria file: industry codes, size band, hard stops, scoring weights | `config/criteria_digital_infra.json` |
| 02 Universe | Companies House bulk file filtered: 48,467 → 1,209 companies | Colab notebook |
| 03 Financials | Latest accounts read for every company (tagged iXBRL, with a text fallback) | Colab notebook → `data/inputs/financials_all.csv` |
| 04 Clean | Flags implausible numbers, looks up ownership (PSC register), merges duplicates, applies the thesis relevance review | `scripts/clean.py` |
| 05 Score | Ranks candidates on the criteria weights (next) | — |

Every exclusion is logged with a reason in `data/outputs/excluded_log.csv`.

## Running it

GitHub Actions runs each step on push or from the **Actions** tab. The Companies House API key is stored as the repository secret `CH_API_KEY`.

*Illustrative analysis from public information only. Not investment advice.*
