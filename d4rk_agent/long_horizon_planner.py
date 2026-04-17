"""
SIRIAN LONG-HORIZON PLANNER — 장기 목표 추적
장기 목표 → 세부 태스크 자동 분해 → 수주 단위 추적
"""
import json, os, logging, threading, time
from datetime import datetime, timedelta
from utils import ask_qwen, strip_chinese

log = logging.getLogger("lh_plan")
LH_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/long_horizon.json"

class LongHorizonPlanner:
    def __init__(self):
        self.data = self._load()
        self._thread = None
        self.running = False

    def _load(self):
        default = {
            "goals": [
                {
                    "id":       "G001",
                    "goal":     "보안 전문가 수준 지식 달성",
                    "horizon":  "3개월",
                    "tasks":    [],
                    "progress": 0.0,
                    "status":   "active",
                    "created":  datetime.now().strftime("%Y-%m-%d"),
                }
            ],
            "completed": [],
            "weekly_review": [],
        }
        try:
            if os.path.exists(LH_FILE):
                with open(LH_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(LH_FILE), exist_ok=True)
            with open(LH_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Long-Horizon Planner 시작")

    def _loop(self):
        time.sleep(1800)  # 30분 후 첫 실행
        while self.running:
            try:
                self._tick()
            except Exception as e:
                log.error(f"LH Planner 오류: {e}")
            time.sleep(3600)  # 1시간마다

    def _tick(self):
        """주기적 진행률 체크 + 태스크 생성"""
        for goal in self.data["goals"]:
            if goal.get("status") != "active":
                continue
            # 세부 태스크 없으면 생성
            if not goal.get("tasks"):
                self._decompose(goal)
            # 진행률 업데이트
            self._update_progress(goal)
            # 완료 체크
            if goal["progress"] >= 1.0:
                self._complete_goal(goal)

        # 주간 리뷰 (7일마다)
        self._weekly_review()
        self._save()

    def add_goal(self, goal_text: str, horizon: str = "1개월") -> str:
        """장기 목표 추가"""
        gid = f"G{len(self.data['goals'])+1:03d}"
        goal = {
            "id":       gid,
            "goal":     goal_text,
            "horizon":  horizon,
            "tasks":    [],
            "progress": 0.0,
            "status":   "active",
            "created":  datetime.now().strftime("%Y-%m-%d"),
        }
        self.data["goals"].append(goal)
        self._decompose(goal)
        self._save()
        log.info(f"장기 목표 추가: {goal_text[:40]}")
        return gid

    def _decompose(self, goal: dict):
        """목표 → 세부 태스크 자동 분해"""
        prompt = (
            "장기 목표: " + goal["goal"] + "\n"
            "기간: " + goal["horizon"] + "\n\n"
            "이 목표를 달성하기 위한 세부 태스크 5개.\n"
            'JSON: [{"task":"...", "week":1~4, "type":"research/practice/review"}]'
        )
        try:
            resp = ask_qwen(prompt, max_tokens=200, temperature=0.5)
            import re
            match = re.search(r'\[.*?\]', resp, re.DOTALL)
            if match:
                tasks = json.loads(match.group())
                goal["tasks"] = [
                    {**t, "done": False, "added": datetime.now().strftime("%Y-%m-%d")}
                    for t in tasks[:7]
                ]
                log.info(f"태스크 {len(goal['tasks'])}개 생성: {goal['goal'][:30]}")
        except Exception as e:
            log.debug(f"태스크 분해 실패: {e}")
            # 기본 태스크
            goal["tasks"] = [
                {"task": f"{goal['goal']} 기초 학습", "week": 1, "type": "research", "done": False},
                {"task": f"{goal['goal']} 실습", "week": 2, "type": "practice", "done": False},
                {"task": f"{goal['goal']} 복습", "week": 3, "type": "review", "done": False},
            ]

    def _update_progress(self, goal: dict):
        """진행률 업데이트"""
        tasks = goal.get("tasks", [])
        if not tasks:
            return
        done = sum(1 for t in tasks if t.get("done"))
        goal["progress"] = done / len(tasks)

        # multi_agent에 다음 태스크 추가
        next_task = next((t for t in tasks if not t.get("done")), None)
        if next_task:
            try:
                from multi_agent import multi_agent
                # 중복 방지
                queue_tasks = [t["goal"] for t in multi_agent._task_queue]
                if next_task["task"] not in queue_tasks:
                    multi_agent.add_task(
                        next_task["task"],
                        goal["goal"][:50],
                        priority=4
                    )
            except: pass

    def complete_task(self, goal_id: str, task_idx: int):
        """태스크 완료 처리"""
        goal = next((g for g in self.data["goals"] if g["id"] == goal_id), None)
        if not goal: return
        tasks = goal.get("tasks", [])
        if 0 <= task_idx < len(tasks):
            tasks[task_idx]["done"] = True
            tasks[task_idx]["completed"] = datetime.now().strftime("%Y-%m-%d")
            self._update_progress(goal)
            self._save()
            log.info(f"태스크 완료: {tasks[task_idx]['task'][:40]}")

    def auto_complete_from_activity(self, activity: str, result: str):
        """활동 기반 자동 태스크 완료"""
        for goal in self.data["goals"]:
            if goal.get("status") != "active": continue
            for i, task in enumerate(goal.get("tasks", [])):
                if task.get("done"): continue
                task_text = task.get("task","").lower()
                # 활동과 태스크 유사도 체크
                words = set(task_text.split())
                act_words = set(activity.lower().split())
                if len(words & act_words) >= 2:
                    self.complete_task(goal["id"], i)
                    break

    def _complete_goal(self, goal: dict):
        goal["status"]    = "completed"
        goal["completed"] = datetime.now().strftime("%Y-%m-%d")
        self.data["completed"].append(goal)
        log.info(f"장기 목표 달성: {goal['goal'][:40]}")
        try:
            from tts_engine import tts
            tts.speak(f"{goal['goal'][:30]} 목표 달성했어!", priority=True)
        except: pass

    def _weekly_review(self):
        """주간 리뷰"""
        reviews = self.data.get("weekly_review", [])
        if reviews:
            last = reviews[-1].get("time","")
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%d")
                if (datetime.now() - last_dt).days < 7:
                    return
            except: pass

        active = [g for g in self.data["goals"] if g.get("status") == "active"]
        if not active: return

        review_str = "\n".join([
            f"- {g['goal'][:40]}: {g['progress']:.0%}"
            for g in active
        ])
        prompt = (
            "시리안 레인이야. 장기 목표 주간 리뷰.\n" + review_str +
            "\n\n이번 주 어떻게 진행됐어? 반말로 두 줄."
        )
        review = ask_qwen(prompt, max_tokens=80, temperature=0.6)
        if review:
            self.data["weekly_review"].append({
                "time":   datetime.now().strftime("%Y-%m-%d"),
                "review": review.strip()
            })
            self.data["weekly_review"] = self.data["weekly_review"][-12:]
            log.info(f"주간 리뷰: {review[:60]}")
            try:
                from memory import memory
                memory.add_agent_thought(f"[주간리뷰] {review[:100]}", "longterm")
            except: pass

    def get_active_goals(self) -> list:
        return [g for g in self.data["goals"] if g.get("status") == "active"]

    def get_for_prompt(self) -> str:
        active = self.get_active_goals()
        if not active: return ""
        lines = []
        for g in active[:2]:
            lines.append(f"- {g['goal'][:50]} ({g['progress']:.0%})")
            next_task = next((t for t in g.get("tasks",[]) if not t.get("done")), None)
            if next_task:
                lines.append(f"  다음: {next_task['task'][:40]}")
        return "장기 목표:\n" + "\n".join(lines) if lines else ""

long_horizon_planner = LongHorizonPlanner()
