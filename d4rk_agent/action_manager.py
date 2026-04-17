"""
SIRIAN ACTION MANAGER — 행동 통제 핵심
반복 차단, 위험 차단, 속도 제한
"""
import time, logging, re, json, os
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional
from utils import ask_qwen, strip_chinese

log = logging.getLogger("action_mgr")

MAX_SAME_ACTION_PER_HOUR = 5
MAX_SAME_ERROR = 3
TIME_LIMIT_SEC = 15

@dataclass
class Action:
    type: str           # research / chat / sns / search / code / rest / free
    payload: dict = field(default_factory=dict)
    priority: int = 5
    source: str = "brain"  # brain / user / researcher / mastodon

@dataclass
class ActionResult:
    success: bool
    output: str = ""
    error: str = ""
    score: float = 0.5

    def summary(self) -> str:
        if self.success:
            return f"성공: {self.output[:100]}"
        return f"실패: {self.error[:100]}"

class ActionManager:
    def __init__(self):
        self._history = []              # 실행 기록
        self._error_counts = defaultdict(int)  # 에러별 카운트
        self._blacklist = set()         # 금지 행동
        self._rate_window = defaultdict(list)  # 속도 제한용
        self._load_blacklist()

    def _load_blacklist(self):
        try:
            path = "C:/Users/gohun/Desktop/sirian/sirian_space/blacklist.json"
            if os.path.exists(path):
                with open(path,'r',encoding='utf-8') as f:
                    self._blacklist = set(json.load(f))
        except: pass

    def _save_blacklist(self):
        try:
            path = "C:/Users/gohun/Desktop/sirian/sirian_space/blacklist.json"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path,'w',encoding='utf-8') as f:
                json.dump(list(self._blacklist), f)
        except: pass

    def validate(self, action: Action) -> tuple:
        """행동 유효성 검사. (ok, reason)"""
        key = f"{action.type}:{json.dumps(action.payload, sort_keys=True)[:50]}"

        # 블랙리스트
        if action.type in self._blacklist:
            return False, f"블랙리스트: {action.type}"

        # 속도 제한
        now = time.time()
        self._rate_window[action.type] = [
            t for t in self._rate_window[action.type]
            if now - t < 3600
        ]
        if len(self._rate_window[action.type]) >= MAX_SAME_ACTION_PER_HOUR:
            return False, f"속도 제한: {action.type} ({MAX_SAME_ACTION_PER_HOUR}/h)"

        # 반복 실패 차단
        if self._error_counts[key] >= MAX_SAME_ERROR:
            return False, f"반복 실패 차단: {key[:40]}"

        # 위험 행동 차단
        dangerous = self._check_dangerous(action)
        if dangerous:
            return False, f"위험 행동: {dangerous}"

        return True, "ok"

    def _check_dangerous(self, action: Action) -> str:
        if action.type == "code":
            code = action.payload.get("code","")
            dangerous_patterns = [
                r'\bos\.remove\b', r'\bshutil\.rmtree\b',
                r'\bos\.system\b.*rm', r'\bformat\b.*drive',
                r'rm\s+-rf', r'\beval\(.*__import__',
            ]
            for p in dangerous_patterns:
                if re.search(p, code, re.IGNORECASE):
                    return p
        return ""

    def execute(self, action: Action) -> ActionResult:
        """행동 실행"""
        ok, reason = self.validate(action)
        if not ok:
            log.info(f"행동 거부: {reason}")
            return ActionResult(success=False, error=reason, score=0.0)

        key = f"{action.type}:{json.dumps(action.payload, sort_keys=True)[:50]}"
        self._rate_window[action.type].append(time.time())

        try:
            result = self._dispatch(action)
            if result.success:
                self._error_counts[key] = 0
            else:
                self._error_counts[key] += 1
                if self._error_counts[key] >= MAX_SAME_ERROR:
                    log.warning(f"블랙리스트 추가: {action.type}")
                    self._blacklist.add(action.type)
                    self._save_blacklist()
                    # 30분 후 해제 (별도 스레드)
                    import threading
                    def unblacklist():
                        time.sleep(1800)
                        self._blacklist.discard(action.type)
                        self._error_counts[key] = 0
                        self._save_blacklist()
                    threading.Thread(target=unblacklist, daemon=True).start()

            self._history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "action": action.type,
                "success": result.success,
                "score": result.score
            })
            self._history = self._history[-200:]
            return result

        except Exception as e:
            log.error(f"실행 오류: {action.type} — {e}")
            self._error_counts[key] += 1
            return ActionResult(success=False, error=str(e), score=0.0)

    def _dispatch(self, action: Action) -> ActionResult:
        """행동 유형별 실행"""
        if action.type == "research":
            return self._exec_research(action)
        elif action.type == "search":
            return self._exec_search(action)
        elif action.type == "code":
            return self._exec_code(action)
        elif action.type == "sns":
            return self._exec_sns(action)
        elif action.type == "rest":
            return ActionResult(success=True, output="휴식", score=0.6)
        elif action.type == "free":
            return self._exec_free(action)
        else:
            return ActionResult(success=False, error=f"알 수 없는 행동: {action.type}")

    def _exec_research(self, action: Action) -> ActionResult:
        try:
            from researcher import researcher
            if not researcher.paused:
                topic = action.payload.get("topic","")
                if topic:
                    researcher.current_topic = topic
                return ActionResult(success=True, output=f"연구 중: {topic}", score=0.6)
            return ActionResult(success=False, error="대화 중 — 연구 대기", score=0.3)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def _exec_search(self, action: Action) -> ActionResult:
        try:
            from tools import tools
            query = action.payload.get("query","")
            results = tools.web_search(query, max_results=3)
            if results:
                out = "\n".join([f"- {r.get('title','')}: {r.get('snippet','')}" for r in results[:2]])
                return ActionResult(success=True, output=out[:300], score=0.7)
            return ActionResult(success=False, error="검색 결과 없음", score=0.2)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def _exec_code(self, action: Action) -> ActionResult:
        import subprocess, tempfile
        code = action.payload.get("code","")
        if not code:
            return ActionResult(success=False, error="코드 없음")
        try:
            with tempfile.NamedTemporaryFile(suffix='.py', mode='w',
                                             encoding='utf-8', delete=False) as f:
                f.write(code)
                tmp = f.name
            result = subprocess.run(
                ['py','-3.11',tmp],
                capture_output=True, text=True, timeout=TIME_LIMIT_SEC
            )
            out = strip_chinese(result.stdout + result.stderr)[:300]
            success = result.returncode == 0
            return ActionResult(success=success, output=out, score=0.8 if success else 0.2)
        except subprocess.TimeoutExpired:
            return ActionResult(success=False, error="timeout", score=0.1)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def _exec_sns(self, action: Action) -> ActionResult:
        try:
            from mastodon_client import mastodon
            content = action.payload.get("content","")
            if mastodon.enabled:
                result = mastodon.post_now(content)
                return ActionResult(success="완료" in result, output=result, score=0.7)
            return ActionResult(success=False, error="마스토돈 비활성")
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def _exec_free(self, action: Action) -> ActionResult:
        try:
            from autonomous_worker import worker
            worker._free_activity()
            return ActionResult(success=True, output="자유 활동 완료", score=0.6)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def get_stats(self) -> dict:
        recent = self._history[-50:]
        if not recent: return {}
        from collections import Counter
        types = Counter([h["action"] for h in recent])
        success_rate = sum(1 for h in recent if h["success"]) / len(recent)
        return {"action_counts": dict(types), "success_rate": round(success_rate,2)}

action_manager = ActionManager()
