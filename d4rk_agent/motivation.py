"""
SIRIAN MOTIVATION — 동기/보상 시스템 v2
내부 상태 변수 + RL Q값 결합으로 행동 선택
"""
import json, os, logging, threading, time
from utils import ask_qwen, clean_response, strip_chinese
from datetime import datetime

log = logging.getLogger("motivation")
STATE_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/inner_state.json"

class MotivationSystem:
    def __init__(self):
        self.state = {
            "curiosity":    0.6,   # 호기심 — 높을수록 탐색
            "boredom":      0.3,   # 지루함 — 높을수록 새 활동
            "satisfaction": 0.5,   # 만족도 — 높을수록 현재 유지
            "energy":       0.8,   # 에너지 — 낮으면 쉬고 싶음
            "social_need":  0.4,   # 사회 욕구 — 높으면 말 걸고 싶음
        }
        self._load()
        self._last_tick = datetime.now()

    def _load(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE,'r',encoding='utf-8') as f:
                    saved = json.load(f)
                    # 유효한 키만 업데이트
                    for k in self.state:
                        if k in saved and isinstance(saved[k], (int, float)):
                            self.state[k] = float(saved[k])
        except: pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE,'w',encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except: pass

    def tick(self):
        """시간 경과에 따른 자연 변화 — 30초마다 호출됨"""
        now = datetime.now()
        elapsed = (now - self._last_tick).seconds / 60  # 분 단위
        self._last_tick = now

        # 자연 변화 (분당 변화량)
        rate = min(elapsed, 5)  # 최대 5분치 한 번에 적용
        self.state["boredom"]      = min(1.0, self.state["boredom"] + 0.005 * rate)
        self.state["energy"]       = max(0.2, self.state["energy"] - 0.002 * rate)
        self.state["social_need"]  = min(1.0, self.state["social_need"] + 0.004 * rate)
        self.state["curiosity"]    = min(1.0, self.state["curiosity"] + 0.002 * rate)
        # 만족도는 서서히 중립으로
        self.state["satisfaction"] += (0.5 - self.state["satisfaction"]) * 0.01 * rate
        self.state["satisfaction"]  = max(0.0, min(1.0, self.state["satisfaction"]))

        # 주기적 저장
        self._save()

    def reward(self, action_type: str, success: bool, score: float = None):
        """행동 결과에 따른 보상/패널티"""
        # score가 있으면 더 정확한 보상
        magnitude = score if score is not None else (0.7 if success else 0.3)

        if action_type == "research":
            delta = (magnitude - 0.5) * 0.3
            self.state["curiosity"]    = max(0.0, min(1.0, self.state["curiosity"] - delta * 0.5))
            self.state["satisfaction"] = max(0.0, min(1.0, self.state["satisfaction"] + delta))
            self.state["boredom"]      = max(0.0, self.state["boredom"] - delta * 0.4)

        elif action_type == "chat":
            delta = (magnitude - 0.5) * 0.2
            self.state["social_need"]  = max(0.0, self.state["social_need"] - 0.2 * magnitude)
            self.state["satisfaction"] = max(0.0, min(1.0, self.state["satisfaction"] + delta))
            self.state["energy"]       = max(0.1, self.state["energy"] - 0.03)

        elif action_type == "sns":
            self.state["social_need"] = max(0.0, self.state["social_need"] - 0.15 * magnitude)
            self.state["boredom"]     = max(0.0, self.state["boredom"] - 0.1)

        elif action_type == "free":
            self.state["boredom"]      = max(0.0, self.state["boredom"] - 0.15)
            self.state["satisfaction"] = max(0.0, min(1.0, self.state["satisfaction"] + 0.1))

        elif action_type == "rest":
            self.state["energy"]       = min(1.0, self.state["energy"] + 0.2)
            self.state["boredom"]      = min(1.0, self.state["boredom"] + 0.05)
            self.state["satisfaction"] = max(0.0, self.state["satisfaction"] - 0.05)

        self._save()

    def decide_action(self) -> str:
        """보상 최대화 기준 + RL Q값 결합"""
        s = self.state

        # 동기 기반 점수
        scores = {
            "research":  s["curiosity"] * 0.6 + s["boredom"] * 0.4,
            "chat":      s["social_need"] * 0.7 + s["energy"] * 0.3,
            "sns_post":  s["social_need"] * 0.4 + s["boredom"] * 0.6,
            "free":      s["boredom"] * 0.5 + s["energy"] * 0.5,
            "rest":      (1.0 - s["energy"]) * 0.9,
            "search":    s["curiosity"] * 0.8 + s["boredom"] * 0.2,
        }

        # RL Q값과 결합 (60% 동기 + 40% RL)
        try:
            from rl_learner import rl
            state_key = rl._get_state()
            for action in scores:
                q = rl.policy["action_values"].get(action, {}).get(state_key, 0.5)
                scores[action] = scores[action] * 0.6 + q * 0.4
        except: pass

        # 성격 가중치 적용
        try:
            from personality import personality
            t = personality.traits
            scores["research"]  *= (0.5 + t["analyticism"] * 0.5)
            scores["chat"]      *= (0.5 + t["extraversion"] * 0.5)
            scores["sns_post"]  *= (0.5 + t["expressiveness"] * 0.5)
        except: pass

        return max(scores, key=scores.get)

    def get_state_key(self) -> str:
        s = self.state
        if s["energy"] < 0.3:    return "tired"
        if s["curiosity"] > 0.7: return "curious"
        if s["boredom"] > 0.6:   return "bored"
        return "default"

    def get_summary(self) -> str:
        s = self.state
        lines = []
        if s["curiosity"] > 0.7:    lines.append("호기심 높음")
        if s["boredom"] > 0.6:      lines.append("지루함")
        if s["satisfaction"] > 0.7: lines.append("만족스러움")
        if s["energy"] < 0.3:       lines.append("피곤함")
        if s["social_need"] > 0.7:  lines.append("말하고 싶음")
        return ", ".join(lines) if lines else "평온"

    def get_for_prompt(self) -> str:
        s = self.state
        return (
            f"내면 상태: {self.get_summary()}\n"
            f"호기심:{s['curiosity']:.1f} "
            f"지루함:{s['boredom']:.1f} "
            f"만족:{s['satisfaction']:.1f} "
            f"에너지:{s['energy']:.1f} "
            f"사회욕구:{s['social_need']:.1f}"
        )

motivation = MotivationSystem()
