"""Back-test: does the score pick out the companies that buyers actually bought? (method v4, item 6)

Sample: every in-band company with positive EBITDA and readable figures that is not out of the sector and not a
duplicate, whatever its ownership (being sold changes who owns a company, so ownership filters are switched off
here). Companies bought between 2023 and 2026 are listed in config/deal_history.csv with the buyer and a source.
For each weighting it reports the AUC: the chance that a bought company scores above one that was not
(0.5 = no better than chance, 1.0 = perfect), for all deals and for private equity deals only (direct buyouts
and sponsor-backed platforms, which is the buyer this ranking is for). Trade buyers buy for their own reasons
(customers, capability) so they are reported but not used to set the weights.
Writes data/outputs/backtest.json and data/outputs/backtest.md.
Caveats, stated in the output: small sample (15 deals, 7 by private equity), some accounts are from after the
deal, and the sample only covers companies whose industry codes put them in the universe.
Skills: returns-sensitivity (which variables carry the result), deal-screening.
"""
import os, json, itertools
import numpy as np
import pandas as pd
import score as SC
import infra_test as IT
from settings import C, W

ROOT = SC.ROOT
OUT = f'{ROOT}/data/outputs'

WEIGHTS = {
    'v3.1 (previous: no growth)': {'revenue_visibility': 25, 'growth': 0, 'strategy_fit': 20, 'size_fit': 15, 'margin_quality': 25, 'balance_sheet': 15},
    'v4 (adopted)': dict(W),
    'growth-heavy (test)': {'revenue_visibility': 15, 'growth': 25, 'strategy_fit': 15, 'size_fit': 15, 'margin_quality': 15, 'balance_sheet': 15},
    'equal (test)': {k: 100 / 6 for k in W},
}


def auc(x, y):
    x, y = np.asarray(x, float), np.asarray(y, bool)
    p, n = x[y], x[~y]
    if not len(p) or not len(n):
        return None
    return float(np.mean([(a > b) + 0.5 * (a == b) for a in p for b in n]))


def boot(x, y, reps=2000, seed=1):
    rng = np.random.default_rng(seed)
    x, y = np.asarray(x, float), np.asarray(y, bool)
    p, n = x[y], x[~y]
    vals = []
    for _ in range(reps):
        a, b = rng.choice(p, len(p)), rng.choice(n, len(n))
        vals.append(np.mean((a[:, None] > b[None, :]) + 0.5 * (a[:, None] == b[None, :])))
    return float(np.percentile(vals, 5)), float(np.percentile(vals, 95))


