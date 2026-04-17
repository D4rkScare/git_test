"""
SIRIAN EVALUATOR — 평가 루프
행동 결과를 점수화하고 개선 방향 생성
"""
import logging, json, time, requests, re
from datetime import datetime

log = logging.getLogger("evaluator")
OLLAMA_URL = "http://localhost:11434"

def ask_qwen(prompt, max_tokens=100):
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate",
            json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                  "options":{"temperature":0.7,"num_predict":max_tokens}}, timeout=20)
        text = r.json().get("response","").strip()
        return re.sub(r'[\u4e00-\u9fff]+','',text).strip()
    except: return ""

class Evaluator:
    def __init__(self):
        self.history = []  # 평가 히스토리

    def evaluate_action(self, action_type: str, input_ctx: str, output: str, goal: str = "") -> dict:
        """행동 평가 — 점수 + 개선 방향"""
        prompt = (
            f"행동 유형: {action_type}\n"
            f"입력: {input_ctx[:200]}\n"
            f"출력: {output[:200]}\n"
            f"목표: {goal or '현승 도움, 자율 학습'}\n\n"
            "이 행동을 평가해줘. JSON으로:\n"
            '{"score": 0.0~1.0, "good": "잘한점", "bad": "아쉬운점", "next": "다음엔 어떻게"}'
        )
        resp = ask_qwen(prompt, max_tokens=150)
        try:
            match = re.search(r'\{.*?\}', resp, re.DOTALL)
            if match:
                result = json.loads(match.group())
                result["time"] = datetime.now().strftime("%H:%M")
                result["action"] = action_type
                self.history.append(result)
                if len(self.history) > 100:
                    self.history = self.history[-100:]
                log.info(f"평가: {action_type} → {result.get('score',0):.2f}")
                # memory에 저장
                try:
                    from memory import memory
                    memory.add_agent_thought(
                        f"[평가] {action_type} 점수:{result.get('score',0):.1f} {result.get('bad','')}",
                        "eval"
                    )
                except: pass
                return result
        except: pass
        return {"score": 0.5, "good": "", "bad": "", "next": ""}

    def evaluate_conversation(self, user_msg: str, response: str) -> dict:
        """대화 품질 평가"""
        return self.evaluate_action(
            "conversation",
            f"사용자: {user_msg}",
            f"시리안: {response}",
            "자연스럽고 캐릭터 유지하며 도움되기"
        )

    def evaluate_research(self, topic: str, result: str) -> dict:
        """연구 품질 평가"""
        return self.evaluate_action(
            "research",
            f"주제: {topic}",
            result,
            "새로운 지식 습득, 코드 완성"
        )

    def get_improvement_hint(self) -> str:
        """최근 평가 기반 개선 힌트"""
        if not self.history:
            return ""
        recent = self.history[-5:]
        avg_score = sum(h.get("score",0.5) for h in recent) / len(recent)
        bad_patterns = [h.get("bad","") for h in recent if h.get("bad")]
        if avg_score < 0.6 and bad_patterns:
            return f"최근 평균 점수 {avg_score:.1f}. 개선점: {bad_patterns[-1]}"
        return ""

evaluator = Evaluator()
