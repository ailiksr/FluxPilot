"""Learn a lightweight user-interest profile from the new review epoch only.

This is deliberately conservative: it learns from explicit keep/ignore/archive
choices and taxonomy corrections, never from the legacy human_score field.
"""
import json, os
from pathlib import Path

DATA_DIR = Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data"))
REVIEWS = DATA_DIR / "benchmark_reviews.jsonl"
TAXONOMY = DATA_DIR / "taxonomy_feedback.jsonl"
SCORING = DATA_DIR / "scoring_results.jsonl"


def _lines(path):
    if not path.exists(): return []
    out=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def build_profile(exclude_entry_id=None):
    reviews={}
    for r in _lines(REVIEWS):
        eid=str(r.get("entry_id"))
        if exclude_entry_id is not None and eid==str(exclude_entry_id):
            continue
        if r.get("status") in {"keep","ignore","archive"}:
            reviews[eid]=r
    # Prefer explicit taxonomy corrections, but fall back to the taxonomy produced
    # by the current scoring ledger. The review UI does not need a second manual
    # taxonomy submission for every article.
    taxonomy={}
    for r in _lines(SCORING):
        j=r.get("judge") or {}
        t=j.get("taxonomy") or {}
        if t: taxonomy[str(r.get("entry_id"))]=t
    for r in _lines(TAXONOMY):
        t=r.get("taxonomy") or {}
        if t: taxonomy[str(r.get("entry_id"))]=t
    topic={}; keyword={}; content_type={}
    def bump(bucket,key,delta):
        if not key: return
        x=bucket.setdefault(str(key),{"keep":0,"ignore":0,"archive":0,"score":0})
        x["score"] += delta
        x["keep"] += 1 if delta>0 else 0
        x["ignore"] += 1 if delta<0 else 0
    for eid,r in reviews.items():
        t=taxonomy.get(eid,{})
        status=r.get("status")
        notes=(r.get("notes") or "")
        delta=1 if status=="keep" else -1
        if "promotion" in notes: delta=-2
        for x in t.get("topics",[]) if isinstance(t.get("topics"),list) else []: bump(topic,x,delta)
        for x in t.get("matched_keywords",[]) if isinstance(t.get("matched_keywords"),list) else []: bump(keyword,x,delta)
        ct=t.get("content_type")
        if ct: bump(content_type,ct,delta)
    def ranked(bucket):
        return sorted(({"name":k,**v} for k,v in bucket.items()), key=lambda x:(abs(x["score"]),x["keep"]+x["ignore"]), reverse=True)
    n=len(reviews)
    return {"version":"preference-profile-v2","epoch":"review-epoch-v2","samples":n,
            "ready":n>=20,"topics":ranked(topic)[:30],"keywords":ranked(keyword)[:50],"content_types":ranked(content_type)[:20]}


def learned_interest(taxonomy, profile=None):
    profile=profile or build_profile()
    if not profile.get("samples"): return None
    signals=[]
    for key in ("topics","matched_keywords"):
        for x in (taxonomy or {}).get(key,[]) or []:
            bucket=profile.get("topics" if key=="topics" else "keywords",[])
            row=next((r for r in bucket if r["name"]==x),None)
            if not row: continue
            # Require evidence. One positive occurrence should not manufacture a
            # strong preference; repeated positive/negative choices carry more weight.
            seen=row.get("keep",0)+row.get("ignore",0)+row.get("archive",0)
            score=float(row.get("score",0))
            if seen >= 2:
                signals.append(max(-1.0,min(1.0,score/seen)))
    if not signals: return 0.0
    # Negative evidence is allowed to be decisive; positive evidence needs consistency.
    pos=[v for v in signals if v>0]; neg=[v for v in signals if v<0]
    if pos and len(pos) < len(signals)/2 and not neg: return 0.0
    avg=sum(signals)/len(signals)
    return max(-25.0,min(25.0,avg*25.0))

# V108 explainable preference probability. This is separate from article quality.
def preference_probability(taxonomy, profile=None):
    profile=profile or build_profile()
    prior=0.5
    samples=int(profile.get('samples') or 0)
    if samples:
        prior=0.5  # neutral prior; evidence below is intentionally sparse and smoothed
    lookup={}
    for kind,key in (("topics","topics"),("keywords","matched_keywords"),("content_types","content_type")):
        for r in profile.get(kind,[]) or []: lookup[f'{key}:{r.get("name")}']=r
    vals=[]
    t=taxonomy or {}
    for x in t.get('topics',[]) or []: 
        r=lookup.get('topics:'+str(x));
        if r and (r.get('keep',0)+r.get('ignore',0)+r.get('archive',0))>=2: vals.append((r.get('keep',0)+1)/(r.get('keep',0)+r.get('ignore',0)+r.get('archive',0)+2))
    for x in t.get('matched_keywords',[]) or []:
        r=lookup.get('matched_keywords:'+str(x));
        if r and (r.get('keep',0)+r.get('ignore',0)+r.get('archive',0))>=2: vals.append((r.get('keep',0)+1)/(r.get('keep',0)+r.get('ignore',0)+r.get('archive',0)+2))
    ct=t.get('content_type'); r=lookup.get('content_type:'+str(ct)) if ct else None
    if r and (r.get('keep',0)+r.get('ignore',0)+r.get('archive',0))>=2: vals.append((r.get('keep',0)+1)/(r.get('keep',0)+r.get('ignore',0)+r.get('archive',0)+2))
    p=sum(vals)/len(vals) if vals else prior
    return max(0.05,min(0.95,p)),len(vals)
