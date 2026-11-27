"""Which sector the pipeline runs for, and its thesis settings (config/thesis/<sector>.json).

Every script reads sector-specific settings from here, so adding a sector means adding a thesis file, not editing code.
Set SECTOR=<name> to run another sector; the default is digital.
"""
import os, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECTOR = os.environ.get('SECTOR', 'digital')
THESIS_PATH = f'{ROOT}/config/thesis/{SECTOR}.json'
C = json.load(open(THESIS_PATH))
W = C['scoring_weights']
TYPES = {k: v for k, v in C['business_types'].items() if not k.startswith('_')}

_BT = None
_SM = None


def business_type(num):
    """The company's business type: config/business_type.csv first, else the default for its sector, else the thesis default."""
    global _BT, _SM
    import pandas as pd
    if _BT is None:
        p = f'{ROOT}/config/business_type.csv'
        _BT = pd.read_csv(p, dtype={'CompanyNumber': str}).set_index('CompanyNumber')['business_type'].to_dict() if os.path.exists(p) else {}
        q = f'{ROOT}/data/outputs/sectors.csv'
        m = f'{ROOT}/config/sector_map.csv'
        _SM = {}
        for path in (q, m):   # the checked sector map wins over the industry-code placement
            if os.path.exists(path):
                s = pd.read_csv(path, dtype={'CompanyNumber': str})
                col = 'sector' if 'sector' in s.columns else 'sector_id'
                if col in s.columns:
                    _SM.update(dict(zip(s['CompanyNumber'], s[col])))
    if num in _BT:
        return _BT[num]
    return C.get('sector_default_type', {}).get(_SM.get(num), C.get('default_type', 'recurring_services'))
