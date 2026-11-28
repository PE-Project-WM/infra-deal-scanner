# Northing method (v4.1, 28 November 2026)

This is the general method. It applies to every sector. Each sector adds an appendix (for digital infrastructure: [digital.md](digital.md)) and one settings file (`config/thesis/<sector>.json`). Adding solar, water and waste, transport and logistics or social infrastructure means writing those two files, not changing the code.

The ranking shows where a mid-market buyer should look first. It is not a valuation and not investment advice.

## 1. Order of work

| Step | Script | What it does |
|---|---|---|
| Universe | `accounts.py`, notebooks, `universe_extend.py` | Every active UK private company under the sector's industry codes, with sales in the band (default £10–250m); plus neighbouring codes where real targets register (IT services, electrical and civil installation), with an automatic rulebook call |
| Monthly reading | `history_fetch.py` (deep_dive.yml, 1st of each month) | Reads the filings of companies that are new or have filed again, so three years stay read |
| Read accounts | `ocr_fetch.py`, `ocr_parse.py`, `history_fetch.py`, `history_parse.py` | Latest accounts, then the last three filings of every company going forward, tagged or scanned |
| Clean | `clean.py` | Number checks, ownership from the register, group rule, sector calls, exclusions |
| History | `history.py` | Years of sales and profit per company, each year checked against the next filing |
| EBITDA rules | `normalise.py` | One set of adjustments for every company (section 6) |
| Score | `score.py` | Business type, six criteria, confidence, the ranked list and the list of network owners still building |
| Price and size | `valuation.py`, `size_check.py` | Price range and buyer returns by business type |
| Infrastructure test | `infra_test.py` | Four investor labels per ranked company, shown but not scored (section 10a) |
| Data-centre check | `dc_adjacent.py` | Companies whose accounts link them to data centres, in or out of the ranking (section 10b) |
| Back-test | `backtest.py` | Checks the weights against real deals (section 9); runs every week |

## 2. Rulebook: is a company in the sector?

Evidence, in order of trust: the principal activity in its filed accounts; its own description or press coverage; its name and industry code. A call says which it used: "rulebook call from the principal activity in the filed accounts", "from public knowledge: check", or "web-checked".

| Call | Rule |
|---|---|
| IN | Owns, operates, builds or maintains the sector's infrastructure, or sells services carried on it, as its main activity (more than half of sales) |
| ADJACENT | The infrastructure is a material part of the business (about a quarter to a half), or the company resells services carried on other firms' infrastructure, or works across this sector and others |
| OUT | Software, data, consultancy, outsourcing, contact centres, consumer products, equipment makers that do not run networks, or the infrastructure is outside the UK |
| UNSURE | The trading business cannot be identified from public information (for example, accounts overdue, virtual office, no description). Not ranked |

An industry code alone never ranks a company. A company that belongs to another sector is marked OUT with "candidate for the X sector", so it is picked up when that sector is added.

## 3. Rulebook: who owns it, and can it be bought?

- Ownership comes from the Companies House register of people with significant control, followed up to four levels. Web-checked facts (recent deals not yet on the register) override it, in `config/ownership_overrides.csv`, with a source.
- Excluded, because the company cannot be bought on its own: foreign-owned subsidiaries; parts of a much larger group (including listed groups and subsidiaries of a merged group); listed companies.
- Kept, with an accessibility label shown beside the score and never added to it: founder or family-owned (High), sponsor-owned with a sale window (Medium), owned via a UK holding company (Medium), overseas founder group (Low-Medium), sponsor bought in the last two years (Low), employee-owned (Low).

## 4. Rulebook: group accounts (count each business once)

The ranked company is the one whose accounts cover the whole business a buyer would buy.

1. A hand-checked entry in `config/group_structure.csv` wins: either "group" (count the company under its group company) or "larger group" (part of a group that is not in the universe or is far bigger, so excluded).
2. Otherwise, if a UK parent on the register is itself in the universe, the parent is ranked and the subsidiary dropped.
3. Otherwise, two companies with the same first name word and turnover within 2% are one business: the holding or group company is kept.
4. A single-contract project company (for example a PFI company) is ranked as itself, with the business type "project company" (section 5).

## 5. Business types

Every company gets one type: from `config/business_type.csv` if listed there, else the default for its sub-sector in the thesis file, else "recurring services". The type sets what counts as good:

