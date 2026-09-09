from collections import defaultdict

def build_advice(rows):
    by=defaultdict(list)
    for r in rows:
        fid=r.get('feed_id')
        if fid is not None: by[str(fid)].append(r)
    out=[]
    for fid,items in by.items():
        scored=[x for x in items if isinstance(x.get('score'),int)]
        if not scored: continue
        avg=round(sum(x['score'] for x in scored)/len(scored),1)
        low=sum(x['score']<20 for x in scored)
        if len(scored)>=3 and avg<25 and low/len(scored)>=.7:
            out.append({'feed_id':fid,'type':'deprioritize','priority':'high','average_score':avg,'sample_size':len(scored),'reason':'近期文章大多数为低价值，建议降低该 Feed 优先级。','requires_approval':True})
        elif len(scored)>=3 and avg<45:
            out.append({'feed_id':fid,'type':'review','priority':'medium','average_score':avg,'sample_size':len(scored),'reason':'近期平均价值偏低，建议人工复核 Feed。','requires_approval':True})
    return out
