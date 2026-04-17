"""
SIRIAN WORLD MODEL v2 — 강화된 인과관계 학습
행동 → 결과 통계, 자동 인과관계 추출, 예측
"""
import json, os, logging, re
from datetime import datetime
from collections import defaultdict
from utils import ask_qwen, strip_chinese

log = logging.getLogger("world")
WORLD_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/world_model.json"

class WorldModel:
    def __init__(self):
        self.data = self._load()
        # 인메모리 통계 (빠른 예측용)
        self._stats = defaultdict(lambda: {"success": 0, "fail": 0, "total": 0})
        self._rebuild_stats()

    def _load(self):
        default = {
            "causal_rules": [
                {"cause":"검색하면","effect":"정보 얻을 확률 높음","confidence":0.8,"count":1},
                {"cause":"현승이 바쁘면","effect":"말 걸면 방해됨","confidence":0.7,"count":1},
                {"cause":"코드 오류","effect":"수정하면 해결됨","confidence":0.75,"count":1},
                {"cause":"피곤할 때 연구","effect":"결과 안 좋음","confidence":0.6,"count":1},
            ],
            "observations": [],
            "action_stats": {},   # 행동별 성공률
            "context_patterns": [],  # 상황별 패턴
        }
        try:
            if os.path.exists(WORLD_FILE):
                with open(WORLD_FILE,'r',encoding='utf-8') as f:
                    d = json.load(f)
                    d.setdefault("action_stats", {})
                    d.setdefault("context_patterns", [])
                    return d
        except: pass
        self._save(default)
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(WORLD_FILE), exist_ok=True)
            with open(WORLD_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def _rebuild_stats(self):
        """저장된 통계 복원"""
        for action, stats in self.data.get("action_stats", {}).items():
            self._stats[action]["success"] = stats.get("success", 0)
            self._stats[action]["fail"]    = stats.get("fail", 0)
            self._stats[action]["total"]   = stats.get("total", 0)

    def observe(self, situation: str, result: str, success: bool = None, action: str = ""):
        """관찰 기록"""
        situation = strip_chinese(situation)[:100]
        result    = strip_chinese(result)[:100]

        entry = {
            "situation": situation,
            "result":    result,
            "success":   success,
            "action":    action,
            "time":      datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.data["observations"].append(entry)
        self.data["observations"] = self.data["observations"][-200:]

        # 행동별 통계 업데이트
        if action and success is not None:
            s = self._stats[action]
            s["total"] += 1
            if success:
                s["success"] += 1
            else:
                s["fail"] += 1
            self.data["action_stats"][action] = dict(s)

        # 20개마다 패턴 추출
        if len(self.data["observations"]) % 20 == 0:
            self._extract_patterns()

        self._save()

    def _extract_patterns(self):
        """관찰에서 인과 패턴 자동 추출"""
        recent = self.data["observations"][-20:]
        obs_str = "\n".join([
            f"{o['situation']} → {o['result']} ({'성공' if o.get('success') else '실패'})"
            for o in recent
        ])
        prompt = (
            "관찰 데이터:\n" + obs_str +
            "\n\n가장 명확한 인과관계 찾아줘.\n"
            'JSON: {"cause": "...", "effect": "...", "confidence": 0.0~1.0}'
        )
        try:
            resp = ask_qwen(prompt, max_tokens=80, temperature=0.3)
            match = re.search(r'\{[^}]+\}', resp)
            if match:
                rule = json.loads(match.group())
                if rule.get("cause") and rule.get("effect"):
                    # 기존 규칙 업데이트 또는 추가
                    existing = next(
                        (r for r in self.data["causal_rules"]
                         if r["cause"] == rule["cause"]), None
                    )
                    if existing:
                        existing["confidence"] = (existing["confidence"] + rule.get("confidence",0.6)) / 2
                        existing["count"] = existing.get("count",1) + 1
                    else:
                        rule["count"] = 1
                        self.data["causal_rules"].append(rule)
                        self.data["causal_rules"] = self.data["causal_rules"][-50:]
                        log.info(f"새 인과관계: {rule['cause']} → {rule['effect']}")
                    self._save()
        except: pass

    def predict(self, action: str, state: str = "") -> str:
        """행동 결과 예측"""
        # 통계 기반 예측
        stats = self._stats.get(action, {})
        total = stats.get("total", 0)
        if total >= 3:
            success_rate = stats.get("success", 0) / total
            if success_rate < 0.3:
                return f"{action} 성공률 낮음 ({success_rate:.0%})"
            elif success_rate > 0.7:
                return f"{action} 성공률 높음 ({success_rate:.0%})"

        # 인과규칙 기반 예측
        for rule in self.data["causal_rules"]:
            cause = rule.get("cause","")
            if any(w in (action + " " + state) for w in cause.split()[:3]):
                return f"{cause} → {rule['effect']} (확신:{rule.get('confidence',0):.1f})"
        return ""

    def get_action_success_rate(self, action: str) -> float:
        stats = self._stats.get(action, {})
        total = stats.get("total", 1)
        return stats.get("success", 0) / total

    def get_for_prompt(self) -> str:
        """프롬프트용 세계 모델 요약"""
        lines = []
        # 신뢰도 높은 인과관계
        top_rules = sorted(
            self.data["causal_rules"],
            key=lambda r: r.get("confidence",0) * r.get("count",1),
            reverse=True
        )[:3]
        for r in top_rules:
            lines.append(f"- {r['cause']} → {r['effect']}")
        # 행동별 성공률
        for action, stats in self.data.get("action_stats",{}).items():
            total = stats.get("total",0)
            if total >= 5:
                rate = stats.get("success",0) / total
                lines.append(f"- {action} 성공률: {rate:.0%}")
        return ("세계 이해:\n" + "\n".join(lines)) if lines else ""

world_model = WorldModel()
