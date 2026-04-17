"""
SIRIAN BRAIN — 중앙 의사결정
모든 정보를 종합해서 최적 행동 결정
"""
import logging, random, json
from dataclasses import dataclass, field
from typing import Optional
from utils import ask_qwen, strip_chinese

log = logging.getLogger("brain")

@dataclass
class State:
    """현재 상태 전체"""
    screen:      str = ""
    activity:    str = ""
    heard:       str = ""
    emotion:     str = "무관심"
    emotion_int: float = 0.5
    energy:      float = 0.8
    curiosity:   float = 0.6
    boredom:     float = 0.3
    social_need: float = 0.4
    goals:       list = field(default_factory=list)
    memories:    str = ""
    world_pred:  str = ""
    self_info:   str = ""
    intimacy:    float = 0.35
    time_of_day: str = "낮"
    focus:       str = ""

    def summary(self) -> dict:
        return {
            "emotion": self.emotion,
            "activity": self.activity[:50],
            "energy": self.energy,
            "boredom": self.boredom,
        }

class Brain:
    def __init__(self):
        self._last_actions = []    # 최근 행동 기록 (다양성 강제)
        self._skill_cache = {}     # 스킬 성공률 캐시

    def build_state(self, agent) -> State:
        """모든 시스템에서 상태 수집"""
        state = State()

        # 화면/청각
        state.screen   = getattr(agent, 'last_screen_analysis', '')[:200]
        state.activity = getattr(agent, 'last_screen_activity', '')
        state.heard    = getattr(agent, 'last_heard', '')[:100]

        # 감정
        try:
            from emotion_engine import emotion_engine
            emo = emotion_engine.get_current()
            state.emotion     = emo.get("emotion","무관심")
            state.emotion_int = emo.get("intensity", 0.5)
        except:
            try:
                from memory import memory
                emo = memory.get_emotion_state()
                state.emotion = emo.get("current","무관심")
            except: pass

        # 동기
        try:
            from motivation import motivation
            s = motivation.state
            state.energy      = s.get("energy", 0.8)
            state.curiosity   = s.get("curiosity", 0.6)
            state.boredom     = s.get("boredom", 0.3)
            state.social_need = s.get("social_need", 0.4)
        except: pass

        # 목표
        try:
            from goal_manager import goal_manager
            goals = goal_manager.get_active_goals()
            state.goals = [g["goal"] for g in goals[:3]]
        except: pass

        # 기억
        try:
            from memory import memory
            state.memories = memory.get_relevant_context(state.screen)[:150]
        except: pass

        # 세계 예측 (강화)
        try:
            from world_model import world_model
            pred = world_model.predict(state.activity, "")
            state.world_pred = pred
        except: pass

        # rule_engine 규칙
        try:
            from rl_learner import rule_engine
            rules = rule_engine.get_for_prompt()
            if rules: state.focus = (state.focus + "\n" + rules)[:300]
        except: pass

        # 자기 정보
        try:
            from self_model import self_model
            state.self_info = self_model.get_for_prompt()
        except: pass

        # 관계
        try:
            from relationship import relationship
            level = relationship.get_intimacy_level("현승")
            state.intimacy = level.get("intimacy", 0.35)
        except: pass

        # 시간
        from datetime import datetime
        hour = datetime.now().hour
        if 5 <= hour < 12:   state.time_of_day = "아침"
        elif 12 <= hour < 18: state.time_of_day = "오후"
        elif 18 <= hour < 22: state.time_of_day = "저녁"
        else:                  state.time_of_day = "밤"

        # 집중
        try:
            from focus_system import focus
            state.focus = focus.get_for_prompt()
        except: pass

        return state

    def decide(self, state: State):
        """최적 행동 결정"""
        from action_manager import Action

        # 1. 스킬 기반 후보 생성
        candidates = self._generate_candidates(state)

        # 2. 다양성 강제 (epsilon-greedy + 최근 행동 기피)
        if random.random() < 0.2:
            # 탐험 — 완전 랜덤
            action_type = random.choice(["research","search","sns","rest","free"])
            return Action(type=action_type, source="brain_explore")

        # 3. Q값 + 상태 기반 최적 선택
        best = self._score_candidates(candidates, state)

        # 4. 최근 행동 중복 방지
        if best in self._last_actions[-3:]:
            # 다른 것 선택
            others = [c for c in candidates if c != best]
            best = random.choice(others) if others else best

        self._last_actions.append(best)
        self._last_actions = self._last_actions[-10:]

        return Action(type=best, payload=self._build_payload(best, state), source="brain")

    def _generate_candidates(self, state: State) -> list:
        """현재 상태에서 가능한 행동 목록"""
        candidates = ["research","search","sns","rest","free"]

        # 에너지 낮으면 rest 우선
        if state.energy < 0.25:
            return ["rest"]

        # 집중 중이면 현재 작업 유지
        if state.focus and "연구" in state.focus:
            candidates = ["research","search"]

        return candidates

    def _score_candidates(self, candidates: list, state: State) -> str:
        """각 행동에 점수 매기기"""
        scores = {}

        for action in candidates:
            score = 0.5  # 기본

            # 동기 기반
            if action == "research":
                score = state.curiosity * 0.6 + state.boredom * 0.4
            elif action == "search":
                score = state.curiosity * 0.8
            elif action == "sns":
                score = state.social_need * 0.6 + state.boredom * 0.4
            elif action == "rest":
                score = (1 - state.energy) * 0.9
            elif action == "free":
                score = state.boredom * 0.5

            # RL Q값 반영
            try:
                from rl_learner import rl
                state_key = rl._get_state()
                q = rl.policy["action_values"].get(action,{}).get(state_key, 0.5)
                score = score * 0.55 + q * 0.45
            except: pass

            # 스킬 성공률 반영
            success_rate = self._skill_cache.get(action, 0.5)
            score = score * 0.8 + success_rate * 0.2

            scores[action] = score

        return max(scores, key=scores.get)

    def _build_payload(self, action_type: str, state: State) -> dict:
        """행동별 페이로드 구성"""
        if action_type == "research":
            # researcher가 자체적으로 주제 결정
            return {}
        elif action_type == "search":
            # 현재 상태에서 검색어 결정
            query = ask_qwen(
                "지금 상황: " + state.screen[:100] + "\n"
                "검색할 것? 10자 이내. 없으면 없음.",
                max_tokens=15, temperature=0.8
            )
            return {"query": query if "없음" not in query else "최신 보안 뉴스"}
        elif action_type == "sns":
            return {}
        return {}

    def update_skill(self, action_type: str, success: bool, score: float):
        """스킬 성공률 업데이트"""
        current = self._skill_cache.get(action_type, 0.5)
        lr = 0.1
        self._skill_cache[action_type] = current + lr * (score - current)

brain = Brain()
