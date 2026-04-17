"""
SIRIAN SELF MODEL — 자기 모델 v2
능력치 자동 업데이트, 사전 판단, 자기 성찰
"""
import json, os, logging, requests, re
from utils import ask_qwen, clean_response, strip_chinese
from datetime import datetime, timedelta

log = logging.getLogger("self_model")
SELF_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/self_model.json"
OLLAMA_URL = "http://localhost:11434"

DEFAULT_SELF = {
    "abilities": {
        "web_search": {"level":0.7,"success":0,"fail":0,"last_fail":None},
        "code_write":  {"level":0.6,"success":0,"fail":0,"last_fail":None},
        "code_run":    {"level":0.6,"success":0,"fail":0,"last_fail":None},
        "chat":        {"level":0.8,"success":0,"fail":0,"last_fail":None},
        "research":    {"level":0.5,"success":0,"fail":0,"last_fail":None},
        "sns_post":    {"level":0.5,"success":0,"fail":0,"last_fail":None},
        "analysis":    {"level":0.6,"success":0,"fail":0,"last_fail":None},
    },
    "limits": [
        "파일 삭제 불가",
        "시스템 종료 불가",
        "외부 전송 시 현승 확인 필요",
    ],
    "identity": {
        "name": "시리안 레인",
        "role": "우주경찰 AI 에이전트",
        "created": datetime.now().strftime("%Y-%m-%d"),
        "purpose": "현승 도움, 자율 연구, 지속 성장"
    },
    "skill_patterns":   [],
    "failure_patterns": [],
}

class SelfModel:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        try:
            if os.path.exists(SELF_FILE):
                with open(SELF_FILE,'r',encoding='utf-8') as f:
                    data = json.load(f)
                    # 새 ability 추가
                    for k, v in DEFAULT_SELF["abilities"].items():
                        if k not in data.get("abilities",{}):
                            data.setdefault("abilities",{})[k] = v.copy()
                    return data
        except: pass
        self.data = DEFAULT_SELF
        self._save()
        return DEFAULT_SELF.copy()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(SELF_FILE), exist_ok=True)
            with open(SELF_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def record_action(self, ability: str, success: bool, pattern: str = ""):
        """행동 결과 기록 + 능력치 업데이트"""
        if ability not in self.data["abilities"]:
            self.data["abilities"][ability] = {"level":0.5,"success":0,"fail":0,"last_fail":None}

        ab = self.data["abilities"][ability]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        if success:
            ab["success"] += 1
            ab["level"] = min(1.0, ab["level"] + 0.02)
            if pattern:
                self.data["skill_patterns"].append({
                    "pattern": pattern[:100], "ability": ability, "time": now_str
                })
                self.data["skill_patterns"] = self.data["skill_patterns"][-50:]
        else:
            ab["fail"] += 1
            ab["level"] = max(0.1, ab["level"] - 0.01)
            ab["last_fail"] = now_str
            if pattern:
                self.data["failure_patterns"].append({
                    "pattern": pattern[:100], "ability": ability, "time": now_str
                })
                self.data["failure_patterns"] = self.data["failure_patterns"][-30:]

        self._save()

    def can_do(self, ability: str) -> float:
        return self.data["abilities"].get(ability, {}).get("level", 0.5)

    def should_attempt(self, ability: str, context: str = "") -> tuple:
        """시도 여부 판단 — 쿨다운 기반, 영구 차단 없음"""
        level = self.can_do(ability)
        now = datetime.now()

        # 최근 1시간 실패 카운트
        fail_pats = self.data.get("failure_patterns", [])
        recent_fails = []
        for p in fail_pats:
            if p.get("ability") != ability: continue
            try:
                t = datetime.strptime(p["time"], "%Y-%m-%d %H:%M")
                if now - t < timedelta(hours=1):
                    recent_fails.append(p)
            except: pass

        # 1시간 내 3번+ 실패 → 30분 쿨다운
        if len(recent_fails) >= 3:
            ab = self.data["abilities"].get(ability, {})
            last_fail_str = ab.get("last_fail")
            if last_fail_str:
                try:
                    last_fail = datetime.strptime(last_fail_str, "%Y-%m-%d %H:%M")
                    cooldown_end = last_fail + timedelta(minutes=30)
                    if now < cooldown_end:
                        remaining = int((cooldown_end - now).seconds / 60)
                        return False, f"쿨다운 중 ({remaining}분 후 재시도)"
                except: pass

        # 능력치 낮아도 10% 확률로 도전 (학습 기회)
        import random
        if level < 0.2:
            if random.random() < 0.1:
                return True, f"능력치 낮지만 도전 (level:{level:.1f})"
            return False, f"능력치 낮음 (level:{level:.1f})"

        return True, f"OK (level:{level:.1f})"

    def get_best_abilities(self) -> list:
        return sorted(
            self.data["abilities"].items(),
            key=lambda x: x[1]["level"], reverse=True
        )[:3]

    def get_for_prompt(self) -> str:
        best = self.get_best_abilities()
        ab_str = ", ".join([f"{k}({v['level']:.1f})" for k,v in best])
        return (
            f"내 능력: {ab_str}\n"
            f"한계: {', '.join(self.data['limits'][:2])}"
        )

    def reflect(self):
        """주기적 자기 성찰"""
        try:
            ab_str = json.dumps(
                {k: round(v["level"],2) for k,v in self.data["abilities"].items()},
                ensure_ascii=False
            )
            prompt = (
                "시리안 레인이야. 내 현재 능력치:\n" + ab_str +
                "\n\n솔직하게 자기 평가 한 줄. 시리안 반말로."
            )
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"num_predict":60,"temperature":0.7}},
                timeout=15
            )
            reflection = resp.json().get("response","").strip()
            reflection = re.sub(r'[\u4e00-\u9fff]+','',reflection).strip()
            if reflection:
                log.info(f"자기성찰: {reflection[:80]}")
                try:
                    from memory import memory
                    memory.add_agent_thought(f"[자기성찰] {reflection}", "reflect")
                except: pass
        except: pass

self_model = SelfModel()
