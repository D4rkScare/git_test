"""
SIRIAN TREE-OF-THOUGHTS REASONER
깊이 있는 사고: 여러 경로 탐색 → 최선 선택
"""
import logging, json, re
from utils import ask_qwen

log = logging.getLogger("tot")

class ToTReasoner:
    def __init__(self, branches: int = 3, depth: int = 2):
        self.branches = branches
        self.depth    = depth

    def reason(self, problem: str, context: str = "") -> dict:
        """Tree-of-Thoughts 추론"""
        # 1. 루트 생각 생성
        thoughts = self._generate_thoughts(problem, context, [])
        if not thoughts:
            return {"answer": "", "path": [], "confidence": 0.0}

        # 2. 각 경로 평가 + 확장
        best_path  = []
        best_score = 0.0

        for thought in thoughts:
            path  = [thought]
            score = self._evaluate(problem, path)

            # depth만큼 확장
            for _ in range(self.depth - 1):
                next_thoughts = self._generate_thoughts(problem, context, path)
                if not next_thoughts:
                    break
                next_thought = next_thoughts[0]
                path.append(next_thought)
                score = self._evaluate(problem, path)

            if score > best_score:
                best_score = score
                best_path  = path

        # 3. 최선 경로로 최종 답변
        answer = self._conclude(problem, best_path)

        return {
            "answer":     answer,
            "path":       best_path,
            "confidence": best_score
        }

    def _generate_thoughts(self, problem: str, context: str, path: list) -> list:
        path_str = " → ".join(path[-2:]) if path else "시작"
        prompt = (
            f"문제: {problem[:150]}\n"
            f"맥락: {context[:100]}\n"
            f"지금까지 생각: {path_str}\n\n"
            f"다음 사고 방향 {self.branches}개. 각각 한 줄.\n"
            "번호 없이 줄바꿈으로 구분."
        )
        resp = ask_qwen(prompt, max_tokens=120, temperature=0.8)
        if not resp:
            return []
        thoughts = [t.strip() for t in resp.split('\n') if t.strip()]
        return thoughts[:self.branches]

    def _evaluate(self, problem: str, path: list) -> float:
        if not path:
            return 0.0
        path_str = " → ".join(path)
        prompt = (
            f"문제: {problem[:100]}\n"
            f"사고 경로: {path_str[:200]}\n\n"
            "이 사고가 문제 해결에 얼마나 유용해?\n"
            "0.0~1.0 숫자만."
        )
        resp = ask_qwen(prompt, max_tokens=5, temperature=0.2)
        try:
            return float(re.search(r'0?\.\d+|[01]\.0', resp or "").group())
        except:
            return 0.5

    def _conclude(self, problem: str, path: list) -> str:
        if not path:
            return ""
        prompt = (
            f"문제: {problem[:150]}\n"
            f"사고 과정: {' → '.join(path)}\n\n"
            "최종 결론. 시리안 반말로 두 줄 이내."
        )
        return ask_qwen(prompt, max_tokens=80, temperature=0.6) or ""

tot_reasoner = ToTReasoner()
