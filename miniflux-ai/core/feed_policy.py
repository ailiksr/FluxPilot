import json,os
from datetime import datetime,timezone
PATH=os.environ.get('AI_WORKER_DATA_DIR','/app/data')+'/feed_weights.json'
def load():
    try:
        with open(PATH,encoding='utf-8') as f:return json.load(f)
    except Exception:return {}
def get_weight(feed_id):
    x=load().get(str(feed_id),{}); return int(x.get('weight',100))
def set_weight(feed_id,weight,reason):
    weight=max(0,min(100,int(weight))); d=load(); old=d.get(str(feed_id),{'weight':100})
    d[str(feed_id)]={'weight':weight,'updated_at':datetime.now(timezone.utc).isoformat(),'reason':reason,'previous_weight':old.get('weight',100)}
    os.makedirs(os.path.dirname(PATH),exist_ok=True)
    with open(PATH,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)
    return d[str(feed_id)]
def rollback(feed_id):
    d=load(); x=d.get(str(feed_id));
    if not x:return None
    return set_weight(feed_id,x.get('previous_weight',100),'rollback')
def apply_weight(score,feed_id):
    return max(0,min(100,round(score*get_weight(feed_id)/100))) if isinstance(score,(int,float)) else score
