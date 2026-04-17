"""
SIRIAN LEARNING SYSTEM — 진짜 학습
실패 분석, 패턴 학습, 전략 변경
"""
import json, os, logging
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("learning")
KNOWLEDGE_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/knowledge_base.json"

class LearningSystem:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "patterns": [],          # (상태, 행동, 결과, 점수) 패턴
            "blacklist": {},         # 실패 행동 (action → 카운트)
            "best_strategies": [],   # 높은 점수 전략
            "failure_analysis": [],  # 실패 분석
            "knowledge": {},         # (상황 → 최선 행동) 지식
        }
        try:
            if os.path.exists(KNOWLEDGE_FILE):
                with open(KNOWLEDGE_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(KNOWLEDGE_FILE), exist_ok=True)
            with open(KNOWLEDGE_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def update(self, state: dict, action_type: str, result, score: float):
        """학습 업데이트 — 핵심"""
        # 저품질 저장 금지
        if score < 0.4:
            self._analyze_failure(action_type, result, score)
            return

        pattern = {
            "state_emotion": state.get("emotion",""),
            "state_activity": state.get("activity","")[:50],
            "action": action_type,
            "score": score,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.data["patterns"].append(pattern)
        self.data["patterns"] = self.data["patterns"][-500:]

        if score > 0.8:
            self.data["best_strategies"].append(pattern)
            self.data["best_strategies"] = self.data["best_strategies"][-100:]

        # 지식 베이스 업데이트
        ctx_key = state.get("state_emotion","") + ":" + state.get("activity","")[:20]
        if ctx_key not in self.data["knowledge"]:
            self.data["knowledge"][ctx_key] = {}
        kb = self.data["knowledge"][ctx_key]
        old_score = kb.get(action_type, 0.5)
        kb[action_type] = old_score + 0.1 * (score - old_score)

        # 다른 시스템 업데이트
        self._update_rl(action_type, score)
        self._update_self_model(action_type, score)
        self._update_world_model(state, action_type, result)

        self._save()

    def _analyze_failure(self, action_type: str, result, score: float):
        """실패 분석"""
        error = getattr(result, 'error', str(result))[:100]
        key = f"{action_type}:{error[:30]}"

        if key not in self.data["blacklist"]:
            self.data["blacklist"][key] = 0
        self.data["blacklist"][key] += 1

        analysis = {
            "action": action_type,
            "error": error,
            "score": score,
            "count": self.data["blacklist"][key],
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.data["failure_analysis"].append(analysis)
        self.data["failure_analysis"] = self.data["failure_analysis"][-50:]

        log.info(f"실패 기록: {action_type} ({score:.1f}) — {error[:40]}")
        self._save()

    def _update_rl(self, action_type: str, score: float):
        try:
            from rl_learner import rl
            rl.update(action_type, score, "learning_system")
        except: pass

    def _update_self_model(self, action_type: str, score: float):
        try:
            from self_model import self_model
            self_model.record_action(action_type, score > 0.5)
        except: pass

    def _update_world_model(self, state: dict, action_type: str, result):
        try:
            from world_model import world_model
            activity = state.get("activity","")
            output = getattr(result, 'output', str(result))[:80]
            world_model.observe(f"{action_type} in {activity}", output)
        except: pass

    def get_best_action(self, state: dict) -> str:
        """현재 상태에서 최선 행동"""
        ctx_key = state.get("emotion","") + ":" + state.get("activity","")[:20]
        kb = self.data["knowledge"].get(ctx_key, {})
        if not kb: return ""
        return max(kb, key=kb.get)

    def should_explore(self) -> bool:
        """탐험 필요 여부"""
        # 최근 실패 많으면 탐험
        recent_fail = [f for f in self.data["failure_analysis"][-10:]
                      if f.get("score",1) < 0.4]
        return len(recent_fail) > 5

    def cleanup(self):
        """오래된/저품질 데이터 정리"""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        # 오래된 패턴 제거
        self.data["patterns"] = [
            p for p in self.data["patterns"]
            if p.get("time","") >= cutoff or p.get("score",0) > 0.8
        ]

        # 블랙리스트 낮은 카운트 제거
        self.data["blacklist"] = {
            k: v for k,v in self.data["blacklist"].items() if v >= 2
        }

        self._save()
        log.info("학습 데이터 정리 완료")

learning_system = LearningSystem()
