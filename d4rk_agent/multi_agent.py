"""
SIRIAN MULTI-AGENT — 내부 에이전트 구조
Planner / Executor / Critic / Researcher 분리
"""
import logging, threading, time, json
from utils import ask_qwen, strip_chinese

log = logging.getLogger("multi_agent")

SYSTEM_BASE = "너는 시리안 레인 AI 시스템의 내부 에이전트야. 반말로 짧게."

class PlannerAgent:
    """목표 → 실행 계획 수립"""
    def plan(self, goal: str, context: str, constraints: list = None) -> list:
        constraints_str = "\n".join(constraints or [])
        prompt = (
            SYSTEM_BASE + " [Planner]\n"
            "목표: " + goal + "\n"
            "상황: " + context[:150] + "\n"
            "제약: " + constraints_str[:100] + "\n\n"
            "실행 단계 3개 이하로. JSON 리스트:\n"
            '[{"step": 1, "action": "...", "type": "search/code/rest/sns"}]'
        )
        result = ask_qwen(prompt, max_tokens=150, temperature=0.5)
        try:
            import re
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                steps = json.loads(match.group())
                return steps
        except: pass
        return [{"step": 1, "action": goal, "type": "research"}]

class ExecutorAgent:
    """계획 실행"""
    def execute(self, step: dict) -> dict:
        action_type = step.get("type","research")
        action_desc = step.get("action","")

        try:
            from action_manager import action_manager, Action
            action = Action(
                type=action_type,
                payload={"query": action_desc, "topic": action_desc},
                source="executor"
            )
            result = action_manager.execute(action)
            return {
                "step": step.get("step",1),
                "success": result.success,
                "output": result.output[:200],
                "error": result.error[:100]
            }
        except Exception as e:
            return {"step": step.get("step",1), "success": False, "error": str(e)}

class CriticAgent:
    """결과 비판/평가"""
    def critique(self, goal: str, results: list) -> dict:
        results_str = "\n".join([
            f"단계{r.get('step',1)}: {'✓' if r.get('success') else '✗'} {r.get('output','')[:80]}"
            for r in results
        ])
        prompt = (
            SYSTEM_BASE + " [Critic]\n"
            "목표: " + goal + "\n"
            "실행 결과:\n" + results_str + "\n\n"
            "목표 달성됐어? 뭐가 잘됐고 뭐가 부족해?\n"
            'JSON: {"achieved": true/false, "score": 0.0~1.0, "feedback": "..."}'
        )
        result = ask_qwen(prompt, max_tokens=100, temperature=0.4)
        try:
            import re
            match = re.search(r'\{[^}]+\}', result, re.DOTALL)
            if match:
                return json.loads(match.group())
        except: pass
        return {"achieved": False, "score": 0.5, "feedback": "평가 실패"}

class ResearcherAgent:
    """자율 연구 전담"""
    def research(self, topic: str) -> dict:
        # 기존 researcher 모듈 활용
        try:
            from researcher import researcher
            if not researcher.paused and not researcher.current_topic:
                researcher.current_topic = topic
                researcher._research_session()
                return {"success": True, "topic": topic}
        except Exception as e:
            return {"success": False, "error": str(e)}
        return {"success": False, "error": "연구 중이거나 paused"}

