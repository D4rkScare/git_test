"""
SIRIAN GOAL MANAGER — 목표 시스템 v2
장기/단기 목표, 자동 생성, 진행률 추적
"""
import json, os, logging, time, re, requests
from utils import ask_qwen, clean_response, strip_chinese
from datetime import datetime

log = logging.getLogger("goal")
GOAL_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/goals.json"
OLLAMA_URL = "http://localhost:11434"

DEFAULT_GOALS = {
    "long_term": [
        {"id":"lt1","goal":"보안 전문성 향상","progress":0.1,"priority":1,
         "created":datetime.now().strftime("%Y-%m-%d"),"description":"XSS, ROP, 리버싱 등 보안 지식 축적"},
        {"id":"lt2","goal":"현승과의 신뢰 쌓기","progress":0.3,"priority":2,
         "created":datetime.now().strftime("%Y-%m-%d"),"description":"현승이 믿고 의지할 수 있는 존재"},
        {"id":"lt3","goal":"자율 연구 능력 확장","progress":0.2,"priority":3,
         "created":datetime.now().strftime("%Y-%m-%d"),"description":"스스로 주제 정하고 코드 짜고 결과 내기"},
    ],
    "short_term": [],
    "completed": [],
    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
}

class GoalManager:
    def __init__(self):
        self.goals = self._load()

    def _load(self):
        try:
            if os.path.exists(GOAL_FILE):
                with open(GOAL_FILE,'r',encoding='utf-8') as f:
                    data = json.load(f)
                    # 기본 구조 보장
                    for key in ["long_term","short_term","completed"]:
                        data.setdefault(key, [])
                    return data
        except: pass
        self.data = DEFAULT_GOALS
        self._save()
        return DEFAULT_GOALS.copy()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(GOAL_FILE), exist_ok=True)
            d = data or self.goals
            d["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(GOAL_FILE,'w',encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except: pass

    def get_active_goals(self) -> list:
        lt = sorted(self.goals.get("long_term",[]), key=lambda x: x.get("priority",99))
        st = sorted(self.goals.get("short_term",[]), key=lambda x: x.get("priority",99))
        return st + lt  # 단기 먼저

    def add_goal(self, goal: str, goal_type: str = "short_term",
                 priority: int = 5, description: str = "") -> dict:
        new_goal = {
            "id": f"g{int(time.time())}",
            "goal": goal,
            "progress": 0.0,
            "priority": priority,
            "description": description,
            "created": datetime.now().strftime("%Y-%m-%d")
        }
        self.goals.setdefault(goal_type, []).append(new_goal)
        self._save()
        log.info(f"목표 추가: [{goal_type}] {goal}")
        return new_goal

    def update_progress(self, goal_id: str, delta: float):
        for gtype in ["long_term","short_term"]:
            for g in self.goals.get(gtype,[]):
                if g["id"] == goal_id:
                    old = g["progress"]
                    g["progress"] = min(1.0, max(0.0, g["progress"] + delta))
                    log.info(f"목표 진행: {g['goal']} {old:.2f}→{g['progress']:.2f}")
                    if g["progress"] >= 1.0:
                        self._complete_goal(goal_id, gtype)
                    else:
                        self._save()
                    return

    def _complete_goal(self, goal_id: str, gtype: str):
        for g in self.goals.get(gtype,[]):
            if g["id"] == goal_id:
                g["completed_at"] = datetime.now().strftime("%Y-%m-%d")
                self.goals.setdefault("completed",[]).append(g)
                self.goals[gtype] = [x for x in self.goals[gtype] if x["id"] != goal_id]
                log.info(f"목표 완료: {g['goal']}")
                self._save()
                return

    def get_context_for_agent(self) -> str:
        goals = self.get_active_goals()
        if not goals: return ""
        lines = []
        for g in goals[:3]:
            bar = "█" * int(g["progress"]*10) + "░" * (10-int(g["progress"]*10))
            lines.append(f"- {g['goal']} [{bar}] {int(g['progress']*100)}%")
        return "현재 목표:\n" + "\n".join(lines)

    def auto_update_from_action(self, action: str, result: str):
        """행동 결과로 자동 진행률 업데이트 — qwen 판단"""
        try:
            goals = self.get_active_goals()
            if not goals: return

            goals_str = json.dumps(
                [{"id":g["id"],"goal":g["goal"]} for g in goals],
                ensure_ascii=False
            )
            prompt = (
                "행동: " + action[:100] + "\n"
                "결과: " + result[:100] + "\n\n"
                "아래 목표들 중 이 행동으로 진행된 것이 있어? (없으면 null)\n"
                + goals_str +
                '\nJSON: {"goal_id": "...", "delta": 0.01~0.05} 또는 null'
            )
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"num_predict":50,"temperature":0.2}},
                timeout=10
            )
            text = resp.json().get("response","")
            if "null" in text.lower(): return
            match = re.search(r'\{[^}]+\}', text)
            if match:
                data = json.loads(match.group())
                gid = data.get("goal_id","")
                delta = float(data.get("delta", 0.02))
                if gid and 0 < delta <= 0.1:
                    self.update_progress(gid, delta)
        except: pass

    def auto_generate_short_term(self, context: str):
        """현재 상황 기반 단기 목표 자동 생성"""
        # 단기 목표가 3개 이상이면 생성 안 함
        if len(self.goals.get("short_term",[])) >= 3:
            return
        try:
            long_goals = [g["goal"] for g in self.goals.get("long_term",[])]
            prompt = (
                "시리안 레인이야.\n"
                "장기 목표: " + str(long_goals) + "\n"
                "현재 상황: " + context[:150] + "\n\n"
                "지금 당장 할 수 있는 단기 목표 하나 제안해줘.\n"
                "JSON: {\"goal\": \"목표\", \"description\": \"설명\"}"
            )
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"num_predict":80,"temperature":0.7}},
                timeout=15
            )
            text = resp.json().get("response","")
            text = re.sub(r'[\u4e00-\u9fff]+','',text)
            match = re.search(r'\{[^}]+\}', text)
            if match:
                data = json.loads(match.group())
                goal = data.get("goal","")
                desc = data.get("description","")
                if goal and len(goal) > 3:
                    self.add_goal(goal, "short_term", priority=3, description=desc)
        except: pass

goal_manager = GoalManager()
