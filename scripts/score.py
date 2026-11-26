"""Step 05: score and rank the cleaned shortlist (method v4, 26 Nov 2026).

Each company gets 0-1 on six criteria, multiplied by the weights in the sector's thesis file (total 100):
revenue visibility, sales growth, strategy fit, size, margin quality and balance sheet.
What counts as a good size, margin or debt level depends on the business type (network owner, recurring
services, contractor, project company), set in config/thesis/<sector>.json, so a fibre network is not marked
down for carrying debt a services firm could not, and a contractor is not marked down for a contractor's margin.
Kept beside the score and never blended into it: accessibility (ownership) and confidence (how far the inputs can be trusted).
Network owners with EBITDA at or below zero are not dropped: they go on a separate list (building_latest.csv).
History: v3 (24 Nov) analyst review; v3.1 net debt; v4 business types, growth (added after the back-test in
scripts/backtest.py), building list, group rule, EBITDA rules (normalise.py), three years read, confidence rule.
Skills: deal-screening (scoring rubric), market-map-and-sourcing (fit and access kept apart; estimates labelled).
"""
import os, re, datetime
import pandas as pd
from fx import to_gbp, rate, currency, label
from settings import C, W, TYPES, business_type

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, CFG = f'{ROOT}/data/outputs', f'{ROOT}/config'


def _load(path, **kw):
    return pd.read_csv(path, dtype={'CompanyNumber': str}, **kw).set_index('CompanyNumber') if os.path.exists(path) else pd.DataFrame()


HS = _load(f'{OUT}/history_summary.csv')       # history.py: years read, growth, margin stability, interest cover
BS = _load(f'{CFG}/balance_sheet.csv')         # net debt transcribed by hand from the latest accounts
RM = _load(f'{CFG}/revenue_mix.csv')           # revenue mix read from the accounts
NM = _load(f'{OUT}/ebitda_normalised.csv')     # normalise.py: the EBITDA rules
BT = _load(f'{CFG}/business_type.csv')
_V = f'{ROOT}/data/ocr/verified.csv'           # figures checked by eye against the filing
CHECKED = set(pd.read_csv(_V, dtype={'CompanyNumber': str})['CompanyNumber']) if os.path.exists(_V) else set()
TF = f'{ROOT}/data/history/text_figures.csv'
TXT = pd.read_csv(TF, dtype={'CompanyNumber': str}) if os.path.exists(TF) else pd.DataFrame(columns=['CompanyNumber', 'filed', 'problem'])
TXT = TXT[TXT['problem'].fillna('') == ''].sort_values('filed').drop_duplicates('CompanyNumber', keep='last').set_index('CompanyNumber')
MONEY = ['turnover', 'turnover_prior', 'operating_profit', 'ebitda', 'gross_profit', 'staff_costs', 'profit_before_tax', 'cash', 'net_assets']
clip = lambda x, lo, hi: max(lo, min(hi, x))


def hist(num, col):
    if num in HS.index and col in HS.columns and pd.notna(HS.at[num, col]):
        return HS.at[num, col]
    return None


def to_pounds(D):
    """Accounts filed in another currency (config/company_currency.csv) are converted to pounds before anything is compared."""
    D['reported_currency'] = D['CompanyNumber'].map(currency)
    for i in D.index[D['reported_currency'] != 'GBP']:
        f = to_gbp(D.at[i, 'CompanyNumber'])
        for c in MONEY:
            if c in D.columns and pd.notna(D.at[i, c]):
                D.at[i, c] = D.at[i, c] * f
    return D


def apply_rules(D):
    """Normalised EBITDA (already in pounds) replaces reported EBITDA; status follows the normalised figure."""
    D['ebitda_reported'] = D['ebitda']
    D['ebitda_adjustments'] = ''
    for i, r in D.iterrows():
        num = r['CompanyNumber']
        if num in NM.index and pd.notna(NM.at[num, 'ebitda_normalised']):
            D.at[i, 'ebitda'] = float(NM.at[num, 'ebitda_normalised'])
            D.at[i, 'ebitda_adjustments'] = NM.at[num, 'adjustments'] if pd.notna(NM.at[num, 'adjustments']) else ''
            if 'basis_normalised' in NM.columns and pd.notna(NM.at[num, 'basis_normalised']):
                D.at[i, 'ebitda_basis'] = NM.at[num, 'basis_normalised']
    D['ebitda_margin'] = D['ebitda'] / D['turnover']
    has = D['ebitda'].notna()
    D.loc[has & (D['ebitda'] > 0), 'status'] = 'Shortlist'
    D.loc[has & (D['ebitda'] <= 0) & D['status'].isin(['Shortlist', 'Watchlist (loss-making)']), 'status'] = 'Watchlist (loss-making)'
    D['business_type'] = D['CompanyNumber'].map(business_type)
    return D


