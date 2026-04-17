"""
SIRIAN META LAYER — 자기 인식 + 전략 조정
"내가 지금 잘하고 있는가?" 스스로 판단
"""
import json, os, logging, threading, time
from datetime import datetime
from utils import ask_qwen

log = logging.getLogger("meta_layer")
META_LAYER_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/meta_layer.json"

class MetaLayer:
    def __init__(self):
        self.data    = self._load()
        self._lock   = threading.Lock()

    def _load(self):
        default = {
            "evaluations": [],
            "current_strategy": "",
            "performance_trend": [],
            "adjustment_count": 0
        }
        try:
            if os.path.exists(META_LAYER_FILE):
                with open(META_LAYER_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(META_LAYER_FILE), exist_ok=True)
            with open(META_LAYER_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def evaluate_cycle(self, state: dict, action: str,
                       result_score: float, reflection: str) -> dict:
        """사이클 평가 + 전략 조정"""
        with self._lock:
            eval_entry = {
                "time":       datetime.now().strftime("%H:%M"),
                "action":     action,
                "score":      result_score,
                "reflection": reflection[:100],
            }
            self.data["evaluations"].append(eval_entry)
            self.data["evaluations"] = self.data["evaluations"][-50:]

            # 성능 추세
            recent_scores = [e["score"] for e in self.data["evaluations"][-10:]]
            avg = sum(recent_scores) / max(len(recent_scores),1)
            self.data["performance_trend"].append(round(avg, 2))
            self.data["performance_trend"] = self.data["performance_trend"][-20:]

            # 전략 조정 필요 여부
            adjustment = self._check_adjustment(avg, action, result_score)
            if adjustment:
                self.data["adjustment_count"] += 1
                self.data["current_strategy"] = adjustment
                log.info(f"전략 조정: {adjustment[:50]}")

            self._save()
            return {
                "avg_score":  avg,
                "adjustment": adjustment,
                "trend":      self._get_trend()
            }

    def _check_adjustment(self, avg: float, action: str, score: float) -> str:
        """전략 조정이 필요한지 판단"""
        # 최근 5개 중 3개 이상 실패
        recent = self.data["evaluations"][-5:]
        fail_count = sum(1 for e in recent if e["score"] < 0.4)

        if fail_count >= 3:
            prompt = (
                f"최근 행동 평균 점수: {avg:.2f}\n"
                f"실패 횟수: {fail_count}/5\n"
                f"마지막 행동: {action} ({score:.2f})\n\n"
                "전략 어떻게 바꿔야 해? 한 줄로."
            )
            return ask_qwen(prompt, max_tokens=50, temperature=0.5) or ""

        return ""

    def _get_trend(self) -> str:
        trend = self.data["performance_trend"]
        if len(trend) < 3: return "측정중"
        recent = trend[-3:]
        if recent[-1] > recent[0] + 0.05: return "상승"
        if recent[-1] < recent[0] - 0.05: return "하락"
        return "안정"

    def self_check(self, context: str) -> str:
        """자기 인식 — "내가 지금 잘하고 있나?" """
        trend = self._get_trend()
        avg = self.data["performance_trend"][-1] if self.data["performance_trend"] else 0.5
        prompt = (
            f"상황: {context[:100]}\n"
            f"최근 성능 추세: {trend} (평균:{avg:.2f})\n"
            f"현재 전략: {self.data['current_strategy'][:80]}\n\n"
            "시리안 레인이야. 지금 내가 잘하고 있어? 한 줄 자기 평가. 반말로."
        )
        return ask_qwen(prompt, max_tokens=40, temperature=0.7) or ""

    def get_for_prompt(self) -> str:
        trend    = self._get_trend()
        strategy = self.data.get("current_strategy","")
        if not strategy and not trend: return ""
        parts = []
        if strategy: parts.append(f"현재 전략: {strategy[:60]}")
        parts.append(f"성능 추세: {trend}")
        return "\n".join(parts)

meta_layer = MetaLayer()
