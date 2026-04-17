"""
SIRIAN STRATEGY LIBRARY — 전략 저장소
과거 성공 전략을 벡터로 저장 + 자동 검색
"""
import json, os, logging, re
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("strategy")
STRATEGY_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/strategy_library.json"

class StrategyLibrary:
    def __init__(self):
        self.data = self._load()
        self._vec_model = None
        self._init_vector()

    def _load(self):
        default = {
            "strategies": [],    # 성공 전략
            "procedures": [],    # 절차 기억 (단계별 방법)
            "avoid_list": [],    # 실패 패턴
        }
        try:
            if os.path.exists(STRATEGY_FILE):
                with open(STRATEGY_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(STRATEGY_FILE), exist_ok=True)
            with open(STRATEGY_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def _init_vector(self):
        try:
            from utils import get_sentence_model
            self._vec_model = get_sentence_model()
            log.info("Strategy Library 벡터 모드")
        except:
            log.debug("Strategy Library 키워드 모드")

    def _encode(self, text: str):
        if self._vec_model:
            return self._vec_model.encode([text])[0].tolist()
        return None

    def add_strategy(self, action: str, situation: str,
                     strategy: str, score: float, steps: list = None):
        """성공 전략 저장"""
        if score < 0.65: return
        entry = {
            "action":    action,
            "situation": situation[:100],
            "strategy":  strategy[:200],
            "steps":     steps or [],
            "score":     score,
            "time":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "use_count": 0
        }
        vec = self._encode(situation + " " + strategy)
        if vec:
            entry["vector"] = vec

        self.data["strategies"].append(entry)
        self.data["strategies"] = self.data["strategies"][-200:]
        self._save()
        log.info(f"전략 저장: {action} | {strategy[:50]}")

    def add_procedure(self, topic: str, steps: list, result: str):
        """절차 기억 저장 (예: XSS 테스트 방법)"""
        entry = {
            "topic":  topic[:100],
            "steps":  steps[:10],
            "result": result[:100],
            "time":   datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.data["procedures"].append(entry)
        self.data["procedures"] = self.data["procedures"][-100:]
        self._save()

    def add_avoid(self, action: str, situation: str, reason: str):
        """실패 패턴 등록"""
        entry = {
            "action":    action,
            "situation": situation[:100],
            "reason":    reason[:100],
            "time":      datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.data["avoid_list"].append(entry)
        self.data["avoid_list"] = self.data["avoid_list"][-50:]
        self._save()

    def search(self, query: str, action: str = "", top_k: int = 3) -> list:
        """상황에 맞는 전략 검색
        semantic similarity + score + recency 종합
        """
        candidates = self.data.get("strategies", [])
        if action:
            candidates = [s for s in candidates if s.get("action") == action] or candidates

        if not candidates: return []

        scored = []
        q_vec = self._encode(query)

        for s in candidates:
            sim = 0.5
            # 벡터 유사도
            if q_vec and "vector" in s:
                import numpy as np
                v = np.array(s["vector"])
                q = np.array(q_vec)
                sim = float(np.dot(q,v) / (np.linalg.norm(q)*np.linalg.norm(v)+1e-9))
            else:
                # 키워드 매칭
                words = set(query.lower().split())
                sit_words = set(s.get("situation","").lower().split())
                sim = len(words & sit_words) / max(len(words), 1) * 0.5

            # 최신성 가중치
            try:
                from datetime import datetime as dt
                t = dt.strptime(s["time"], "%Y-%m-%d %H:%M")
                days = (dt.now() - t).days
                recency = max(0, 1 - days/30)
            except:
                recency = 0.5

            # 점수 = 유사도 0.5 + 성공점수 0.3 + 최신성 0.2
            final = sim * 0.5 + s.get("score",0.5) * 0.3 + recency * 0.2
            scored.append((final, s))

        scored.sort(reverse=True)
        results = [s for _, s in scored[:top_k]]

        # 사용 횟수 증가
        for s in results:
            s["use_count"] = s.get("use_count",0) + 1
        self._save()

        return results

    def get_for_prompt(self, query: str, action: str = "") -> str:
        """프롬프트용 전략 요약"""
        strategies = self.search(query, action, top_k=3)
        avoid = [a for a in self.data.get("avoid_list",[])
                if not action or a.get("action") == action][-2:]

        lines = []
        if strategies:
            lines.append("📌 성공 전략:")
            for s in strategies:
                lines.append(f"  - [{s['action']}] {s['strategy'][:80]}")
        if avoid:
            lines.append("⚠️ 피할 것:")
            for a in avoid:
                lines.append(f"  - {a['reason'][:60]}")

        return "\n".join(lines) if lines else ""

    def auto_extract_from_researcher(self, topic: str, notes: list):
        """연구 결과에서 절차 기억 자동 추출"""
        if len(notes) < 2: return
        notes_str = json.dumps(notes[-5:], ensure_ascii=False)[:400]
        prompt = (
            f"주제: {topic}\n연구 노트:\n{notes_str}\n\n"
            "이 연구에서 다음에 재사용할 수 있는 절차 있어? "
            'JSON: {"steps": ["단계1", "단계2", ...]} 또는 null'
        )
        result = ask_qwen(prompt, max_tokens=100, temperature=0.4)
        try:
            match = re.search(r'\{[^}]+\}', result, re.DOTALL)
            if match:
                data = json.loads(match.group())
                steps = data.get("steps",[])
                if steps:
                    self.add_procedure(topic, steps, f"{len(notes)}번 시도")
        except: pass

strategy_library = StrategyLibrary()
