# Back-test of the weights

Sample: 204 in-band companies with positive EBITDA; 15 were bought in 2023-2026, 7 of them by private equity (direct or through a backed platform).

| Weighting | AUC, all deals | AUC, private equity | 90% range (private equity) |
|---|---|---|---|
| v3.1 (previous: no growth) | 0.51 | 0.57 | 0.37-0.76 |
| v4 (adopted) | 0.57 | 0.67 | 0.46-0.85 |
| growth-heavy (test) | 0.62 | 0.71 | 0.51-0.88 |
| equal (test) | 0.58 | 0.67 | 0.45-0.86 |

| Criterion on its own | AUC, all deals | AUC, private equity |
|---|---|---|
| revenue visibility | 0.36 | 0.36 |
| growth | 0.69 | 0.76 |
| strategy fit | 0.54 | 0.55 |
| size fit | 0.47 | 0.52 |
| margin quality | 0.59 | 0.62 |
| balance sheet | 0.59 | 0.60 |

AUC is the chance a bought company scores above one that was not: 0.5 is chance, 1.0 is perfect.
Caveats: few deals, so the ranges are wide; some accounts are from after the deal; trade buyers buy for their own reasons.
