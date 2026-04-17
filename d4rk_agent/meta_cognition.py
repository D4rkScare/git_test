"""
SIRIAN META COGNITION — 메타 인지
왜 잘했는지 / 왜 실패했는지 분석 → 전략 수정
"""
import json, os, logging, requests, re
from utils import ask_qwen, clean_response, strip_chinese
from datetime import datetime

log = logging.getLogger("meta")
META_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/meta_cognition.json"

class MetaCognition:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "analyses": [],
            "strategies": {
                "chat": "현승 말에 공감하고 짧게 핵심만",
                "research": "코드 먼저 짜고 실행하면서 개선",
                "sns": "다양한 주제로 짧게",
            },
            "improvement_notes": []
        }
        try:
            if os.path.exists(META_FILE):
                with open(META_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(META_FILE), exist_ok=True)
            with open(META_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def analyze(self, action: str, context: str, result: str, score: float):
        """행동 분석 — 왜 잘했는지/실패했는지"""
        if abs(score - 0.5) < 0.15:
            return  # 평범한 결과는 스킵

        outcome = "성공" if score > 0.65 else "실패"
        prompt = (
            f"시리안 레인이야.\n"
            f"행동: {action}\n"
            f"상황: {context[:100]}\n"
            f"결과: {result[:100]}\n"
            f"점수: {score:.2f} ({outcome})\n\n"
            f"왜 {outcome}했어? 한 줄로. 다음엔 어떻게 하면 좋을지도."
        )
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"num_predict":80,"temperature":0.6}},
                timeout=15
            )
            analysis = resp.json().get("response","").strip()
            analysis = re.sub(r'[\u4e00-\u9fff]+','',analysis).strip()
            if not analysis: return

            entry = {
                "action": action, "outcome": outcome,
                "score": score, "analysis": analysis[:200],
                "time": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            self.data["analyses"].append(entry)
            self.data["analyses"] = self.data["analyses"][-50:]

            # 전략 업데이트
            if score > 0.8:
                self._update_strategy(action, analysis, positive=True)
            elif score < 0.3:
                self._update_strategy(action, analysis, positive=False)

            self._save()
            log.info(f"메타 분석({outcome}): {analysis[:60]}")
        except: pass

    def _update_strategy(self, action: str, analysis: str, positive: bool):
        """전략 업데이트"""
        if positive:
            note = f"[성공 패턴] {action}: {analysis[:100]}"
        else:
            note = f"[실패 회피] {action}: {analysis[:100]}"
        self.data["improvement_notes"].append(note)
        self.data["improvement_notes"] = self.data["improvement_notes"][-20:]

        # 현재 전략도 업데이트
        if positive and action in self.data["strategies"]:
            self.data["strategies"][action] = analysis[:100]

    def get_strategy(self, action: str) -> str:
        return self.data["strategies"].get(action, "")

    def get_for_prompt(self) -> str:
        notes = self.data["improvement_notes"][-3:]
        if not notes: return ""
        return "자기 개선 메모:\n" + "\n".join(notes)

meta_cognition = MetaCognition()
