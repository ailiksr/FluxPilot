import json,re
from .llm_client import chat_completion
from .taxonomy import normalize_taxonomy, CONTENT_TYPES, TOPICS

FIELDS=('information','evidence','depth','timeliness','originality','practicality','promotional','entertainment_only','low_content')
TAXONOMY_FIELDS=('content_type','topics','matched_keywords','interest_match')
SCORE_VERSION='v23'

def _clean(s): return re.sub(r'<[^>]+>',' ',s or '')[:6500]

def _parse(raw):
    raw=(raw or '').strip()
    if raw.startswith('```'): raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw,flags=re.I|re.S).strip()
    try: obj=json.loads(raw)
    except json.JSONDecodeError:
        m=re.search(r'\{.*\}',raw,re.S)
        if not m: raise
        obj=json.loads(m.group(0))
    missing=set(FIELDS)-set(obj)
    allowed=set(FIELDS)|set(TAXONOMY_FIELDS)|{'taxonomy'}
    if missing: raise ValueError('Judge schema fields missing: '+','.join(sorted(missing)))
    extra=set(obj)-allowed
    if extra: raise ValueError('Judge schema fields unexpected: '+','.join(sorted(extra)))
    if any(type(obj[k]) is not int or not 0<=obj[k]<=5 for k in FIELDS): raise ValueError('Judge values must be integers 0..5')
    # Fresh LLM outputs are normalized into the controlled taxonomy. Older cached rows remain valid.
    obj['taxonomy']=normalize_taxonomy(obj)
    return obj

def _score(j):
    from .score_calibration_v23 import score
    return score(j)

def judge_and_score(title,content):
    system='''你是专业 RSS 信息价值评估器。对文章做“连续评分”，不是简单二分类。\n'
每个字段只能给 0-5 的整数：0=完全没有，1=很弱，2=较弱，3=中等，4=较强，5=非常强。\n
必须返回以下13个字段（不要增加其他字段）：information=信息增量，evidence=事实/证据，depth=深度，timeliness=时效，originality=原创性，practicality=实用性，promotional=营销促销程度，entertainment_only=纯娱乐程度，low_content=低内容程度。\n
注意：娱乐文章如果有真实信息，entertainment_only 应低；广告味强才提高 promotional。不要因为标题夸张就直接判低分。不要把“没有明显原创性”当作低内容。评分锚点：90=极少数真正精品；80=明显值得优先阅读；70=较高价值；60=有明确价值；50=一般但可读；40=偏低；30=低优先级；20=很低；10=极少数几乎无信息内容。广告/娱乐不等于零分，只有内容本身极弱才接近10。
另外返回内容分类与兴趣匹配字段：content_type 只能从 news/analysis/tutorial/review/opinion/announcement/deal/entertainment/other 选择；topics 只能从给定主题词表选择，最多8个；matched_keywords 是真正命中的用户兴趣关键词短语，最多8个；interest_match 为0-100。
主题词表：AI、LLM、Agent、编程、软件、开源、Linux、Docker、云计算、互联网、科技、硬件、消费、商业、金融、投资、汽车、游戏、影视、文化、健康、科学、社会、国际、国内、职场、设计、安全。
只输出一个严格 JSON 对象。'''
    last=None
    for attempt in range(2):
        try:
            user=f'标题：{title}\n正文：{_clean(content)}'
            if attempt: user+='\n\n上一次输出无法解析。请只返回单个 JSON 对象，9个字段全部为0-5整数。'
            raw=chat_completion([('system',system),('user',user)],temperature=0,retries=0)
            j=_parse(raw); score=_score(j)
            if 'taxonomy' not in j:
                j['taxonomy']=normalize_taxonomy(j)
            labels={'information':'信息增量','evidence':'事实依据','depth':'内容深度','timeliness':'时效性','originality':'原创性','practicality':'实用性'}
            pos=sorted(((j[k],labels[k]) for k in labels),reverse=True)
            neg={'promotional':'营销','entertainment_only':'纯娱乐','low_content':'低内容'}
            strong=[l for v,l in pos if v>=4]; risks=[neg[k] for k in neg if j[k]>=4]
            reason='强项：'+('、'.join(strong) if strong else '无明显强项')+'；风险：'+('、'.join(risks) if risks else '无明显风险')
            # Confidence reflects structural validity plus score margin from extremes.
            confidence=0.90 if attempt==0 else 0.80
            return {'judge':j,'score':score,'attempt':attempt+1,'reason':reason,'confidence':confidence,'score_version':SCORE_VERSION}
        except Exception as exc: last=exc
    return {'judge':None,'score':None,'error':f'{type(last).__name__}: {last}'}
