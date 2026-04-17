"""
SIRIAN STATE MACHINE — Observe→Plan→Act→Reflect→Adapt 사이클
Central Brain의 핵심 루프
"""
import time, logging, json, threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("state_machine")

# ── 상태 정의 ──
class CycleState:
    OBSERVE  = "observe"
    PLAN     = "plan"
    ACT      = "act"
    REFLECT  = "reflect"
    ADAPT    = "adapt"
    IDLE     = "idle"

@dataclass
class CycleContext:
    """한 사이클의 전체 컨텍스트"""
    # Observe
    screen:       str = ""
    activity:     str = ""
    heard:        str = ""
    emotion:      str = "무관심"
    energy:       float = 0.8
    curiosity:    float = 0.6
    boredom:      float = 0.3
    goals:        List[str] = field(default_factory=list)
    memories:     str = ""
    strategies:   str = ""  # 과거 성공 전략
    world_pred:   str = ""
    rules:        str = ""  # RL 규칙

    # Plan
    selected_action: str = ""
    action_reason:   str = ""
    sub_steps:       List[str] = field(default_factory=list)

    # Act
    result:     Optional[Any] = None
    success:    bool = False
    score:      float = 0.5

    # Reflect
    reflection: str = ""
    why_success: str = ""
    why_fail:    str = ""
    next_suggestion: str = ""

    # Adapt
    adapted: bool = False
    adaptation: str = ""

    # Meta
    cycle_id: int = 0
    started_at: str = ""
    elapsed: float = 0.0

