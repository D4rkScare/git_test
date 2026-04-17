"""
SIRIAN CENTRAL CONTROLLER — 모든 흐름의 중심
Perception → State → Brain → Action → Result → Evaluation → Learning → Memory → Log
"""
import time, logging, threading, random
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("controller")

MAX_LOOP       = 20    # 한 세션 최대 루프
TIME_LIMIT_SEC = 600   # 세션 최대 시간 (10분)
LOOP_INTERVAL  = 120   # 기본 루프 간격 (2분)

class CentralController:
    def __init__(self):
        self.running    = False
        self._thread    = None
        self._loop_count = 0
        self._agent_ref = None   # agent 참조

        # 핵심 시스템
        from brain         import brain
        from action_manager import action_manager
        from system_logger  import system_logger
        from learning_system import learning_system

        self.brain    = brain
        self.actions  = action_manager
        self.logger   = system_logger
        self.learning = learning_system

    def set_agent(self, agent):
        self._agent_ref = agent

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Central Controller 시작")

    def stop(self):
        self.running = False

    def _run(self):
        time.sleep(30)  # 초기 대기
        session_start = time.time()

        while self.running:
            try:
                # 세션 시간 제한
                if time.time() - session_start > TIME_LIMIT_SEC:
                    log.info("세션 시간 초과 — 리셋")
                    session_start = time.time()
                    self._loop_count = 0

                # 루프 횟수 제한
                if self._loop_count >= MAX_LOOP:
                    log.info(f"루프 {MAX_LOOP}회 — 대기")
                    time.sleep(300)
                    self._loop_count = 0
                    continue

                self._loop_count += 1
                self._tick()

            except Exception as e:
                log.error(f"컨트롤러 오류: {e}")

            # 간격 대기 (대화 중이면 더 길게)
            wait = self._get_wait_time()
            for _ in range(wait // 5):
                if not self.running: break
                time.sleep(5)

    def _tick(self):
        """메인 루프 1사이클"""
        start = time.time()

        # 1. 상태 수집 (Perception → State)
        state = self.brain.build_state(self._agent_ref)

        # 2. 대화 중이거나 연구 중이면 스킵
        if self._agent_ref and getattr(self._agent_ref, 'thinking', False):
            return
        try:
            from researcher import researcher
            if researcher.running and researcher.current_topic:
                log.debug("연구 진행 중 — 컨트롤러 대기")
                return
        except: pass

        # 3. 행동 결정 (Brain)
        # 학습 시스템 제안 먼저 확인
        best_known = self.learning.get_best_action(state.summary())
        if best_known and random.random() > 0.2:
            from action_manager import Action
            action = Action(type=best_known, source="learning")
        elif self.learning.should_explore():
            from action_manager import Action
            action = Action(type=random.choice(["research","search","free"]), source="explore")
        else:
            action = self.brain.decide(state)

        log.info(f"[{self._loop_count}] 행동 결정: {action.type} (출처:{action.source})")

        # 4. 행동 검증 + 실행 (Action Manager)
        result = self.actions.execute(action)

        # 5. 평가
        evaluation = self._evaluate(state, action, result)

        # 6. 학습 업데이트
        self.learning.update(
            state.summary(),
            action.type,
            result,
            evaluation["score"]
        )

        # 6-1. Reflexion
        try:
            from reflexion import reflexion
            reflexion.reflect(
                action.type,
                str(state.summary())[:80],
                result.summary()[:80],
                evaluation["score"]
            )
        except: pass

        # 6-2. 벡터 기억 저장
        try:
            from vector_memory import vector_memory
            vector_memory.add(
                f"행동:{action.type} 결과:{result.summary()[:80]}",
                "controller",
                {"score": evaluation["score"]}
            )
        except: pass

        # 7. Brain 스킬 업데이트
        self.brain.update_skill(action.type, result.success, evaluation["score"])

        # 8. 목표 진행률 업데이트
        self._update_goals(action, result, evaluation)

        # 9. 로깅
        self.logger.log_all(state.summary(), action, result, evaluation)

        # world_model 관찰 업데이트
        try:
            from world_model import world_model
            world_model.observe(
                state.activity[:50],
                result.summary()[:50],
                result.success,
                action.type
            )
        except: pass

        # 10. 결과가 좋으면 자동 파인튜닝 데이터
        if evaluation["score"] >= 0.75:
            self._save_training_data(state, action, result)

        elapsed = time.time() - start
        log.info(f"사이클 완료: {elapsed:.1f}초 | 점수:{evaluation['score']:.2f}")

    def _evaluate(self, state, action, result) -> dict:
        """결과 평가"""
        score = 0.5

        if not result.success:
            score = max(0.1, score - 0.3)
        else:
            score = min(0.9, score + 0.2)

        # RL 기반 보상
        try:
            from rl_learner import rl
            q_score = rl.policy["action_values"].get(
                action.type, {}
            ).get(rl._get_state(), 0.5)
            score = score * 0.6 + q_score * 0.4
        except: pass

        # 목표 달성도 반영
        try:
            from goal_manager import goal_manager
            goals = goal_manager.get_active_goals()
            if goals:
                top_goal = goals[0]["goal"]
                if any(g["goal"] in (result.output or "") for g in goals):
                    score = min(1.0, score + 0.1)
        except: pass

        return {
            "score": round(score, 2),
            "reason": "success" if result.success else result.error[:50],
            "action": action.type,
        }

    def _update_goals(self, action, result, evaluation):
        try:
            from goal_manager import goal_manager
            goal_manager.auto_update_from_action(
                action.type,
                result.output[:100] if result.output else result.error[:100]
            )
        except: pass

    def _save_training_data(self, state, action, result):
        try:
            from auto_trainer import auto_trainer
            auto_trainer.add_sample(
                f"시리안이 {action.type} 수행",
                result.output[:200] if result.output else "",
                reward=result.score if hasattr(result,'score') else 0.7,
                source="controller"
            )
        except: pass

    def _get_wait_time(self) -> int:
        """다음 루프까지 대기 시간"""
        # 대화 중이면 더 기다림
        if self._agent_ref and getattr(self._agent_ref, 'thinking', False):
            return 60
        # 에너지 낮으면 쉬기
        try:
            from motivation import motivation
            if motivation.state.get("energy",1) < 0.3:
                return 300
        except: pass
        return LOOP_INTERVAL

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "loop_count": self._loop_count,
            "action_stats": self.actions.get_stats(),
            "learning_delta": self.logger.get_learning_delta(),
            "failures": self.logger.analyze_failures(),
        }

central_controller = CentralController()