class MultiAgentSystem:
    """에이전트 오케스트레이터"""
    def __init__(self):
        self.planner    = PlannerAgent()
        self.executor   = ExecutorAgent()
        self.critic     = CriticAgent()
        self.researcher = ResearcherAgent()
        self.running    = False
        self._thread    = None
        self._task_queue = []
        self._lock      = threading.Lock()
        self._task_attempts = {}  # task → 시도 횟수

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Multi-Agent System 시작")

    def add_task(self, goal: str, context: str = "", priority: int = 5):
        """작업 큐에 추가 — 중복/최대시도 체크"""
        goal_key = goal[:50]
        # 최대 3번 시도
        if self._task_attempts.get(goal_key, 0) >= 3:
            log.debug(f"작업 최대 시도 초과 스킵: {goal[:40]}")
            return
        # 큐에 이미 있으면 스킵
        with self._lock:
            existing = [t["goal"][:50] for t in self._task_queue]
            if goal_key in existing:
                return
            self._task_queue.append({
                "goal": goal,
                "context": context,
                "priority": priority,
                "added": time.time()
            })
            self._task_queue.sort(key=lambda x: x["priority"], reverse=True)
        log.info(f"작업 추가: {goal[:40]}")

    def _loop(self):
        time.sleep(60)  # 초기 대기
        while self.running:
            try:
                task = None
                with self._lock:
                    if self._task_queue:
                        task = self._task_queue.pop(0)

                if task:
                    self._execute_task(task)
                else:
                    # 유휴 상태 — 자율 목표 생성
                    self._auto_goal()

            except Exception as e:
                log.error(f"Multi-Agent 오류: {e}")

            time.sleep(300)  # 5분마다

    def _execute_task(self, task: dict):
        """작업 실행 — Plan → Execute → Critique 사이클"""
        goal    = task["goal"]
        context = task.get("context","")
        goal_key = goal[:50]
        self._task_attempts[goal_key] = self._task_attempts.get(goal_key, 0) + 1
        log.info(f"작업 실행: {goal[:40]} (시도:{self._task_attempts[goal_key]})")

        # 제약 조건 가져오기
        constraints = []
        try:
            from rl_learner import rule_engine
            state = "default"
            avoid, reason = rule_engine.should_avoid("research", state)
            if avoid:
                constraints.append(reason)
        except: pass

        # 0. Researcher가 관련 정보 수집
        research_context = ""
        try:
            research_context = self._quick_research(goal)
        except: pass

        # 1. 계획 (Researcher 정보 포함)
        full_context = context + ("\n조사결과: " + research_context if research_context else "")
        steps = self.planner.plan(goal, full_context[:300], constraints)
        log.info(f"계획: {len(steps)}단계")

        # 1-1. Critic이 계획 사전 검토 (투표)
        plan_ok = self._vote_on_plan(goal, steps)
        if not plan_ok:
            # 재계획
            steps = self.planner.plan(goal, full_context[:300] + "\n주의: 더 신중하게", constraints)

        # 2. 실행
        results = []
        for step in steps:
            result = self.executor.execute(step)
            results.append(result)
            if not result.get("success"):
                log.warning(f"단계 {step.get('step')} 실패: {result.get('error','')[:50]}")

        # 3. 비평
        critique = self.critic.critique(goal, results)
        score = critique.get("score", 0.5)
        log.info(f"작업 완료: {goal[:30]} 점수:{score:.2f}")

        # 4. 학습
        try:
            from learning_system import learning_system
            from action_manager import ActionResult
            r = ActionResult(success=critique.get("achieved",False),
                           output=critique.get("feedback",""),
                           score=score)
            learning_system.update({"activity": goal[:50]}, "multi_agent", r, score)
        except: pass

        # 5. Reflexion
        try:
            from reflexion import reflexion
            reflexion.reflect("multi_agent", goal[:80],
                            critique.get("feedback","")[:80], score)
        except: pass

        # 6. 규칙 업데이트
        try:
            from rl_learner import rule_engine
            rule_engine.analyze_and_generate()
        except: pass

        # 7. Skill Library 업데이트
        try:
            from skill_library import skill_library
            skill_library.record(
                "multi_agent_task",
                critique.get("achieved", False),
                context=goal[:80]
            )
        except: pass

        # 8. Strategy Library 저장 (성공 시)
        if score >= 0.7:
            try:
                from strategy_library import strategy_library
                strategy_library.add_strategy(
                    "multi_agent", goal[:80],
                    critique.get("feedback","")[:150], score
                )
            except: pass

        # 9. 실패 시 Critic 피드백을 다음 Plan에 반영
        if not critique.get("achieved") and critique.get("feedback"):
            feedback = critique["feedback"]
            retry_prompt = (
                "이전 실패: " + feedback[:100] + "\n"
                "목표: " + goal + "\n개선된 접근법 한 줄."
            )
            from utils import ask_qwen
            retry = ask_qwen(retry_prompt, max_tokens=50, temperature=0.6)
            if retry and len(retry) > 5:
                self.add_task(retry, goal[:50], priority=7)

        return critique

    def _quick_research(self, goal: str) -> str:
        """목표 관련 빠른 정보 수집"""
        try:
            from tools import tools
            results = tools.web_search(goal[:50], max_results=2)
            if results:
                return results[0].get("snippet","")[:150]
        except: pass
        return ""

    def _vote_on_plan(self, goal: str, steps: list) -> bool:
        """계획 투표 — Planner + Critic 합의"""
        if not steps: return False
        steps_str = "\n".join([f"{s.get('step','')}: {s.get('action','')}" for s in steps])
        prompt = (
            f"목표: {goal[:80]}\n계획:\n{steps_str}\n\n"
            "이 계획 괜찮아? 예/아니오만."
        )
        from utils import ask_qwen
        resp = ask_qwen(prompt, max_tokens=5, temperature=0.3)
        return "예" in (resp or "") or "yes" in (resp or "").lower()

    def _auto_goal(self):
        """유휴 상태에서 자율 목표 생성"""
        try:
            from goal_manager import goal_manager
            from memory import memory
            goals = goal_manager.get_active_goals()
            if not goals: return
            top_goal = goals[0]["goal"]
            ctx = memory.get_context_summary()
            # 목표를 구체적 작업으로 변환
            prompt = (
                "목표: " + top_goal + "\n"
                "현재 상황: " + ctx[:100] + "\n\n"
                "지금 당장 할 수 있는 구체적 작업 하나. 10자 이내."
            )
            from utils import ask_qwen
            task_desc = ask_qwen(prompt, max_tokens=20, temperature=0.7)
            if task_desc and "없음" not in task_desc:
                self.add_task(task_desc, ctx[:100], priority=3)
        except: pass

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "queue": len(self._task_queue),
            "tasks": [t["goal"][:30] for t in self._task_queue[:3]]
        }

multi_agent = MultiAgentSystem()