def net_debt(num):
    """Net debt in pounds and where it came from: the hand-checked file first, else what the accounts text shows."""
    if num in BS.index:
        b = BS.loc[num].fillna(0)
        return float(b['bank_debt'] + b['leases_hp'] + b['shareholder_or_group_loans'] - b['cash']) * rate(b['currency']), 'checked by hand'
    if num in TXT.index:
        t = TXT.loc[num]
        debt = [t.get(c) for c in ('bank_loans', 'finance_leases')]
        if any(pd.notna(x) for x in debt) and pd.notna(t.get('cash')):
            return (sum(float(x) for x in debt if pd.notna(x)) - float(t['cash'])) * to_gbp(num), 'read from the accounts text'
    return None, None


# 1. Revenue visibility: evidence from the accounts beats the estimate
def visibility(r):
    num = r['CompanyNumber']
    if num in RM.index:
        return float(RM.at[num, 'visibility']), 'From the accounts: ' + RM.at[num, 'evidence']
    reason = str(r['relevance_reason']).lower()
    for score, pattern in C['visibility_rules']:
        if re.search(pattern, reason):
            return score, 'Provisional: estimated from the business description'
    return TYPES[r['business_type']]['visibility_default'], 'Provisional: estimated from the business type'


# 2. Growth: yearly average over 3+ years, else one year; project companies score on contract years left
def growth(r):
    num, g = r['CompanyNumber'], C['growth_scale']
    if r['business_type'] == 'project_company':
        end = BT.at[num, 'contract_end_year'] if num in BT.index and 'contract_end_year' in BT.columns else None
        if end is not None and pd.notna(end):
            left = max(0, int(end) - datetime.date.today().year)
            return clip(left / C['contract_life_full_marks_years'], 0, 1), f'{left} years left on the contract'
        return 0.3, 'contract length not known'
    cagr = hist(num, 'sales_cagr')
    years = hist(num, 'years_of_sales') or 0
    if cagr is not None:
        v, basis = float(cagr), f'sales {cagr:+.0%} a year over {int(years)} years'
    else:
        one = hist(num, 'growth_1y')
        one = float(one) if one is not None else (float(r['turnover_growth']) if pd.notna(r['turnover_growth']) else None)
        if one is None:
            return 0.4, 'growth not known (treated as flat)'
        v, basis = one, f'sales {one:+.0%} in one year (only two years read)'
    return clip((v - g['floor']) / (g['full_marks'] - g['floor']), 0, 1), basis


# 3. Strategy fit
FIT = C['fit_scores']


# 4. Size: EBITDA against the sweet spot for the business type
def size(r):
    e, t = r['ebitda'], TYPES[r['business_type']]
    lo, hi = t['ebitda_sweet_spot_gbp']
    if not r['numbers_ok'] or pd.isna(e) or e <= 0:
        return 0.0
    if e < t['ebitda_min_useful_gbp']:
        return 0.2
    if e < lo:
        return 0.2 + 0.8 * (e - t['ebitda_min_useful_gbp']) / (lo - t['ebitda_min_useful_gbp'])
    if e <= hi:
        return 1.0
    return max(0.6, 1.0 - 0.4 * (e - hi) / (t['ebitda_upper_fade_to_gbp'] - hi))


# 5. Margin quality: level against what is normal for the type (70%) and stability over 3+ years (30%)
def margin(r):
    if not r['numbers_ok']:
        return 0.0, 'no reliable margin'
    level = clip(r['ebitda_margin'] / TYPES[r['business_type']]['margin_full_marks'], 0, 1)
    swing = hist(r['CompanyNumber'], 'margin_swing_pp')
    if swing is None:
        return 0.7 * level + 0.3 * 0.5, 'stability not tested (fewer than 3 years read)'
    years = int(hist(r['CompanyNumber'], 'years_of_margin'))
    stability = clip(1 - (swing - 3) / 15, 0, 1)   # within 3 points = stable; 18+ points = unstable
    return 0.7 * level + 0.3 * stability, f'margin moved {swing:.0f} points across {years} years'


