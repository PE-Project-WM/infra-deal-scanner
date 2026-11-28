# Back-test of the weights

Sample: 206 in-band companies with positive EBITDA; 15 were bought in 2023-2026, 7 of them by private equity (direct or through a backed platform).

| Weighting | AUC, all deals | AUC, private equity | 90% range (private equity) |
|---|---|---|---|
| v3.1 (previous: no growth) | 0.49 | 0.54 | 0.34-0.75 |
| v4 (adopted) | 0.56 | 0.65 | 0.43-0.84 |
| growth-heavy (test) | 0.60 | 0.68 | 0.46-0.88 |
| equal (test) | 0.57 | 0.65 | 0.43-0.85 |

| Criterion on its own | AUC, all deals | AUC, private equity |
|---|---|---|
| revenue visibility | 0.36 | 0.37 |
| growth | 0.68 | 0.76 |
| strategy fit | 0.53 | 0.54 |
| size fit | 0.47 | 0.52 |
| margin quality | 0.58 | 0.62 |
| balance sheet | 0.58 | 0.58 |

## Infrastructure test (method v4.1): extra inputs, not adopted

Labels from rules only (business type plus contract terms found in the accounts text), so every company is treated alike.

| Test | AUC, all deals | AUC, private equity | 90% range (private equity) |
|---|---|---|---|
| revenue_type on its own | 0.40 | 0.44 | 0.35-0.57 |
| contract_length on its own | 0.53 | 0.49 | 0.33-0.64 |
| v4 + revenue type (10 pts) | 0.54 | 0.63 | 0.41-0.83 |
| v4 + contract length (10 pts) | 0.57 | 0.64 | 0.42-0.84 |
| v4 + both (10 pts each) | 0.53 | 0.62 | 0.41-0.81 |

Best combination: v4 + contract length (10 pts) at 0.64 against v4 at 0.65. It does not clearly beat v4, so no weight change is proposed. With 7 private equity deals the 90% ranges overlap heavily; keep the labels as information only.

AUC is the chance a bought company scores above one that was not: 0.5 is chance, 1.0 is perfect.
Caveats: few deals, so the ranges are wide; some accounts are from after the deal; trade buyers buy for their own reasons.
