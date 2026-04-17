"""
SIRIAN SOCIAL MODEL — 사회성/관계 모델
사람별 신뢰도/친밀도/감정 관리
"""
import json, os, logging
from utils import ask_qwen, clean_response, strip_chinese
from datetime import datetime

log = logging.getLogger("social")
SOCIAL_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/social_model.json"

class SocialModel:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "people": {
                "현승": {
                    "trust": 0.8,
                    "intimacy": 0.6,
                    "emotion": "호감",
                    "interaction_count": 0,
                    "last_seen": datetime.now().strftime("%Y-%m-%d"),
                    "notes": ["주인님","보안 연구원","CTF 플레이어"]
                }
            }
        }
        try:
            if os.path.exists(SOCIAL_FILE):
                with open(SOCIAL_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(SOCIAL_FILE), exist_ok=True)
            with open(SOCIAL_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def update_relation(self, person: str, interaction_type: str, positive: bool):
        """상호작용으로 관계 업데이트"""
        if person not in self.data["people"]:
            self.data["people"][person] = {
                "trust": 0.5, "intimacy": 0.3,
                "emotion": "중립", "interaction_count": 0,
                "last_seen": datetime.now().strftime("%Y-%m-%d"), "notes": []
            }
        p = self.data["people"][person]
        p["interaction_count"] += 1
        p["last_seen"] = datetime.now().strftime("%Y-%m-%d")

        if positive:
            p["trust"] = min(1.0, p["trust"] + 0.02)
            p["intimacy"] = min(1.0, p["intimacy"] + 0.03)
        else:
            p["trust"] = max(0.0, p["trust"] - 0.01)

        # 친밀도에 따른 감정
        if p["intimacy"] > 0.8: p["emotion"] = "친밀"
        elif p["intimacy"] > 0.6: p["emotion"] = "호감"
        elif p["intimacy"] > 0.4: p["emotion"] = "보통"
        else: p["emotion"] = "거리감"

        self._save()

    def get_relation(self, person: str) -> dict:
        return self.data["people"].get(person, {
            "trust": 0.5, "intimacy": 0.3, "emotion": "중립"
        })

    def get_behavior_modifier(self, person: str) -> dict:
        """사람별 행동 조정값"""
        rel = self.get_relation(person)
        return {
            "verbosity": rel["intimacy"],          # 친밀할수록 말 많이
            "formality": 1.0 - rel["intimacy"],    # 친밀할수록 반말
            "initiative": rel["trust"],             # 신뢰 높을수록 먼저 말 걸기
            "openness": rel["intimacy"],            # 친밀할수록 솔직
        }

    def get_for_prompt(self, person: str = "현승") -> str:
        rel = self.get_relation(person)
        return (
            f"{person}과의 관계: "
            f"신뢰도 {rel['trust']:.1f} / "
            f"친밀도 {rel['intimacy']:.1f} / "
            f"감정: {rel['emotion']}"
        )

social_model = SocialModel()
