import json,os,threading
import fcntl
from datetime import datetime,timezone
_PATH=os.environ.get('AI_WORKER_DATA_DIR','/app/data') + '/feed_advice_actions.jsonl'; _LOCK=threading.Lock(); _LOCK_PATH=_PATH+'.lock'
def record(action,advice):
    row={'action':action,'at':datetime.now(timezone.utc).isoformat(),'advice':advice}
    try:
        from core.control_store import enabled as pg_write_enabled, persist_action
        if pg_write_enabled():
            persist_action(row)
            return row
    except Exception:
        raise
    with _LOCK:
        os.makedirs(os.path.dirname(_PATH),exist_ok=True)
        with open(_LOCK_PATH,'a',encoding='utf-8') as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                with open(_PATH,'a',encoding='utf-8') as f:
                    f.write(json.dumps(row,ensure_ascii=False,separators=(",", ":"))+'\n')
                    f.flush()
                    os.fsync(f.fileno())
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    try:
        from core.pg_mirror import mirror_action
        mirror_action(row)
    except Exception:
        pass
    return row
