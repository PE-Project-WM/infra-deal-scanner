"""Infrastructure test (method v4.1): is each ranked company "real" infrastructure in an investor's terms?

Four labels per company, shown on the profiles and in the workbook but NOT scored (the v4 weights are unchanged):
  revenue type       contracted / regulated / merchant / mixed   (after EDHEC TICCS business-risk models)
  contract length    under 1 year / 1–3 years / 3–10 years / 10+ years / unknown
  inflation linkage  yes / partial / no / unknown
  infra tier         core / core-plus / value-add / hybrid

Definitions (method/METHOD.md, "Infrastructure test"):
  contracted = most revenue fixed by contracts of 3+ years with committed payments (lease, availability, PFI, bulk deals)
  regulated  = price set by a regulator
  merchant   = revenue depends on orders, usage or renewals within 3 years (includes short subscriptions and framework work)
  mixed      = a material part (about a quarter or more) of two of the above

Hand calls live in config/infra_test.csv with a basis for each field. Points per basis follow the v4 confidence rule:
stated in the accounts 0.9, described in the accounts 0.6, public information 0.6, inferred from the business model 0.4.
A company's infrastructure-test confidence is the average over revenue type, contract length and inflation linkage:
High at 0.85 or more, Medium at 0.6 or more, otherwise Low. The tier is a judgement built on those three, so it
carries their confidence.
A ranked company missing from the config (a new entrant) gets the business-type default with basis "inferred".

rule_fields() gives the same labels from rules alone (business type plus the accounts text), so the back-test can
compare bought and not-bought companies on an equal footing; hand calls exist only for ranked companies.
Writes data/outputs/infra_test_latest.csv.
Skills: deal-screening (business quality), competitive-moat-review (barriers to entry).
"""
import os, re, glob
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, CFG = f'{ROOT}/data/outputs', f'{ROOT}/config'
POINTS = {'stated': 0.9, 'described': 0.6, 'public': 0.6, 'inferred': 0.4}
DEFAULTS = {   # business type -> (revenue type, contract length, inflation linkage, tier)
    'network_owner': ('mixed', 'unknown', 'unknown', 'core-plus'),
    'project_company': ('contracted', '10+ years', 'unknown', 'core'),
    'recurring_services': ('merchant', '1–3 years', 'unknown', 'hybrid'),
    'contractor': ('merchant', 'under 1 year', 'unknown', 'hybrid'),
}
FIELDS = [('revenue_type', 'revenue_type_basis'), ('contract_length', 'contract_length_basis'), ('inflation_linkage', 'inflation_basis')]
# scores used only by the back-test (higher = more infrastructure-like)
REV_SCORE = {'contracted': 1.0, 'regulated': 1.0, 'mixed': 0.6, 'merchant': 0.3}
LEN_SCORE = {'10+ years': 1.0, '3–10 years': 0.75, '1–3 years': 0.5, 'under 1 year': 0.25, 'unknown': 0.4}
WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'ten': 10, 'fifteen': 15, 'twenty': 20}
TERM = re.compile(r'\b(\d{1,2}|one|two|three|four|five|six|seven|ten|fifteen|twenty)(?:\s*(?:-|to)\s*(\d{1,2}))?[- ](year|month)s?[- ](?:term|contract|agreement|lease|concession)', re.I)


def label(p):
    return 'High' if p >= 0.85 else 'Medium' if p >= 0.6 else 'Low'


def bucket(years):
    return '10+ years' if years >= 10 else '3–10 years' if years >= 3 else '1–3 years' if years >= 1 else 'under 1 year'


def latest_text(num):
    fs = sorted(glob.glob(f'{ROOT}/data/history/text/{num}_*.txt')) or sorted(glob.glob(f'{ROOT}/data/deep_dive/text/{num}*'))
    return re.sub(r'\s+', ' ', open(fs[-1], errors='ignore').read()) if fs else ''


def rule_fields(num, business_type):
    """Labels from rules only: business-type default, then a contract term or PFI wording found in the accounts."""
    rt, cl, il, tier = DEFAULTS.get(business_type, DEFAULTS['recurring_services'])
    t = latest_text(num)
    terms = []
    for m in TERM.finditer(t):
        g = m.group(1)
        n = int(g) if g.isdigit() else WORDS[g.lower()]
        n = int(m.group(2)) if m.group(2) else n   # a range ("3-5 year terms") counts at its top
        terms.append(n / 12 if m.group(3).lower() == 'month' else n)
    terms = [x for x in terms if 0 < x <= 40]
    if re.search(r'\bPFI\b|private finance initiative|concession agreement', t, re.I):
        rt, cl = 'contracted', '10+ years'
    elif terms:
        cl = bucket(max(terms))
    elif business_type == 'contractor' and re.search(r'framework', t, re.I):
        cl = '1–3 years'
    if re.search(r'\b(RPI|CPI)\b.{0,60}(increase|uplift|index|linked)|index[- ]linked', t, re.I):
        il = 'partial'
    return {'revenue_type': rt, 'contract_length': cl, 'inflation_linkage': il, 'infra_tier': tier}


def main():
    R = pd.read_csv(f'{OUT}/ranking_latest.csv', dtype={'CompanyNumber': str})
    T = pd.read_csv(f'{CFG}/infra_test.csv', dtype={'CompanyNumber': str}).set_index('CompanyNumber')
    rows = []
    for _, r in R.iterrows():
        num = r['CompanyNumber']
        if num in T.index:
            d = T.loc[num].to_dict()
        else:
            rt, cl, il, tier = DEFAULTS.get(r['business_type'], DEFAULTS['recurring_services'])
            d = {'revenue_type': rt, 'revenue_type_basis': 'inferred', 'contract_length': cl, 'contract_length_basis': 'inferred',
                 'inflation_linkage': il, 'inflation_basis': 'inferred', 'infra_tier': tier, 'tier_reason': '',
                 'evidence': 'New to the ranking: business-type default until read', 'source': 'Business type'}
        pts = [POINTS.get(str(d[b]), 0.4) for _, b in FIELDS]
        p = round(sum(pts) / len(pts), 2)
        rows.append({'CompanyNumber': num, 'CompanyName': r['CompanyName'], 'rank': r['rank'], 'business_type': r['business_type'],
                     **{k: ('' if pd.isna(v) else v) for k, v in d.items() if k != 'CompanyName'},
                     'infra_points': p, 'infra_confidence': label(p), 'scored': 'No (shown only, method v4.1)'})
    D = pd.DataFrame(rows)
    D.to_csv(f'{OUT}/infra_test_latest.csv', index=False)
    print(f'Infrastructure test for {len(D)} ranked companies (not scored)')
    for c in ['revenue_type', 'contract_length', 'inflation_linkage', 'infra_tier', 'infra_confidence']:
        print(' ', c, D[c].value_counts().to_dict())


if __name__ == '__main__':
    main()
