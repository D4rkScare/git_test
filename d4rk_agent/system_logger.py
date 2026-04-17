"""
SIRIAN SYSTEM LOGGER — 통합 로깅
행동/결과/실패/학습 변화 추적
"""
import json, os, logging
from datetime import datetime
from utils import strip_chinese

log = logging.getLogger("syslog")
LOG_FILE  = "C:/Users/gohun/Desktop/sirian/sirian_space/system_log.jsonl"
MAX_LINES = 5000

class SystemLogger:
    def __init__(self):
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        self._buffer = []

    def log_all(self, state: dict, action, result, evaluation: dict):
        entry = {
            "time":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "state":  self._safe(state),
            "action": action.type if hasattr(action,'type') else str(action),
            "payload":str(getattr(action,'payload',{}))[:100],
            "result": result.summary() if hasattr(result,'summary') else str(result)[:100],
            "success":getattr(result,'success', False),
            "score":  evaluation.get("score", 0.5),
            "reason": evaluation.get("reason",""),
        }
        self._buffer.append(entry)
        if len(self._buffer) >= 10:
            self._flush()

    def log_event(self, event_type: str, detail: str, score: float = None):
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": event_type,
            "detail": strip_chinese(detail)[:200],
        }
        if score is not None:
            entry["score"] = score
        self._buffer.append(entry)
        if len(self._buffer) >= 10:
            self._flush()

    def _flush(self):
        if not self._buffer: return
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                for entry in self._buffer:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            self._buffer = []
            self._trim()
        except: pass

    def _trim(self):
        """로그 파일 크기 제한"""
        try:
            with open(LOG_FILE,'r',encoding='utf-8') as f:
                lines = f.readlines()
            if len(lines) > MAX_LINES:
                with open(LOG_FILE,'w',encoding='utf-8') as f:
                    f.writelines(lines[-MAX_LINES:])
        except: pass

    def _safe(self, d: dict) -> dict:
        if not d: return {}
        return {k: strip_chinese(str(v))[:100] for k,v in list(d.items())[:5]}

    def get_recent(self, n: int = 20) -> list:
        self._flush()
        try:
            with open(LOG_FILE,'r',encoding='utf-8') as f:
                lines = f.readlines()
            return [json.loads(l) for l in lines[-n:] if l.strip()]
        except:
            return []

    def analyze_failures(self) -> dict:
        """실패 패턴 분석"""
        recent = self.get_recent(100)
        failures = [e for e in recent if not e.get("success", True)]
        if not failures: return {}
        from collections import Counter
        action_fails = Counter([e.get("action","") for e in failures])
        return {"total_failures": len(failures), "by_action": dict(action_fails)}

    def get_learning_delta(self) -> str:
        """학습 변화 요약"""
        recent = self.get_recent(50)
        if not recent: return ""
        scores = [e.get("score", 0.5) for e in recent if "score" in e]
        if len(scores) < 2: return ""
        first_half = sum(scores[:len(scores)//2]) / max(1, len(scores)//2)
        second_half = sum(scores[len(scores)//2:]) / max(1, len(scores) - len(scores)//2)
        delta = second_half - first_half
        if delta > 0.05:
            return f"성능 향상 중 (+{delta:.2f})"
        elif delta < -0.05:
            return f"성능 하락 주의 ({delta:.2f})"
        return "안정적"

system_logger = SystemLogger()