| Type | What it is | EBITDA sweet spot | Full marks for margin | Comfortable net debt | Price range | Buyer's return target |
|---|---|---|---|---|---|---|
| Network owner | Owns the network or site and earns from access to it | £3–20m | 50% | 5x EBITDA | 12–18x | 12% (infrastructure funds) |
| Recurring services | Services that repeat under contract or subscription | £2–15m | 30% | 1x | 6–8x | 20% (private equity) |
| Contractor | Builds and maintains networks for their owners, project by project | £2–15m | 15% | 1x | 5–7x | 20% |
| Project company | Exists for one long contract and ends with it | £2–15m | 50% | 5x | Cash left in the contract at 8–10% | n/a |

Services firms and contractors with EBITDA under £3m take half a turn off their price range.

**Network owners still building.** A network owner with EBITDA at or below zero is not dropped. It goes on a separate list (`building_latest.csv`) with sales, growth, losses and funding, because buyers price it on the network (premises, sites, MW), not on EBITDA. Other loss-making companies stay on the loss-making watchlist.

## 6. EBITDA rules (the same for every company)

Reported EBITDA is operating profit plus depreciation and amortisation (D&A) from the latest accounts. Then, in order:

| Rule | What happens |
|---|---|
| R0 Missing D&A | Where EBITDA was only operating profit, D&A read from the same accounts (text, or the fixed-asset notes of tagged accounts) is added. A correction, not an adjustment |
| R1 R&D tax credits | R&D expenditure credits booked above operating profit are taken out (a tax relief, not trading profit). Credits in the tax charge are not touched |
| R2 IFRS 16 | For accounts under IFRS, depreciation of leased assets is taken off, so every company is on the UK GAAP basis where rent is a cost |
| R3 One-year margin jump | For services firms and contractors, where the latest margin is more than 10 points above the average of earlier years (and those years were profitable), EBITDA is priced on the two-year average until a second year shows it holds |
| R4 Exceptional items | Added back (costs) or taken off (gains) only once checked against the filing (`config/ebitda_adjustments.csv`). Found but unchecked items are listed, not applied: an add-back needs evidence, a deduction does not |
| R5 Directors' pay | Not adjusted. What owners pay themselves is a cost; any add-back is for a buyer to negotiate |

## 7. Score (100 points)

| Criterion | Points | How it is scored (0–1, then times the points) |
|---|---|---|
| Repeat revenue | 20 | From the accounts where read (`config/revenue_mix.csv`, section 7a); otherwise estimated from the business description, then the type default |
| Sales growth | 15 | Yearly average over three or more years; one year where only two are read. Scores 0 at −10% a year, 0.4 at zero, 1 at +15% or more. Sales that more than quadruple in a year are a change of perimeter, scored as unknown (0.4). Project companies: years left on the contract over 15 |
| Strategy fit | 15 | IN 1.0, ADJACENT 0.6 |
| Size | 15 | EBITDA against the type's sweet spot: 0.2 below £1m, rising to 1 at the sweet spot, fading to 0.6 above it |
| Margin quality | 20 | 70% margin level against the type's full-marks margin; 30% stability: within 3 points across three or more years is stable, 18 points or more is unstable (neutral when fewer years are read) |
| Balance sheet | 15 | Net assets (0.4), cash against sales (0.3), margin headroom (0.3); less for interest cover under 3x and for net debt above the type's comfortable level |

**7a. Reading repeat revenue.** From the latest accounts: 0.9 where 85% or more of sales is stated as recurring; 0.8 for 70–85% (or described as mostly contracted or billed in advance); 0.7 for 50–70% or a mix described; 0.5 for mostly projects with long-term frameworks or maintenance; 0.35–0.4 for project and installation work. Each entry says whether the accounts give a split ("split") or describe the mix ("described").

## 8. Confidence (shown beside the score, never added to it)

Points start from where the figures came from, then move:

| Item | Points |
|---|---|
| Figures tagged in digital accounts | 1.00 |
| Figures checked against the filing by eye, or corrected by hand | 0.90 |
| Figures confirmed by the next filing (the same year read twice, within 2%) | 0.85 |
| Read from the accounts text, not yet checked | 0.60 |
| Read by OCR from a scan, not yet checked | 0.50 |
| Three or more years read | +0.05 |
| Only one year read | −0.15 |
| EBITDA estimated (no D&A found) | −0.20 |
| Cash or net assets missing (each) | −0.05 |
| Repeat revenue estimated rather than read | −0.05 |
| Only adjacent to the thesis | −0.10 |

