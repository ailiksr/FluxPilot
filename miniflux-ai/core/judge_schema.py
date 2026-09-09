from dataclasses import dataclass

_FIELDS = ('new_information','factual_evidence','depth','timeliness','originality','promotional','entertainment_noise','empty_or_low_content')

def validate_judge(obj: dict) -> dict:
    if not isinstance(obj, dict): raise ValueError('judge must be an object')
    out = {}
    for k in _FIELDS:
        v = obj.get(k)
        if isinstance(v, bool): raise ValueError(f'{k} must be 0 or 1')
        if isinstance(v, str) and v.strip() in ('0','1'): v=int(v)
        if v not in (0,1): raise ValueError(f'{k} must be 0 or 1')
        out[k]=v
    return out
