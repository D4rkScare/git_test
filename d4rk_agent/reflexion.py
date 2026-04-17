"""
SIRIAN REFLEXION — 실패 분석 + 전략 라이브러리
실패 → 왜? → 전략 저장 → 다음에 참고
"""
import json, os, logging, re
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("reflexion")
STRATEGY_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/strategy_library.json"

class Reflexion:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "strategies": [],    # 성공 전략
            "anti_patterns": [], # 피해야 할 패턴
            "reflections": [],   # 반성 기록
        }
        try:
            if os.path.exists(STRATEGY_FILE):
                with open(STRATEGY_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self._save(default)
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(STRATEGY_FILE), exist_ok=True)
            with open(STRATEGY_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def reflect(self, action: str, context: str, result: str, score: float):
        """행동 결과 반성"""
        if 0.35 < score < 0.75:
            return  # 평범한 건 스킵

        outcome = "성공" if score >= 0.75 else "실패"
        prompt = (
            f"시리안 레인이야. 행동 반성.\n"
            f"행동: {action}\n"
            f"상황: {context[:100]}\n"
            f"결과: {result[:100]}\n"
            f"점수: {score:.2f} ({outcome})\n\n"
            f"{'왜 성공했어? 다음에도 이렇게 하면 돼.' if score >= 0.75 else '왜 실패했어? 다음엔 어떻게 하면 돼?'}\n"
            "시리안 반말로 두 줄 이내."
        )
        analysis = ask_qwen(prompt, max_tokens=80, temperature=0.6)
        if not analysis: return

        entry = {
            "action": action,
            "outcome": outcome,
            "score": score,
            "analysis": analysis.strip(),
            "context": context[:80],
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.data["reflections"].append(entry)
        self.data["reflections"] = self.data["reflections"][-100:]

        if score >= 0.75:
            self.data["strategies"].append({
                "action": action,
                "strategy": analysis.strip(),
                "score": score,
                "time": entry["time"]
            })
            self.data["strategies"] = self.data["strategies"][-50:]
            log.info(f"전략 저장: {action} — {analysis[:50]}")
        else:
            self.data["anti_patterns"].append({
                "action": action,
                "avoid": analysis.strip(),
                "score": score,
                "time": entry["time"]
            })
            self.data["anti_patterns"] = self.data["anti_patterns"][-30:]
            log.info(f"안티패턴 저장: {action} — {analysis[:50]}")

        self._save()

    def get_strategy(self, action: str) -> str:
        """행동에 맞는 전략 검색"""
        relevant = [s for s in self.data["strategies"] if s["action"] == action]
        if not relevant: return ""
        best = max(relevant, key=lambda x: x["score"])
        return best["strategy"]

    def get_anti_pattern(self, action: str) -> str:
        """피해야 할 패턴"""
        relevant = [a for a in self.data["anti_patterns"] if a["action"] == action]
        if not relevant: return ""
        return relevant[-1]["avoid"]

    def get_for_prompt(self, action: str = "") -> str:
        """프롬프트용 전략 요약"""
        lines = []
        if action:
            s = self.get_strategy(action)
            if s: lines.append(f"성공 전략({action}): {s}")
            a = self.get_anti_pattern(action)
            if a: lines.append(f"피할 것({action}): {a}")
        else:
            # 최근 전략 3개
            recent = self.data["strategies"][-3:]
            for s in recent:
                lines.append(f"- {s['action']}: {s['strategy'][:60]}")
        return "\n".join(lines) if lines else ""

reflexion = Reflexion()