# 6. Balance sheet resilience: net assets, cash cover, margin headroom, interest cover, net debt against the type's comfort level
def balance(r):
    t = TYPES[r['business_type']]
    s = 0.4 if r['net_assets'] > 0 else 0.0
    if pd.notna(r['cash']) and r['turnover'] > 0:
        s += 0.3 * clip(r['cash'] / r['turnover'] / 0.15, 0, 1)
    full = t['margin_full_marks']
    if r['numbers_ok'] and r['ebitda_margin'] >= full / 3:
        s += 0.3
    elif r['numbers_ok'] and r['ebitda_margin'] >= full / 6:
        s += 0.15
    cover = hist(r['CompanyNumber'], 'interest_cover')
    if cover is not None and cover < 3:
        s -= 0.3 * (3 - cover) / 3
    nd, _ = net_debt(r['CompanyNumber'])
    if nd is not None and r['ebitda'] > 0 and nd / r['ebitda'] > t['net_debt_comfort_x']:
        s -= 0.4 * clip((nd / r['ebitda'] - t['net_debt_comfort_x']) / 3.0, 0, 1)
    return clip(s, 0, 1)


# Confidence (not scored): how far the inputs can be trusted
CF = C['confidence']


def confidence(r):
    if not r['numbers_ok']:
        return 'Low', 'numbers flagged', 0.0
    num, src = r['CompanyNumber'], str(r['figures_source'])
    reasons = []
    if src == 'Tagged':
        c = CF['source']['tagged']
    elif num in CHECKED or 'corrected by hand' in src:
        c = CF['source']['checked_against_filing']
        reasons.append('figures checked against the filing')
    elif hist(num, 'latest_line_confirmed'):
        c = CF['source']['confirmed_by_two_filings']
        reasons.append('figures confirmed by the next filing')
    elif src.startswith('OCR'):
        c = CF['source']['ocr_unchecked']
        reasons.append('figures read by OCR, not yet checked')
    else:
        c = CF['source']['text_unchecked']
        reasons.append('figures read from the accounts text, not yet checked')
    if str(r['ebitda_basis']).startswith('ESTIMATE'):
        c += CF['ebitda_estimated']
        reasons.append('EBITDA estimated (no D&A found)')
    missing = [lab for col, lab in (('cash', 'cash'), ('net_assets', 'net assets')) if pd.isna(r[col])]
    c += CF['missing_item'] * len(missing)
    if missing:
        reasons.append('missing ' + ', '.join(missing))
    years = hist(num, 'years_of_sales') or 1
    if years >= 3:
        c += CF['three_years_read']
    elif years <= 1:
        c += CF['one_year_only']
        reasons.append('only one year read')
    else:
        reasons.append('two years read')
    if r['relevance'] == 'ADJACENT':
        c += CF['adjacent']
        reasons.append('only adjacent to the thesis')
    if num not in RM.index:
        c += CF['revenue_mix_estimated']
        reasons.append('recurring revenue estimated')
    if label(num):
        reasons.append(label(num))
    level = 'High' if c >= CF['high'] - 1e-9 else 'Medium' if c >= CF['medium'] - 1e-9 else 'Low'
    return level, '; '.join(reasons), round(c, 2)


def score_frame(S, weights=None):
    """Adds the 0-1 criterion scores (s_*), the points (pts_*) and the total score."""
    weights = weights or W
    vis = S.apply(visibility, axis=1)
    S['s_revenue_visibility'] = [v[0] for v in vis]
    S['revenue_visibility_basis'] = [v[1] for v in vis]
    gr = S.apply(growth, axis=1)
    S['s_growth'] = [g[0] for g in gr]
    S['growth_basis'] = [g[1] for g in gr]
    S['s_strategy_fit'] = S['relevance'].map(FIT)
    S['s_size_fit'] = S.apply(size, axis=1)
    mq = S.apply(margin, axis=1)
    S['s_margin_quality'] = [m[0] for m in mq]
    S['margin_stability_basis'] = [m[1] for m in mq]
    S['s_balance_sheet'] = S.apply(balance, axis=1)
    for k, w in weights.items():
        S[f'pts_{k}'] = (S[f's_{k}'] * w).round(1)
    S['score'] = S[[f'pts_{k}' for k in weights]].sum(axis=1).round(1)
    return S


def load_candidates():
    D = pd.read_csv(f'{OUT}/candidates_clean.csv', dtype={'CompanyNumber': str})
    return apply_rules(to_pounds(D))


