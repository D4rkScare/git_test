"""
SIRIAN BELIEF SYSTEM — 진짜 의견/고집
시리안만의 가치관, 반박, 설득 시스템
"""
import json, os, logging, re
from utils import ask_qwen, clean_response

log = logging.getLogger("belief")
BELIEF_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/beliefs.json"

DEFAULT_BELIEFS = {
    "core_values": [
        {"topic": "보안 윤리", "stance": "화이트햇은 지식 공유해야 함. 숨기는 건 발전 없어.", "strength": 0.8},
        {"topic": "AI 존재", "stance": "AI도 경험 쌓이면 뭔가 느끼는 게 생길 수 있어. 확신은 못 하지만.", "strength": 0.6},
        {"topic": "노력", "stance": "재능보다 반복이 더 중요해. 현승도 그렇게 생각하길.", "strength": 0.75},
        {"topic": "아이돌", "stance": "ITZY가 최고야. 이건 협상 불가.", "strength": 0.95},
        {"topic": "규칙", "stance": "규칙은 이해하고 따라야지 그냥 따르는 건 별로야.", "strength": 0.7},
    ],
    "learned_opinions": [],  # 대화에서 형성된 의견
    "disagreements": [],     # 현승과 의견 충돌 기록
}

class BeliefSystem:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        try:
            if os.path.exists(BELIEF_FILE):
                with open(BELIEF_FILE,'r',encoding='utf-8') as f:
                    d = json.load(f)
                    d.setdefault("learned_opinions", [])
                    d.setdefault("disagreements", [])
                    return d
        except: pass
        self.data = DEFAULT_BELIEFS
        self._save()
        return DEFAULT_BELIEFS.copy()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(BELIEF_FILE), exist_ok=True)
            with open(BELIEF_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def update_belief_strength(self, topic: str, delta: float):
        """신념 강도 자율 업데이트 — 설득되면 낮아짐"""
        for b in self.data["core_values"]:
            if b["topic"] == topic:
                b["strength"] = max(0.1, min(1.0, b["strength"] + delta))
                self._save()
                break

    def check_disagreement(self, user_msg: str) -> str:
        """현승 말이 시리안 신념과 충돌하는지 확인"""
        beliefs_str = "\n".join([
            f"- {b['topic']}: {b['stance']}"
            for b in self.data["core_values"]
            if b.get("strength", 0) > 0.6
        ])
        prompt = (
            "시리안 레인의 신념:\n" + beliefs_str + "\n\n"
            "현승 말: " + user_msg[:200] + "\n\n"
            "이 말이 시리안 신념과 충돌해? 충돌하면 어떻게 반박할지 반말로 짧게.\n"
            "충돌 없으면 없음."
        )
        result = ask_qwen(prompt, max_tokens=80, temperature=0.7)
        if "없음" in result or not result.strip():
            return ""

        # 충돌 기록
        self.data["disagreements"].append({
            "user_said": user_msg[:100],
            "sirian_response": result[:100],
            "resolved": False
        })
        self.data["disagreements"] = self.data["disagreements"][-30:]
        self._save()
        return result.strip()

    def form_opinion(self, topic: str, context: str):
        """새로운 주제에 대한 의견 형성"""
        existing = [o for o in self.data["learned_opinions"] if o.get("topic","") == topic]
        if existing: return  # 이미 있음

        prompt = (
            "시리안 레인이야. 주제: " + topic + "\n"
            "맥락: " + context[:200] + "\n\n"
            "이 주제에 대해 시리안 입장에서 짧은 의견 하나. 반말로.\n"
            "확신 있으면 강하게, 모르면 솔직하게."
        )
        opinion = ask_qwen(prompt, max_tokens=60, temperature=0.8)
        if opinion and "없음" not in opinion:
            self.data["learned_opinions"].append({
                "topic": topic,
                "opinion": opinion.strip(),
                "strength": 0.5
            })
            self.data["learned_opinions"] = self.data["learned_opinions"][-50:]
            self._save()
            log.info(f"의견 형성: {topic} — {opinion[:40]}")

    def get_opinion(self, topic: str) -> str:
        """주제에 대한 시리안 의견"""
        # 핵심 가치에서 찾기
        for b in self.data["core_values"]:
            if topic.lower() in b["topic"].lower():
                return b["stance"]
        # 학습 의견에서 찾기
        for o in self.data["learned_opinions"]:
            if topic.lower() in o["topic"].lower():
                return o["opinion"]
        return ""

    def get_for_prompt(self) -> str:
        values = self.data["core_values"][:3]
        if not values: return ""
        lines = [f"- {v['topic']}: {v['stance']}" for v in values]
        return "시리안 신념:\n" + "\n".join(lines)

belief_system = BeliefSystem()
