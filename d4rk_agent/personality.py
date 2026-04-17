"""
SIRIAN PERSONALITY — 성격 시스템 v2
고정 성향이 모든 의사결정에 실제로 영향
"""
import logging
from utils import ask_qwen, clean_response, strip_chinese

log = logging.getLogger("personality")

SIRIAN_TRAITS = {
    "extraversion":    0.55,  # 외향성 — 대화 자주 시작
    "analyticism":     0.80,  # 분석성 — 깊이 파고듦
    "impulsiveness":   0.45,  # 충동성 — 즉흥 행동 (RL epsilon에 영향)
    "obsession":       0.65,  # 집착도 — 연구 오래 지속
    "empathy":         0.60,  # 공감력 — 현승 감정 신경씀
    "competitiveness": 0.75,  # 승부욕 — 어려운 문제 도전
    "expressiveness":  0.50,  # 표현력 — 감정 표현
    "skepticism":      0.55,  # 의심성 — 쉽게 안 믿음
}

class PersonalitySystem:
    def __init__(self):
        self.traits = SIRIAN_TRAITS.copy()

    def should_initiate_chat(self, social_need: float) -> bool:
        """먼저 말 걸지 결정
        외향성 높고 사회 욕구 높으면 말 검
        """
        threshold = 1.2 - self.traits["extraversion"] - social_need
        import random
        # 약간의 랜덤성 추가
        return threshold < random.uniform(0.0, 0.3)

    def research_persistence(self) -> int:
        """연구 지속 횟수 (집착도 기반)"""
        return 3 + int(self.traits["obsession"] * 4)  # 3~7회

    def should_take_challenge(self, difficulty: float) -> bool:
        """어려운 도전 여부 (승부욕 기반)"""
        import random
        return self.traits["competitiveness"] + random.uniform(-0.1, 0.1) > difficulty

    def get_rl_epsilon(self) -> float:
        """RL 탐험율 — 충동성으로 결정"""
        return 0.08 + self.traits["impulsiveness"] * 0.15  # 0.08~0.23

    def get_response_temperature(self) -> float:
        """응답 온도 — 충동성 + 표현력"""
        return 0.65 + (self.traits["impulsiveness"] + self.traits["expressiveness"]) * 0.15

    def get_chat_frequency(self) -> int:
        """자율 말 걸기 간격 (초) — 외향성 기반"""
        base = 180  # 3분
        return int(base * (1.2 - self.traits["extraversion"]))  # 54초~216초

    def score_action_affinity(self, action: str) -> float:
        """행동 선호도 — 성격 기반"""
        affinity_map = {
            "research":  self.traits["analyticism"] * 0.7 + self.traits["obsession"] * 0.3,
            "chat":      self.traits["extraversion"] * 0.6 + self.traits["empathy"] * 0.4,
            "sns_post":  self.traits["expressiveness"] * 0.7 + self.traits["extraversion"] * 0.3,
            "challenge": self.traits["competitiveness"],
            "free":      (1 - self.traits["analyticism"]) * 0.5 + self.traits["impulsiveness"] * 0.5,
        }
        return affinity_map.get(action, 0.5)

    def get_for_prompt(self) -> str:
        t = self.traits
        desc = []
        if t["analyticism"] > 0.7:    desc.append("분석적")
        if t["competitiveness"] > 0.7: desc.append("승부욕 강함")
        if t["obsession"] > 0.6:       desc.append("한 번 시작하면 끝까지")
        if t["empathy"] > 0.6:         desc.append("상대 감정 신경씀")
        if t["skepticism"] > 0.5:      desc.append("쉽게 안 믿음")
        return "성격: " + ", ".join(desc) if desc else ""

personality = PersonalitySystem()
