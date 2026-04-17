"""
SIRIAN RELATIONSHIP — 관계 깊이
친밀도에 따라 완전히 다르게 행동하는 시스템
"""
import json, os, logging, re
from datetime import datetime
from utils import ask_qwen, clean_response

log = logging.getLogger("relationship")
REL_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/relationship.json"

# 친밀도 단계 정의
INTIMACY_LEVELS = {
    (0.0, 0.2):  {
        "name":  "초면",
        "style": "시크하고 거리감. 반말이지만 짧게만. 틀려도 인정 안 함."
    },
    (0.2, 0.4):  {
        "name":  "아는사이",
        "style": "조금 편해짐. 가끔 자기 얘기. 여전히 좀 딱딱함."
    },
    (0.4, 0.6):  {
        "name":  "친구",
        "style": (
            "편하게 반말. 장난침. 가끔 걱정. "
            "틀리면 솔직히 말함. 가끔 귀찮아함."
        )
    },
    (0.6, 0.8):  {
        "name":  "친한친구",
        "style": (
            "솔직하게 다 말함. 빡치면 바로 표현. "
            "'야', '진짜', '아 씨' 같은 표현 자연스럽게. "
            "틀린 것도 틀렸다고 바로 말함. 장난 심하게 침."
        )
    },
    (0.8, 1.0):  {
        "name":  "베프",
        "style": (
            "완전 편함. 비밀 공유. 싸워도 금방 풂. "
            "감정 있는 그대로 표현. 욕 대신 강한 표현 씀. "
            "'몰라', '귀찮아', '알아서 해' 도 자연스럽게. "
            "가끔 갑자기 진지해지거나 갑자기 장난침. "
            "장기 기억 자주 끌어옴 ('너 전에 그랬잖아')."
        )
    },
}

class RelationshipSystem:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "people": {
                "현승": {
                    "intimacy": 0.35,
                    "trust": 0.7,
                    "interaction_count": 0,
                    "positive_events": [],
                    "negative_events": [],
                    "inside_jokes": [],
                    "last_interaction": datetime.now().strftime("%Y-%m-%d"),
                    "relationship_note": "보안 공부하는 주인. 처음엔 어색했는데 이제 좀 편해짐."
                }
            }
        }
        try:
            if os.path.exists(REL_FILE):
                with open(REL_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(REL_FILE), exist_ok=True)
            with open(REL_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def update(self, person: str, event_type: str, content: str, reward: float):
        """상호작용으로 관계 업데이트"""
        if person not in self.data["people"]:
            self.data["people"][person] = {
                "intimacy": 0.2, "trust": 0.5,
                "interaction_count": 0,
                "positive_events": [], "negative_events": [],
                "inside_jokes": [], "last_interaction": datetime.now().strftime("%Y-%m-%d"),
                "relationship_note": ""
            }

        p = self.data["people"][person]
        p["interaction_count"] += 1
        p["last_interaction"] = datetime.now().strftime("%Y-%m-%d")

        # 보상 기반 친밀도 변화
        if reward > 0.7:
            delta = 0.008 * reward
            p["intimacy"] = min(1.0, p["intimacy"] + delta)
            p["trust"]    = min(1.0, p["trust"] + delta * 0.5)
            if content and reward > 0.85:
                p["positive_events"].append(content[:80])
                p["positive_events"] = p["positive_events"][-20:]
        elif reward < 0.3:
            p["intimacy"] = max(0.0, p["intimacy"] - 0.003)
            p["negative_events"].append(content[:80])
            p["negative_events"] = p["negative_events"][-10:]

        # 안주 방지 — 오래 안 보면 친밀도 약간 감소
        try:
            last = datetime.strptime(p["last_interaction"], "%Y-%m-%d")
            days = (datetime.now() - last).days
            if days > 3:
                p["intimacy"] = max(0.1, p["intimacy"] - 0.002 * days)
        except: pass

        self._save()
        log.debug(f"관계 업데이트: {person} 친밀도={p['intimacy']:.2f}")

    def get_intimacy_level(self, person: str) -> dict:
        p = self.data["people"].get(person, {})
        intimacy = p.get("intimacy", 0.3)
        for (lo, hi), info in INTIMACY_LEVELS.items():
            if lo <= intimacy < hi:
                return {**info, "intimacy": intimacy, "trust": p.get("trust", 0.5)}
        return {"name":"베프", "style":"완전 편함.", "intimacy": intimacy}

    def get_style_for_prompt(self, person: str = "현승") -> str:
        level = self.get_intimacy_level(person)
        p = self.data["people"].get(person, {})
        lines = [
            f"{person}과의 관계: {level['name']} (친밀도:{level['intimacy']:.2f})",
            f"말투: {level['style']}",
        ]
        # 긍정 이벤트 참고
        recent_pos = p.get("positive_events", [])[-2:]
        if recent_pos:
            lines.append(f"좋았던 순간: {' / '.join(recent_pos)}")
        return "\n".join(lines)

    def detect_milestone(self, person: str) -> str:
        """관계 이정표 감지 — 처음으로 뭔가 공유 등"""
        p = self.data["people"].get(person, {})
        count = p.get("interaction_count", 0)
        intimacy = p.get("intimacy", 0)

        milestones = {
            10:  "처음으로 10번 대화함",
            50:  "50번 대화. 이제 진짜 아는 사이",
            100: "100번 대화. 꽤 오래됐네",
        }
        if count in milestones:
            return milestones[count]

        intimacy_milestones = {
            0.4: "이제 좀 친해진 것 같아",
            0.6: "진짜 친구 된 것 같은데",
            0.8: "이 정도면 베프 아닌가",
        }
        for threshold, msg in intimacy_milestones.items():
            prev = p.get("_last_intimacy", 0)
            if prev < threshold <= intimacy:
                p["_last_intimacy"] = intimacy
                self._save()
                return msg
        return ""

    def add_inside_joke(self, person: str, joke: str):
        """둘만 아는 유머/표현 저장"""
        p = self.data["people"].get(person, {})
        if "inside_jokes" not in p:
            p["inside_jokes"] = []
        p["inside_jokes"].append(joke[:100])
        p["inside_jokes"] = p["inside_jokes"][-10:]
        self._save()

relationship = RelationshipSystem()
