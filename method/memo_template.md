# One-page screening memo: template (method v4.1)

Use this for any company taken from the ranking to a first look. It is a screening memo, not an investment committee paper. Public information only; say so on the page.

Rules for every memo:
- Every number has a source (filing and note, or the pipeline file it came from) and a confidence (section 8 of METHOD.md).
- No causal claims the accounts do not make. Write "sales rose 56% and margin fell 4 points", not "margin fell because of growth", unless the accounts say so.
- Never name directors or owners who are individuals. Name a corporate owner or fund only where the register or a public announcement shows it.
- Recurring-services and contractor targets are **hybrid infrastructure**. Say so in the first section and state the gaps openly: short contracts, few physical assets, merchant revenue. Do not present them as core infrastructure.

---

## 1. Summary (3–4 lines)
Company, what it does in one sentence, rank and score, business type, infrastructure tier. The recommendation (pass to diligence / ask one question first / monitor / pass) and the two reasons for it.

## 2. Why it ranks
The criteria where it scores well, from the profile ("Why it is on the list"), with the figures behind them.

## 3. Infrastructure characteristics
From `config/infra_test.csv`. For each line, give the label, the evidence and its basis (stated in the accounts / described / public information / inferred).

| | Label | Evidence | Basis |
|---|---|---|---|
| Revenue type | contracted / regulated / merchant / mixed | | |
| Typical contract length | under 1 year / 1–3 / 3–10 / 10+ years / unknown | | |
| Inflation linkage | yes / partial / no / unknown | | |
| Infrastructure tier | core / core-plus / value-add / hybrid | | |
| Barriers to entry | What would stop a competitor copying it (owned sites, consents, exclusive networks, switching costs, accreditation). "Low" is an acceptable answer | | |
| Essential service | What fails for its customers if it stops, and who those customers are | | |

For a hybrid company, close the section with one sentence on what it lacks against core infrastructure, for example: "Hybrid infrastructure: repeat revenue from maintaining networks it does not own, on contracts renewed every one to three years, with few physical assets."

## 4. Financials
Three years of sales, EBITDA (with the EBITDA rules applied, section 6 of METHOD.md) and margin; cash, net assets, net debt; cash conversion. Flag any figure read by OCR or corrected by hand.

## 5. Price check
Price range for its business type, net debt, the range for the shares, and the buyer-returns check (IRR and multiple at the type's hurdle). State that these are benchmarks, not a valuation.

## 6. Risks
One or two lines under each heading. Write "none found in public information" rather than leaving a heading out.

| Heading | What to cover |
|---|---|
| Political | Government funding or policy the business depends on (for example broadband subsidy programmes, defence budgets) |
| Regulatory | Ofcom, Ofgem or other rules that set prices, terms or licences; changes under way |
| Technological | Whether the asset or service could be replaced (satellite against fibre, cloud against on-site systems) |
| Climate | Physical exposure of sites and networks; transition costs |
| Economic | Customer spending cycles, inflation in costs against prices it can pass on, interest rates on its debt |
| Governance | Ownership structure, group carve-out, related-party balances, filing quality |
| Revenue uncertainty | Contract length, renewal and churn, customer concentration, share of project work |

## 7. What to check first
From the profile's "Check first" list and `config/company_notes.csv`, each marked as something to price, fix or walk away on.

## 8. Sources and limits
Filings used (with dates), pipeline files, any public announcements. One line on what public information cannot show (renewal rates, contract terms, management quality).