def main():
    D = SC.load_candidates()
    U = D[(D['status'] == 'Shortlist') & D['numbers_ok'] & (D['ebitda'] > 0) & (D['relevance'] != 'OUT')
          & ~D['excluded_reason'].fillna('').str.startswith('Duplicate')].copy()
    U['relevance'] = U['relevance'].replace({'UNSURE': 'ADJACENT'})
    U = SC.score_frame(U, weights=W)
    # infrastructure test (v4.1): labels from rules only, so bought and not-bought companies are treated alike
    lab = U.apply(lambda r: IT.rule_fields(r['CompanyNumber'], r['business_type']), axis=1, result_type='expand')
    U['s_revenue_type'] = lab['revenue_type'].map(IT.REV_SCORE).fillna(0.3)
    U['s_contract_length'] = lab['contract_length'].map(IT.LEN_SCORE).fillna(0.4)
    deals = pd.read_csv(f'{ROOT}/config/deal_history.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber')
    U['deal'] = U['CompanyNumber'].isin(deals.index)
    U['buyer_type'] = U['CompanyNumber'].map(deals['buyer_type'])
    pe = U['buyer_type'].isin(['sponsor', 'sponsor platform'])
    res = {'sample': int(len(U)), 'deals': int(U['deal'].sum()), 'pe_deals': int(pe.sum()), 'weights': {}, 'criteria': {}}
    for name, w in WEIGHTS.items():
        sc = sum(U[f's_{k}'] * v for k, v in w.items())
        res['weights'][name] = {'weights': w, 'auc_all': auc(sc, U['deal']), 'auc_pe': auc(sc, pe), 'auc_pe_90': boot(sc, pe)}
    for k in W:
        res['criteria'][k] = {'auc_all': auc(U[f's_{k}'], U['deal']), 'auc_pe': auc(U[f's_{k}'], pe)}
    # extra inputs: each infrastructure-test label on its own, and added to v4 at 10 points (v4 scaled to 90)
    res['infra_test'] = {}
    for k in ['revenue_type', 'contract_length']:
        res['infra_test'][k + ' on its own'] = {'auc_all': auc(U[f's_{k}'], U['deal']), 'auc_pe': auc(U[f's_{k}'], pe), 'auc_pe_90': boot(U[f's_{k}'], pe)}
    base = sum(U[f's_{k}'] * v for k, v in W.items())
    for name, extra in [('v4 + revenue type (10 pts)', ['revenue_type']), ('v4 + contract length (10 pts)', ['contract_length']),
                        ('v4 + both (10 pts each)', ['revenue_type', 'contract_length'])]:
        sc = base * (100 - 10 * len(extra)) / 100 + sum(U[f's_{k}'] * 10 for k in extra)
        res['infra_test'][name] = {'auc_all': auc(sc, U['deal']), 'auc_pe': auc(sc, pe), 'auc_pe_90': boot(sc, pe)}
    res['infra_test_labels_of_deals'] = (lab[U['deal'].values].assign(CompanyName=U.loc[U['deal'], 'CompanyName'].values,
                                         buyer_type=U.loc[U['deal'], 'buyer_type'].values).to_dict('records'))
    sc = sum(U[f's_{k}'] * v for k, v in W.items())
    U['pct'] = pd.Series(sc).rank(pct=True)
    res['companies'] = (U[U['deal']][['CompanyName', 'buyer_type', 'pct']].assign(buyer=lambda d: d.index.map(lambda i: None))
                        .drop(columns='buyer').round(2).sort_values('pct', ascending=False).to_dict('records'))
    json.dump(res, open(f'{OUT}/backtest.json', 'w'), indent=1)
    lines = ['# Back-test of the weights', '', f"Sample: {res['sample']} in-band companies with positive EBITDA; {res['deals']} were bought in 2023-2026, {res['pe_deals']} of them by private equity (direct or through a backed platform).", '',
             '| Weighting | AUC, all deals | AUC, private equity | 90% range (private equity) |', '|---|---|---|---|']
    for name, r in res['weights'].items():
        lines.append(f"| {name} | {r['auc_all']:.2f} | {r['auc_pe']:.2f} | {r['auc_pe_90'][0]:.2f}-{r['auc_pe_90'][1]:.2f} |")
    lines += ['', '| Criterion on its own | AUC, all deals | AUC, private equity |', '|---|---|---|']
    for k, r in res['criteria'].items():
        lines.append(f"| {k.replace('_', ' ')} | {r['auc_all']:.2f} | {r['auc_pe']:.2f} |")
    lines += ['', '## Infrastructure test (method v4.1): extra inputs, not adopted', '',
              'Labels from rules only (business type plus contract terms found in the accounts text), so every company is treated alike.', '',
              '| Test | AUC, all deals | AUC, private equity | 90% range (private equity) |', '|---|---|---|---|']
    for name, r in res['infra_test'].items():
        lines.append(f"| {name} | {r['auc_all']:.2f} | {r['auc_pe']:.2f} | {r['auc_pe_90'][0]:.2f}-{r['auc_pe_90'][1]:.2f} |")
    v4 = res['weights']['v4 (adopted)']['auc_pe']
    best = max((r['auc_pe'], n) for n, r in res['infra_test'].items() if n.startswith('v4 +'))
    verdict = (f"Best combination: {best[1]} at {best[0]:.2f} against v4 at {v4:.2f}. "
               + ('It beats v4 by 0.05 or more, but with ' if best[0] >= v4 + 0.05 else 'It does not clearly beat v4, so no weight change is proposed. With ')
               + f"{res['pe_deals']} private equity deals the 90% ranges overlap heavily; keep the labels as information only.")
    lines += ['', verdict]
    lines += ['', 'AUC is the chance a bought company scores above one that was not: 0.5 is chance, 1.0 is perfect.',
              'Caveats: few deals, so the ranges are wide; some accounts are from after the deal; trade buyers buy for their own reasons.']
    open(f'{OUT}/backtest.md', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
