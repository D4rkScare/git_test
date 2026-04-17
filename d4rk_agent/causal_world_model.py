"""
SIRIAN CAUSAL WORLD MODEL — 인과관계 학습 강화
"이 행동 → 이런 결과 확률" 자동 모델링
"""
import json, os, logging, re
from datetime import datetime
from collections import defaultdict
from utils import ask_qwen, strip_chinese

log = logging.getLogger("causal")
CAUSAL_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/causal_model.json"

class CausalWorldModel:
    def __init__(self):
        self.data = self._load()
        # (action, context) → [results] 인메모리 통계
        self._stats = defaultdict(list)
        self._rebuild()

    def _load(self):
        default = {
            "causal_graph": [],     # 인과 관계 노드
            "observations":  [],    # 원시 관찰 데이터
            "predictions":   [],    # 예측 기록
            "accuracy":      0.5,   # 예측 정확도
        }
        try:
            if os.path.exists(CAUSAL_FILE):
                with open(CAUSAL_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(CAUSAL_FILE), exist_ok=True)
            with open(CAUSAL_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def _rebuild(self):
        for obs in self.data.get("observations", []):
            key = (obs.get("action",""), obs.get("context","")[:20])
            self._stats[key].append(obs.get("success", False))

    def observe(self, action: str, context: str, result: str, success: bool):
        """관찰 기록 + 인과관계 자동 추출"""
        obs = {
            "action":  action,
            "context": context[:80],
            "result":  result[:80],
            "success": success,
            "time":    datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.data["observations"].append(obs)
        self.data["observations"] = self.data["observations"][-500:]

        key = (action, context[:20])
        self._stats[key].append(success)

        # 10개 쌓이면 인과관계 추출
        if len(self.data["observations"]) % 10 == 0:
            self._extract_causal()
        self._save()

    def _extract_causal(self):
        """관찰에서 인과관계 자동 추출"""
        recent = self.data["observations"][-20:]
        obs_str = "\n".join([
            f"행동:{o['action']} 상황:{o['context'][:30]} → "
            f"{'성공' if o['success'] else '실패'}: {o['result'][:40]}"
            for o in recent
        ])
        prompt = (
            "관찰 데이터:\n" + obs_str + "\n\n"
            "가장 명확한 인과관계 2개를 찾아줘.\n"
            'JSON 리스트: [{"cause":"...", "effect":"...", '
            '"probability":0.0~1.0, "condition":"..."}]'
        )
        try:
            resp = ask_qwen(prompt, max_tokens=150, temperature=0.3)
            match = re.search(r'\[.*?\]', resp, re.DOTALL)
            if match:
                rules = json.loads(match.group())
                for rule in rules:
                    if rule.get("cause") and rule.get("effect"):
                        # 기존 업데이트 또는 추가
                        existing = next(
                            (r for r in self.data["causal_graph"]
                             if r["cause"] == rule["cause"]), None
                        )
                        if existing:
                            existing["probability"] = (
                                existing["probability"] * 0.7 +
                                rule.get("probability", 0.5) * 0.3
                            )
                            existing["count"] = existing.get("count",1) + 1
                        else:
                            rule["count"] = 1
                            self.data["causal_graph"].append(rule)

                self.data["causal_graph"] = self.data["causal_graph"][-100:]
                self._save()
                log.info(f"인과관계 {len(rules)}개 업데이트")
        except: pass

    def predict(self, action: str, context: str) -> dict:
        """행동 결과 예측"""
        # 통계 기반
        key = (action, context[:20])
        stats = self._stats.get(key, [])
        if len(stats) >= 3:
            prob = sum(stats) / len(stats)
            return {
                "action": action,
                "success_prob": prob,
                "basis": "통계",
                "count": len(stats)
            }

        # 인과그래프 기반
        for rule in self.data["causal_graph"]:
            cause = rule.get("cause","")
            if any(w in (action + " " + context) for w in cause.split()[:3]):
                return {
                    "action": action,
                    "success_prob": rule.get("probability", 0.5),
                    "effect": rule.get("effect",""),
                    "basis": "인과",
                    "condition": rule.get("condition","")
                }

        return {"action": action, "success_prob": 0.5, "basis": "기본"}

    def verify_prediction(self, action: str, context: str, actual_success: bool):
        """예측 정확도 업데이트"""
        pred = self.predict(action, context)
        pred_success = pred["success_prob"] > 0.5
        correct = pred_success == actual_success
        # 지수 이동 평균
        self.data["accuracy"] = (
            self.data["accuracy"] * 0.9 + (1.0 if correct else 0.0) * 0.1
        )
        self.data["predictions"].append({
            "action": action,
            "predicted": pred_success,
            "actual": actual_success,
            "correct": correct,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        self.data["predictions"] = self.data["predictions"][-100:]
        self._save()

    def get_for_prompt(self) -> str:
        lines = []
        top = sorted(
            self.data["causal_graph"],
            key=lambda r: r.get("probability",0) * r.get("count",1),
            reverse=True
        )[:4]
        for r in top:
            lines.append(
                f"- {r['cause']} → {r['effect']} "
                f"(확률:{r.get('probability',0.5):.0%})"
            )
        acc = self.data.get("accuracy", 0.5)
        lines.append(f"예측 정확도: {acc:.0%}")
        return "인과 모델:\n" + "\n".join(lines) if lines else ""

causal_world_model = CausalWorldModel()