def main():
    D = load_candidates()
    for i in D.index[D['reported_currency'] != 'GBP']:
        print(f"{D.at[i, 'CompanyName']}: {label(D.at[i, 'CompanyNumber'])}")
    GATE = C['sector_gate']['ranked_if_relevance_in']
    fwd = D[D['goes_forward']]
    S = fwd[fwd['status'] == 'Shortlist'].copy()
    check = S[~S['relevance'].isin(GATE)].copy()
    S = S[S['relevance'].isin(GATE)].copy()
    B = fwd[(fwd['status'] == 'Watchlist (loss-making)') & fwd['relevance'].isin(GATE)
            & fwd['business_type'].isin(C['building_list']['types'])].copy()
    print(f'Companies to score: {len(S)} ({len(check)} more need a sector check first); network owners still building: {len(B)}')
    S = score_frame(S)
    cf = S.apply(confidence, axis=1)
    S['confidence'] = [c[0] for c in cf]
    S['confidence_reasons'] = [c[1] for c in cf]
    S['confidence_points'] = [c[2] for c in cf]
    nd = S['CompanyNumber'].map(lambda n: net_debt(n))
    S['net_debt'] = [x[0] for x in nd]
    S['net_debt_source'] = [x[1] for x in nd]
    S['years_read'] = S['CompanyNumber'].map(lambda n: hist(n, 'years_of_sales'))
    S['business_type_label'] = S['business_type'].map(lambda t: TYPES[t]['label'])
    S['accessibility'] = S['ownership'].map(C['accessibility']).fillna('Check')
    S = S.sort_values('score', ascending=False).reset_index(drop=True)
    S.insert(0, 'rank', S.index + 1)
    S['scored_on'] = datetime.date.today().isoformat()
    S['method_version'] = C['method_version'].split(' ')[0]
    cols = (['rank', 'CompanyName', 'CompanyNumber', 'score'] + [f'pts_{k}' for k in W] +
            ['confidence', 'confidence_reasons', 'confidence_points', 'margin_stability_basis', 'growth_basis', 'method_version',
             'business_type', 'business_type_label', 'accessibility', 'relevance', 'relevance_reason', 'segment', 'turnover',
             'turnover_growth', 'ebitda', 'ebitda_reported', 'ebitda_adjustments', 'ebitda_margin', 'ebitda_basis',
             'figures_source', 'years_read', 'reported_currency', 'revenue_visibility_basis', 'data_flags', 'ownership',
             'owner_chain', 'owner_since_year', 'cash', 'net_assets', 'net_debt', 'net_debt_source', 'employees',
             'RegAddress.PostTown', 'accounts_filed', 'scored_on'])
    S = S[[c for c in cols if c in S.columns]]
    os.makedirs(f'{OUT}/rankings', exist_ok=True)
    S.to_csv(f'{OUT}/ranking_latest.csv', index=False)
    S.to_csv(f'{OUT}/rankings/ranking_{S["scored_on"].iloc[0]}.csv', index=False)
    check[['CompanyName', 'CompanyNumber', 'relevance', 'relevance_reason', 'segment', 'turnover', 'ebitda_margin', 'ownership']].sort_values(
        'turnover', ascending=False).to_csv(f'{OUT}/sector_check.csv', index=False)
    B['growth_1y'] = B['CompanyNumber'].map(lambda n: hist(n, 'growth_1y'))
    B['sales_cagr'] = B['CompanyNumber'].map(lambda n: hist(n, 'sales_cagr'))
    B['accessibility'] = B['ownership'].map(C['accessibility']).fillna('Check')
    B = B.sort_values('turnover', ascending=False)
    B[['CompanyName', 'CompanyNumber', 'business_type', 'relevance', 'relevance_reason', 'turnover', 'growth_1y', 'sales_cagr',
       'ebitda', 'ebitda_margin', 'ebitda_basis', 'net_assets', 'cash', 'ownership', 'owner_chain', 'accessibility',
       'figures_source']].to_csv(f'{OUT}/building_latest.csv', index=False)
    pd.set_option('display.width', 250)
    show = S.head(20).copy()
    show['turnover'] = (show['turnover'] / 1e6).round(1).astype(str) + 'm'
    show['ebitda_margin'] = (show['ebitda_margin'] * 100).round(0).astype(str) + '%'
    print(show[['rank', 'CompanyName', 'score', 'business_type', 'confidence', 'relevance', 'turnover', 'ebitda_margin']].to_string(index=False))
    print('Confidence:', S['confidence'].value_counts().to_dict())
    print('\nSaved ranking_latest.csv, building_latest.csv, a dated copy in data/outputs/rankings/ and sector_check.csv')


if __name__ == '__main__':
    main()
