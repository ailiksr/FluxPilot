"""V98 automation safety gate. Shadow-only, no side effects."""
VERSION="automation-gate-v1"

DEFAULT_POLICY={"auto_keep":False,"auto_negative":False,"require_explanation":True}

def evaluate(backtest=None):
    b=backtest or {}
    m=b.get("metrics") or {}
    keep=m.get("keep_precision")
    neg=m.get("negative_precision")
    ready_keep=bool(keep is not None and keep>=95)
    ready_negative=bool(neg is not None and neg>=95)
    return {"version":VERSION,"mode":"shadow_only","production_actions_enabled":False,"gates":{"auto_keep":ready_keep,"auto_negative":ready_negative},"reasons":["人工审核样本不足时保持人工确认","自动操作需要达到安全阈值"] ,"policy":DEFAULT_POLICY}
