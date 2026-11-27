# Appendix: UK digital infrastructure (method v4, 26 November 2026)

Settings: `config/thesis/digital.json`. General method: [METHOD.md](METHOD.md).

## Universe

- Industry codes: 61100 fibre and wired networks, 61200 wireless and towers, 61300 satellite, 61900 other telecoms, 63110 data centres and hosting, 42220 network build.
- 48,467 register records, 1,209 active private companies filing full accounts and three or more years old, 620 with sales of £10–250m.
- After ownership, group and sector checks (updated 27 Nov 2026): 83 are ranked, 8 network owners are still building, and 1 is not ranked because its trading business cannot be confirmed (Egnaro: £22m of UK turnover described only as "wireless telecommunications activities").

## Sub-sectors and default business types

| Sub-sector | Default type |
|---|---|
| Fibre networks, towers and small cells, data centres, subsea | Network owner |
| Network build and maintenance | Contractor |
| Wireless, satellite, critical communications, business connectivity | Recurring services |

Exceptions are listed in `config/business_type.csv`: Wifinity is a network owner (it owns the wifi networks it sells), Alert Communications is a project company (one MoD PFI contract to 2033), and GPU cloud and hosting firms registered as data centres are recurring services. The ranked list has 52 recurring services firms, 22 contractors, 7 network owners and 1 project company.

## Price ranges and return targets

| Type | Range | Evidence |
|---|---|---|
| Recurring services | 6–8x EBITDA | Gamma near 6x before its bid, taken private by Epiris at about 7.6x; UK private deals under £250m median about 6.2x |
| Contractor | 5–7x | SPIE trades near 8x; smaller and project-based, so lower |
| Network owner | 12–18x, 12% return target | Dutch towers sold at 16.2x 2025 EBITDA; TeleTower at 16x; infrastructure funds target about 10–15% |
| Project company | Cash left in the contract, after tax, at 8–10% | Alert: about £19–20m |

## Three years of accounts

The last three filings of every company going forward were read on 26 November 2026 (642 filings: 239 digital, 403 scanned and read by text recognition where needed). Of the 82 ranked companies, 73 now have three or four years of sales and profit, and 9 have two (their earlier accounts had no profit and loss account). 181 companies have at least one year read in two filings that agree within 2%.

## EBITDA rules applied (ranked companies)

D&A added where it had been missing (R0) for 5; R&D expenditure credits taken out (R1) for 3 plus Clarus by hand (£1.22m); IFRS 16 lease depreciation taken off (R2) for 3; margin jumps priced on the two-year average (R3) for VEA (31% to 23%) and Telecommunications Management (27% to 20%); Wifinity's £0.85m exceptional costs added back after a check against the filing.

## Repeat revenue

Read from the accounts for 64 of the 82 ranked companies (recurring shares where given, e.g. Redwood 86%, Redcentric 88.5%, Opus 90%, Onecom about 86%, Maintel 74%, Natilik 70%, WIG 80%; otherwise the mix described). The biggest corrections: Nano Fibre UK down from 0.9 to 0.35 (all installation and civils work) and WIG up from 0.6 to 0.8.

## Back-test (data/outputs/backtest.md)

15 companies in the sample were bought in 2023–2026 (7 by private equity or a private-equity-backed platform: Wifinity, TNP, Southern Communications Group, North, OCU Nettworx, Glenelly, York Telecom).

| Weighting | AUC, all deals | AUC, private equity |
|---|---|---|
| v3.1 (no growth) | 0.51 | 0.57 |
| v4 (adopted) | 0.57 | 0.67 |

Sales growth on its own separates bought companies best (0.76 for private equity deals). Estimated repeat revenue did not (0.36): bought companies were often contractors and add-ons. Its weight went from 25 to 20 rather than to zero, because the case for infrastructure rests on it and most of the scores are now read rather than estimated; this is the first thing to re-test when more deals are logged. A growth-heavy weighting scored slightly higher (0.71) but within the margin of error of seven deals, so it was not adopted.

## Confidence

| | Before (v3.1, 25 Nov) | After (v4, 26 Nov) |
|---|---|---|
| High | 1 | 55 |
| Medium | 13 | 27 |
| Low | 68 | 0 |

What moved it: three years read for almost every company; figures checked against the filing now count for nearly as much as tagged figures (they are checked line by line); revenue mix read from the accounts for 64 companies; cash, net assets and D&A filled from the same accounts where the first reader missed them; three number flags checked and found real. What keeps 27 at Medium: 58 ranked companies are only adjacent to the thesis, and 9 have only two years of accounts.

## Checks closed on 27 November 2026

- 110 sector calls made from public knowledge were checked against the principal activity in the companies' filed accounts. Ten changed: Purdicom, TXO Systems, MDA Satconn, Radio Design and Resilient to OUT (equipment or software); (AQ) and Transaction Network Services to IN (TNS is US-owned, so excluded); NexGen Cloud, Brightsolid and Electricityworx to ADJACENT. Connexin sold its fibre network, so it is now a services firm and off the still-building list. 145 calls on companies that do not reach the ranking (mostly obvious OUTs such as software firms) still rest on public knowledge.
- Ridown Capital does not own Onecom: it sold its web-hosting subsidiary to Onecom, which belongs to Solo Topco (LDC). No double count.
- Net debt checked by hand: Community Fibre £760m (term loan and accordion drawn £765m, cash £7m); Saint Topco £472.6m as reported for March 2025 (before the Providence deal); Glide owes £109m to its parent group (the acquisition debt sits above it).
- Trust Group Ventures (phone-system distribution) and SOLiD Telecommunications (hardware sales) are OUT. Egnaro stays unconfirmed.

## Open checks

- Companies registered under IT or engineering codes: being added (method v4.1, universe extension).