class StateMachine:
    def __init__(self):
        self.state   = CycleState.IDLE
        self.cycle   = 0
        self.running = False
        self._thread = None
        self._agent_ref = None
        self._lock = threading.Lock()

    def set_agent(self, agent):
        self._agent_ref = agent

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("State Machine 시작")

    def _run(self):
        time.sleep(45)  # 초기 대기
        while self.running:
            try:
                # 대화 중이면 스킵
                if self._agent_ref and getattr(self._agent_ref, 'thinking', False):
                    time.sleep(10)
                    continue

                ctx = CycleContext(
                    cycle_id=self.cycle,
                    started_at=datetime.now().strftime("%H:%M:%S")
                )
                self._run_cycle(ctx)
                self.cycle += 1

            except Exception as e:
                log.error(f"State Machine 오류: {e}")

            # 대기 (에너지/동기 기반)
            wait = self._calc_wait()
            for _ in range(wait // 5):
                if not self.running: break
                time.sleep(5)

    def _run_cycle(self, ctx: CycleContext):
        """Observe → Plan → Act → Reflect → Adapt"""
        t0 = time.time()

        # 1. OBSERVE
        self.state = CycleState.OBSERVE
        ctx = self._observe(ctx)
        log.debug(f"[{ctx.cycle_id}] OBSERVE: {ctx.activity[:30]} | {ctx.emotion}")

        # 2. PLAN
        self.state = CycleState.PLAN
        ctx = self._plan(ctx)
        log.info(f"[{ctx.cycle_id}] PLAN: {ctx.selected_action} ({ctx.action_reason[:40]})")

        if not ctx.selected_action:
            return

        # 3. ACT
        self.state = CycleState.ACT
        ctx = self._act(ctx)
        log.info(f"[{ctx.cycle_id}] ACT: {'✓' if ctx.success else '✗'} score:{ctx.score:.2f}")

        # 4. REFLECT
        self.state = CycleState.REFLECT
        ctx = self._reflect(ctx)
        log.info(f"[{ctx.cycle_id}] REFLECT: {ctx.reflection[:60]}")

        # 5. ADAPT
        self.state = CycleState.ADAPT
        ctx = self._adapt(ctx)
        if ctx.adapted:
            log.info(f"[{ctx.cycle_id}] ADAPT: {ctx.adaptation[:60]}")

        ctx.elapsed = time.time() - t0
        self.state = CycleState.IDLE

        # 로그
        try:
            from system_logger import system_logger
            system_logger.log_event("cycle", json.dumps({
                "id": ctx.cycle_id,
                "action": ctx.selected_action,
                "score": ctx.score,
                "adapted": ctx.adapted,
                "elapsed": round(ctx.elapsed, 1)
            }, ensure_ascii=False))
        except: pass

    # ── 1. OBSERVE ──
    def _observe(self, ctx: CycleContext) -> CycleContext:
        agent = self._agent_ref

        # 화면/청각
        ctx.screen   = getattr(agent, 'last_screen_analysis', '')[:200]
        ctx.activity = getattr(agent, 'last_screen_activity', '')
        ctx.heard    = getattr(agent, 'last_heard', '')[:100]

        # 감정
        try:
            from emotion_engine import emotion_engine
            e = emotion_engine.get_current()
            ctx.emotion = e.get("emotion", "무관심")
        except: pass

        # 동기
        try:
            from motivation import motivation
            s = motivation.state
            ctx.energy    = s.get("energy", 0.8)
            ctx.curiosity = s.get("curiosity", 0.6)
            ctx.boredom   = s.get("boredom", 0.3)
        except: pass

        # 목표
        try:
            from goal_manager import goal_manager
            ctx.goals = [g["goal"] for g in goal_manager.get_active_goals()[:3]]
        except: pass

        # Vector Memory 검색 (semantic + recency + importance)
        try:
            from vector_memory import vector_memory
            query = ctx.activity + " " + ctx.heard + " " + " ".join(ctx.goals)
            ctx.memories = vector_memory.get_context(query, top_k=4)
        except: pass

        # 과거 성공 전략 검색
        try:
            from reflexion import reflexion
            ctx.strategies = reflexion.get_for_prompt(ctx.selected_action or "")
        except: pass

        # World Model 예측
        try:
            from world_model import world_model
            ctx.world_pred = world_model.predict(ctx.activity)
        except: pass

        # RL 규칙
        try:
            from rl_learner import rule_engine
            ctx.rules = rule_engine.get_for_prompt()
        except: pass

        # Graph Memory 검색
        try:
            from graph_memory import graph_memory
            gm = graph_memory.get_for_prompt(
                ctx.activity + " " + " ".join(ctx.goals)
            )
            if gm:
                ctx.memories = (ctx.memories + "\n" + gm)[:400]
        except: pass

        return ctx

    # ── 2. PLAN (ToT + Brain) ──
    def _plan(self, ctx: CycleContext) -> CycleContext:
        # 복잡한 상황은 ToT로 깊이 추론
        try:
            if ctx.boredom < 0.3 and ctx.goals:
                from tot_reasoner import tot_reasoner
                problem = f"목표: {ctx.goals[0]} | 상황: {ctx.activity[:50]}"
                tot_result = tot_reasoner.reason(problem, ctx.memories[:100])
                if tot_result.get("confidence",0) > 0.6:
                    ctx.action_reason = f"ToT({tot_result['confidence']:.1f})"
                    log.debug(f"ToT 추론: {tot_result['answer'][:50]}")
        except: pass

        # 학습 시스템에서 최선 행동 먼저 확인
        try:
            from learning_system import learning_system
            best = learning_system.get_best_action({
                "emotion": ctx.emotion,
                "activity": ctx.activity[:20]
            })
            if best:
                ctx.selected_action = best
                ctx.action_reason   = ctx.action_reason or "학습된 최선 행동"
                return ctx
        except: pass

        # Brain으로 결정
        try:
            from brain import brain, State
            state = State(
                screen=ctx.screen, activity=ctx.activity,
                heard=ctx.heard, emotion=ctx.emotion,
                energy=ctx.energy, curiosity=ctx.curiosity,
                boredom=ctx.boredom, goals=ctx.goals,
                memories=ctx.memories, world_pred=ctx.world_pred,
                focus=ctx.rules
            )
            action = brain.decide(state)
            ctx.selected_action = action.type
            ctx.action_reason   = action.source
        except Exception as e:
            log.debug(f"Plan 오류: {e}")
            ctx.selected_action = "rest"
            ctx.action_reason   = "fallback"

        # RL 규칙으로 필터
        try:
            from rl_learner import rule_engine, rl
            avoid, reason = rule_engine.should_avoid(ctx.selected_action, rl._get_state())
            if avoid:
                log.info(f"행동 규칙 차단: {ctx.selected_action} — {reason}")
                ctx.selected_action = "rest"
                ctx.action_reason   = f"규칙 차단: {reason}"
        except: pass

        return ctx

    # ── 3. ACT ──
    def _act(self, ctx: CycleContext) -> CycleContext:
        try:
            from action_manager import action_manager, Action
            action = Action(
                type=ctx.selected_action,
                payload={},
                source="state_machine"
            )
            result = action_manager.execute(action)
            ctx.result  = result
            ctx.success = result.success
            ctx.score   = getattr(result, 'score', 0.5)

            # RL 업데이트
            try:
                from rl_learner import rl
                rl.update(ctx.selected_action, ctx.score, ctx.activity[:50])
            except: pass

        except Exception as e:
            log.error(f"Act 오류: {e}")
            ctx.success = False
            ctx.score   = 0.1

        return ctx

    # ── 4. REFLECT ──
    def _reflect(self, ctx: CycleContext) -> CycleContext:
        result_str = ""
        if ctx.result:
            result_str = getattr(ctx.result, 'output', '') or getattr(ctx.result, 'error', '')

        outcome = "성공" if ctx.success else "실패"
        prompt = (
            f"시리안 레인이야. 방금 행동 반성.\n"
            f"행동: {ctx.selected_action}\n"
            f"이유: {ctx.action_reason[:60]}\n"
            f"결과: {outcome} (점수:{ctx.score:.2f})\n"
            f"출력: {result_str[:100]}\n\n"
            f"{'왜 성공했어? 핵심 이유.' if ctx.success else '왜 실패했어? 핵심 이유.'}\n"
            "한 줄로. 시리안 반말."
        )
        reflection = ask_qwen(prompt, max_tokens=60, temperature=0.5)
        # 이상한 텍스트 필터
        from utils import clean_response, strip_chinese
        reflection = clean_response(strip_chinese(reflection or ""))
        # 숫자+영어 잡음 제거
        import re as _re
        reflection = _re.sub(r'\d{4,}|[a-zA-Z]{1,3}', '', reflection).strip()
        ctx.reflection = reflection[:100] if reflection else ""

        if ctx.success:
            ctx.why_success = reflection or ""
        else:
            ctx.why_fail = reflection or ""

        # Reflexion 저장
        try:
            from reflexion import reflexion
            reflexion.reflect(
                ctx.selected_action,
                ctx.activity[:80],
                result_str[:80],
                ctx.score
            )
        except: pass

        # Meta Layer 평가
        try:
            from meta_layer import meta_layer
            meta_eval = meta_layer.evaluate_cycle(
                {"activity": ctx.activity, "emotion": ctx.emotion},
                ctx.selected_action,
                ctx.score,
                ctx.reflection
            )
            if meta_eval.get("adjustment"):
                log.info(f"Meta 전략 조정: {meta_eval['adjustment'][:40]}")
        except: pass

        # 다음 제안
        if ctx.score < 0.4:
            suggest_prompt = (
                f"행동 {ctx.selected_action} 실패.\n"
                f"이유: {ctx.why_fail[:80]}\n"
                "다음엔 뭘 해볼까? 행동 하나만."
            )
            suggestion = ask_qwen(suggest_prompt, max_tokens=20, temperature=0.6)
            ctx.next_suggestion = suggestion or ""

        return ctx

    # ── 5. ADAPT ──
    def _adapt(self, ctx: CycleContext) -> CycleContext:
        """Reflection 결과로 실제 전략/행동 수정"""

        # 실패면 다음 행동 변경 + 규칙 업데이트
        if not ctx.success and ctx.score < 0.35:
            try:
                from rl_learner import rule_engine, rl
                # 실패 패턴 기록
                rl.record_step(ctx.selected_action, ctx.activity[:40])
                # 규칙 재분석
                new_rules = rule_engine.analyze_and_generate()
                if new_rules:
                    ctx.adapted = True
                    ctx.adaptation = f"새 규칙 {len(new_rules)}개 생성"
            except: pass

        # 성공이면 전략 강화
        elif ctx.success and ctx.score > 0.75:
            try:
                from learning_system import learning_system
                from action_manager import ActionResult
                r = ActionResult(success=True, output=ctx.why_success, score=ctx.score)
                learning_system.update(
                    {"emotion": ctx.emotion, "activity": ctx.activity[:20]},
                    ctx.selected_action, r, ctx.score
                )
                ctx.adapted  = True
                ctx.adaptation = f"성공 전략 강화: {ctx.selected_action}"
            except: pass

        # next_suggestion 있으면 multi_agent에 작업 추가
        if ctx.next_suggestion and len(ctx.next_suggestion) > 3:
            try:
                from multi_agent import multi_agent
                multi_agent.add_task(ctx.next_suggestion, ctx.activity[:50], priority=6)
                ctx.adapted    = True
                ctx.adaptation += f" | 후속 작업: {ctx.next_suggestion[:30]}"
            except: pass

        # World Model 업데이트
        try:
            from world_model import world_model
            world_model.observe(
                ctx.activity[:50],
                getattr(ctx.result, 'output', '')[:50] if ctx.result else "",
                ctx.success,
                ctx.selected_action
            )
        except: pass

        # Causal World Model 관찰
        try:
            from causal_world_model import causal_world_model
            causal_world_model.observe(
                ctx.selected_action,
                ctx.activity[:50],
                getattr(ctx.result, 'output', ctx.reflection)[:60],
                ctx.success
            )
            causal_world_model.verify_prediction(
                ctx.selected_action, ctx.activity, ctx.success
            )
        except: pass

        # 장기 목표 태스크 자동 완료
        try:
            from long_horizon_planner import long_horizon_planner
            long_horizon_planner.auto_complete_from_activity(
                ctx.selected_action + " " + ctx.activity[:30],
                getattr(ctx.result, 'output', '')[:50]
            )
        except: pass

        # Goal 진행률 업데이트
        try:
            from goal_manager import goal_manager
            result_text = getattr(ctx.result, 'output', '') if ctx.result else ''
            goal_manager.auto_update_from_action(ctx.selected_action, result_text[:100])
        except: pass

        # Vector Memory에 저장
        try:
            from vector_memory import vector_memory
            entry = (
                f"[{ctx.cycle_id}] {ctx.selected_action} → "
                f"{'성공' if ctx.success else '실패'} "
                f"({ctx.score:.1f}) | {ctx.reflection[:80]}"
            )
            vector_memory.add(entry, "cycle", {"score": ctx.score})
        except: pass

        return ctx

    def _calc_wait(self) -> int:
        try:
            from motivation import motivation
            if motivation.state.get("energy", 1) < 0.3:
                return 300
            if motivation.state.get("boredom", 0) > 0.7:
                return 60
        except: pass
        return 120

    def get_status(self) -> dict:
        return {
            "state":  self.state,
            "cycle":  self.cycle,
            "running": self.running
        }

state_machine = StateMachine()