High is 0.85 or more, Medium 0.60 or more, otherwise Low. Figures with a failed number check are Low until the flag is checked; a flag checked against the filing and found real (`config/flag_checks.csv`) no longer counts.

## 9. Back-test

`backtest.py` scores every in-band company with positive EBITDA, whatever its owner, and asks how often a company bought in the last three years (`config/deal_history.csv`, with buyer and source) scores above one that was not (AUC: 0.5 is chance, 1.0 is perfect). Weights are only changed where the evidence is clear, because the deal sample is small. Results for each sector are in its appendix.

## 10. Sector measures

Measures an investor prices in a sector (homes passed, take-up, sites, MW, order book) are shown but not scored. A measure counts in the score only once it is collected for at least 80% of the ranked companies of that business type in the sector, so no company is marked down for a figure nobody collected.

## 10a. Infrastructure test (shown, not scored)

Infrastructure investors ask whether a company is "real" infrastructure: how certain its revenue is, how long its contracts run, whether prices follow inflation, how hard it is to copy and whether the service is essential. The score measures financial quality, so these labels sit beside it (`config/infra_test.csv`, `data/outputs/infra_test_latest.csv`). They are on the company profiles, in the workbook (Infra test sheet) and in the memo template.

| Label | Values | Meaning |
|---|---|---|
| Revenue type (after EDHEC TICCS business-risk models) | contracted / regulated / merchant / mixed | Contracted: most revenue fixed by contracts of 3+ years with committed payments (lease, availability, PFI, bulk agreements). Regulated: price set by a regulator. Merchant: revenue depends on orders, usage or renewals within 3 years, including short subscriptions and framework work. Mixed: a material part (about a quarter or more) of two of these |
| Typical contract length | under 1 year / 1–3 years / 3–10 years / 10+ years / unknown | The term customers sign for, not how long they stay |
| Inflation linkage | yes / partial / no / unknown | Yes: indexed contracts or regulated prices. Partial: some indexation or fixed annual rises |
| Infra tier | core / core-plus / value-add / hybrid | Default from business type: project company core, network owner core-plus, recurring services and contractor hybrid. Changed by hand only with a written reason |

Each label carries its basis and points, as in section 8: stated in the accounts 0.9, described in the accounts 0.6, public information 0.6, inferred from the business model 0.4. The company's infrastructure-test confidence is the average over revenue type, contract length and inflation linkage (High 0.85+, Medium 0.6+, otherwise Low). Contract terms and indexation are rarely in UK accounts, so most labels start Low: they rise as contract lists, terms and conditions and management answers come in.

Hybrid infrastructure: recurring-services and contractor companies earn repeat revenue from infrastructure without owning much of it. Memos frame them as hybrid and state the gaps openly (short contracts, few physical assets, merchant revenue).

A label joins the score only if the back-test shows it clearly improves the ranking (section 9). The back-test uses labels from rules alone (business type plus contract terms found in the accounts text) so that bought and not-bought companies are labelled the same way.

## 10b. Data-centre adjacent check

Each week `dc_adjacent.py` reads every set of accounts the pipeline holds and lists the companies linked to data centres, by role (operator, connectivity, power, cooling, fit-out, or a user of data-centre space), and whether each is ranked or why not. Hand checks in `config/dc_adjacent.csv` set the role and a note. Companies coded only as electrical installation, cooling or building M&E are outside the sector's codes; the sector appendix says which of those codes the universe extension covers.

## 11. What stays a limit

- Public information only; accounts can be up to two years old.
- Renewal and churn rates are rarely published, so repeat revenue is read as a share of sales, not as retention.
- Net debt is checked by hand only for the leading companies; read automatically for the rest, so it can only mark a company down.
- Price ranges come from listed peers and deal averages, not deals in each niche. Deal size is always an estimate.
- The universe follows industry codes, so companies registered under other codes (for example IT services) are missed.

## 12. Adding a sector (checklist)

1. Write the thesis in `config/thesis/<sector>.json`: industry codes, size band, weights, business types and their defaults per sub-sector, visibility rules, price ranges and return targets.
2. Add the sub-sectors to the sector map, with measures to collect.
3. Run the universe, accounts reading and three-year reading with `SECTOR=<sector>`.
4. Make sector calls with the rulebook (section 2); place companies and set business types.
5. List the deals of the last three years in the sector and run the back-test before trusting the weights.
6. Write the sector appendix in `method/<sector>.md`.
7. Fill `config/infra_test.csv` for the ranked companies (section 10a) and the memo template's infrastructure section for any memo.
