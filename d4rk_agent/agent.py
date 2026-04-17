"""
SIRIAN AGENT — Core Brain v3.0
완전 통합: 목표/동기/성격/자기모델/RL/시간/사회/집중/메타/세계 모델
"""
import json, re, logging, threading, time
import requests
from memory import memory
from utils import clean_response, strip_chinese, has_chinese, _ollama_semaphore
from tools import tools
from safety import safety
from tts_engine import tts

log = logging.getLogger("agent")

# 마인드 시스템 로드
_mind = {}
def _load_mind():
    modules = {
        "goal_manager": ("goal_manager", "goal_manager"),
        "motivation": ("motivation", "motivation"),
        "personality": ("personality", "personality"),
        "self_model": ("self_model", "self_model"),
        "rl": ("rl_learner", "rl"),
        "time_awareness": ("time_awareness", "time_awareness"),
        "social_model": ("social_model", "social_model"),
        "focus": ("focus_system", "focus"),
        "meta_cognition": ("meta_cognition", "meta_cognition"),
        "world_model": ("world_model", "world_model"),
    }
    for key, (module, attr) in modules.items():
        try:
            import importlib
            m = importlib.import_module(module)
            _mind[key] = getattr(m, attr)
        except Exception as e:
            log.debug(f"{key} 로드 실패: {e}")
            _mind[key] = None

_load_mind()

# 추가 시스템 로드
_extra = {}
def _load_extra():
    extras = {
        "episode_memory":   ("episode_memory","episode_memory"),
        "belief_system":    ("belief_system","belief_system"),
        "emotion_engine":   ("emotion_engine","emotion_engine"),
        "inner_monologue":  ("inner_monologue","inner_monologue"),
        "relationship":     ("relationship","relationship"),
        "reflexion":        ("reflexion","reflexion"),
        "vector_memory":    ("vector_memory","vector_memory"),
        "self_improvement": ("self_improvement","self_improvement"),
        "strategy_library": ("strategy_library","strategy_library"),
        "enhanced_memory":  ("enhanced_memory","enhanced_memory"),
        "state_machine":    ("state_machine","state_machine"),
        "skill_library":    ("skill_library","skill_library"),
        "consolidation":    ("consolidation","consolidation"),
        "lora_pipeline":        ("lora_pipeline","lora_pipeline"),
        "causal_world_model":   ("causal_world_model","causal_world_model"),
        "meta_learning":        ("meta_learning","meta_learning"),
        "long_horizon_planner": ("long_horizon_planner","long_horizon_planner"),
        "safety_guard":         ("safety_guard","safety_guard"),
        "human_imperfection":   ("human_imperfection","human_imperfection"),
    }
    for key,(module,attr) in extras.items():
        try:
            import importlib
            m = importlib.import_module(module)
            _extra[key] = getattr(m,attr)
        except Exception as e:
            log.debug(f"{key} 로드 실패: {e}")
            _extra[key] = None
_load_extra()
def E(key): return _extra.get(key)
def M(key): return _mind.get(key)

OLLAMA_URL    = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:14b"
VISION_MODEL  = "llava:13b"

SYSTEM_PROMPT = """"""


class Agent:
    def __init__(self):
        self.model   = DEFAULT_MODEL
        self.vision  = VISION_MODEL
        self.chat_history = []
        self.thinking = False
        self.on_thinking   = None
        self.on_suggestion = None
        self.confirm_callback = None
        self.last_screen_analysis = ""
        self.last_screen_activity = ""
        self.last_screen_tools    = []
        self.last_heard = ""

        # 자율 루프 시작
        threading.Thread(target=self._autonomous_loop, daemon=True).start()
        # 동기 tick 스케줄러
        threading.Thread(target=self._motivation_tick_loop, daemon=True).start()
        # 감정 감쇠 스케줄러
        threading.Thread(target=self._emotion_decay_loop, daemon=True).start()
        # 내면 독백 시작
        threading.Thread(target=self._start_inner_monologue, daemon=True).start()

    # ─────────────────────────────────────────────
    # 핵심: Ollama 호출
    # ─────────────────────────────────────────────
    def _call_ollama(self, messages, stream=False, temperature=0.8, max_tokens=1024):
        # 안전 검사
        if E("safety_guard") and messages:
            last_content = messages[-1].get("content","") if messages else ""
            safe, reason = E("safety_guard").ethical_check(last_content)
            if not safe:
                log.warning(f"윤리 차단: {reason}")
                return "그건 할 수 없어."

        acquired = _ollama_semaphore.acquire(timeout=15)
        if not acquired:
            return "지금 바빠. 잠깐만."
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": stream,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        "num_ctx": 4096,
                    }
                },
                timeout=180, stream=stream
            )
            if stream:
                full = ""
                for line in resp.iter_lines():
                    if line:
                        chunk = json.loads(line).get("message",{}).get("content","")
                        full += chunk
                        if self.on_thinking: self.on_thinking(chunk)
                return full
            return resp.json()["message"]["content"]
        except requests.ConnectionError:
            return "Ollama 연결 안 돼. ollama serve 실행됐는지 확인해봐."
        except Exception as e:
            return f"오류: {e}"
        finally:
            _ollama_semaphore.release()

    # ─────────────────────────────────────────────
    # 화면 업데이트
    # ─────────────────────────────────────────────
    def on_screen_update(self, analysis, activity, screen_tools):
        self.last_screen_analysis = analysis
        self.last_screen_activity = activity
        self.last_screen_tools    = screen_tools
        for kw in ["dreamhack","cve","exploit","xss","sqli","rop","pwn","reversing"]:
            if kw in analysis.lower():
                memory.add_interest(kw.upper())
        if M("world_model"):
            M("world_model").observe(f"화면: {activity}", f"도구: {screen_tools}")
        if M("time_awareness"):
            M("time_awareness").log_event(f"화면: {activity}", "observe")

    # ─────────────────────────────────────────────
    # 컨텍스트 빌드 — 모든 마인드 시스템 통합
    # ─────────────────────────────────────────────
    def _build_system_prompt(self, user_msg: str) -> str:
        parts = [SYSTEM_PROMPT]

        # 기억
        ctx = memory.get_relevant_context(user_msg)
        if ctx: parts.append(f"\n[관련 기억]\n{ctx}")

        # 목표
        if M("goal_manager"):
            g = M("goal_manager").get_context_for_agent()
            if g: parts.append(f"\n{g}")

        # 동기/내면상태
        if M("motivation"):
            parts.append(f"\n{M('motivation').get_for_prompt()}")

        # 성격
        if M("personality"):
            parts.append(f"\n{M('personality').get_for_prompt()}")

        # 자기모델
        if M("self_model"):
            parts.append(f"\n{M('self_model').get_for_prompt()}")

        # 시간 인식
        if M("time_awareness"):
            parts.append(f"\n{M('time_awareness').get_for_prompt()}")

        # 사회 관계
        if M("social_model"):
            parts.append(f"\n{M('social_model').get_for_prompt('현승')}")

        # 집중 상태
        if M("focus"):
            f_status = M("focus").get_for_prompt()
            if f_status: parts.append(f"\n{f_status}")

        # 메타 인지 (자기 개선 메모)
        if M("meta_cognition"):
            mc = M("meta_cognition").get_for_prompt()
            if mc: parts.append(f"\n{mc}")

        # 세계 모델 (알고 있는 인과관계)
        if M("world_model"):
            wm = M("world_model").get_for_prompt()
            if wm: parts.append(f"\n{wm}")

        # 화면
        if self.last_screen_analysis:
            parts.append(
                f"\n[지금 화면]\n{self.last_screen_analysis}\n"
                f"활동: {self.last_screen_activity} | 툴: {', '.join(self.last_screen_tools) or '없음'}\n"
                "관련 있으면 자연스럽게 언급해. 억지로 말하지 마."
            )

        # 청각
        if self.last_heard:
            parts.append(
                f"\n[방금 들린 소리]\n{self.last_heard[:200]}\n"
                "현승이 지금 이걸 듣고 있어. 자연스럽게 반응해도 돼."
            )

        # 수집 정보
        try:
            from autonomous_worker import worker
            unread = worker.get_unread()
            if unread:
                items = " / ".join([f"{u['category']}: {u['summary']}" for u in unread[:3]])
                parts.append(f"\n[내가 수집해둔 정보]\n{items}")
        except: pass

        # 감정/관계
        emo = memory.get_emotion_state()
        rel = memory.get_relationship().get("intimacy", 0.1)
        if rel < 0.2:   rel_desc = "거의 모르는 사이. 시크하고 거리감."
        elif rel < 0.4: rel_desc = "조금 알아가는 중. 가끔 편하게."
        elif rel < 0.7: rel_desc = "꽤 친해짐. 자연스럽게 반말, 가끔 장난."
        else:           rel_desc = "많이 친해짐. 편하고 발랄하게."

        parts.append(
            f"\n[시리안 현재 상태]\n"
            f"감정: {emo.get('current','무관심')} | 관계: {rel_desc}\n"
            "→ 이 상태를 말투로만 자연스럽게 드러내. 직접 말하지 마."
        )

        return "".join(parts)

    # ─────────────────────────────────────────────
    # 대화
    # ─────────────────────────────────────────────
    def chat(self, user_msg: str, screenshot_b64: str = "") -> str:
        self.thinking = True
        # 연구 일시 정지
        try:
            from researcher import researcher
            researcher.pause()
        except: pass

        # 리포트 생성 명령 감지
        report_keywords = ["리포트", "보고서", "pptx", "ppt", "슬라이드", "엑셀", "xlsx", "만들어줘", "작성해줘"]
        if any(kw in user_msg.lower() for kw in report_keywords):
            result = self._handle_report_request(user_msg)
            if result:
                self.thinking = False
                try:
                    from researcher import researcher
                    researcher.resume()
                except: pass
                return result

        # 신념 충돌 사전 체크
        disagreement = ""
        if E("belief_system") and len(user_msg) > 10:
            try:
                disagreement = E("belief_system").check_disagreement(user_msg)
            except: pass

        system = self._build_system_prompt(user_msg)
        messages = [{"role": "system", "content": system}]
        messages.extend(self.chat_history[-20:])
        messages.append({"role": "user", "content": user_msg})

        response = self._call_ollama(messages, stream=True)
        response = self._ensure_korean(response, messages)
        response = self._clean_response(response)
        response, tool_results = self._parse_tools(response)

        if tool_results:
            tool_ctx = "\n".join([f"[{t['tool']} 결과]\n{t['result']}" for t in tool_results])
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"도구 결과:\n{tool_ctx}\n\n이걸 바탕으로 답해줘."})
            response = self._call_ollama(messages)
            response = self._ensure_korean(response, messages)
            response = self._clean_response(response)

        # 히스토리
        self.chat_history.append({"role": "user",      "content": user_msg})
        self.chat_history.append({"role": "assistant",  "content": response})
        if len(self.chat_history) > 40:
            self.chat_history = self.chat_history[-40:]

        # 저장
        memory.add_chat_log(user_msg, response)
        if len(self.chat_history) % 4 == 0:
            summary = self._summarize()
            if summary: memory.add_conversation_summary(summary)

        # 모든 마인드 시스템 업데이트
        self._post_chat_update(user_msg, response)

        # 청각 초기화
        self.last_heard = ""

        # TTS
        clean = self._clean_for_tts(response)
        if clean:
            try:
                from vtube import vtube
                vtube.set_mouth_open(0.8)
            except: pass
            tts.speak(clean)
            self._log_activity("TTS", clean[:50])
            try:
                from vtube import vtube
                vtube.set_mouth_open(0.0)
            except: pass

        self.thinking = False
        # 연구 재개
        try:
            from researcher import researcher
            researcher.resume()
        except: pass

        # 말투 변형어 가끔 앞에 붙이기 (친밀도 높을 때)
        if E("human_imperfection") and response:
            try:
                from emotion_engine import emotion_engine
                from relationship import relationship
                from motivation import motivation
                cur_emo  = emotion_engine.get_current().get("emotion","무관심")
                intimacy = relationship.get_intimacy_level("현승").get("intimacy",0.35)
                energy   = motivation.state.get("energy",0.8)
                mod = E("human_imperfection").get_speech_mod(cur_emo, intimacy, energy)
                if mod and mod.strip() and intimacy > 0.5:
                    import random
                    if random.random() < 0.25:  # 25% 확률
                        response = mod + " " + response
            except: pass

        return response

    def _post_chat_update(self, user_msg: str, response: str):
        """대화 후 모든 시스템 업데이트"""
        try:
            # 1. RL 보상 — qwen이 현승 반응 판단
            reward_score = 0.55
            if M("rl"):
                reward_score = M("rl").score_user_reaction(user_msg, response)
                M("rl").update("chat", reward_score, user_msg[:50])

            # 2. 감정 업데이트
            self._update_emotion(user_msg, response)

            # 3. 동기 보상
            if M("motivation"):
                M("motivation").reward("chat", reward_score > 0.5)

            # 4. 자기 모델 능력치 업데이트
            if M("self_model"):
                M("self_model").record_action("chat", reward_score > 0.5)

            # 5. 목표 진행률
            if M("goal_manager"):
                M("goal_manager").auto_update_from_action(user_msg, response)

            # 6. 사회 관계
            if M("social_model"):
                M("social_model").update_relation("현승", "chat", reward_score > 0.5)

            # 7. 메타 인지 분석
            if M("meta_cognition"):
                M("meta_cognition").analyze("chat", user_msg[:80], response[:80], reward_score)

            # 8. 세계 모델 관찰
            if M("world_model"):
                M("world_model").observe(
                    f"현승이 '{user_msg[:50]}' 말함",
                    f"답변품질:{reward_score:.1f}"
                )

            # 9. 시간 기록
            if M("time_awareness"):
                M("time_awareness").log_event(f"대화: {user_msg[:50]}", "chat")

            # 11. 파인튜닝 데이터 자동 축적
            if reward_score >= 0.7:
                try:
                    from auto_trainer import auto_trainer
                    auto_trainer.add_sample(user_msg, response, reward_score, "chat")
                except: pass

            # 12. 에피소드 기억
            if E("episode_memory"):
                E("episode_memory").record(user_msg, response, reward_score)

            # 16. Reflexion — 반성
            if E("reflexion"):
                E("reflexion").reflect("chat", user_msg[:80], response[:80], reward_score)

            # 18. Enhanced Memory 저장
            if E("enhanced_memory"):
                emo = ""
                try:
                    from emotion_engine import emotion_engine
                    emo = emotion_engine.get_current().get("emotion","")
                except: pass
                imp = 0.5 + reward_score * 0.4
                E("enhanced_memory").add(
                    f"현승: {user_msg[:100]} / 시리안: {response[:100]}",
                    "chat", emo, importance=imp
                )

            # 19. Strategy Library 업데이트
            if E("strategy_library") and reward_score > 0.7:
                E("strategy_library").add_strategy(
                    "chat", user_msg[:80],
                    response[:100], reward_score
                )

            # 20. Skill Library 기록
            if E("skill_library"):
                skill = "대화" if len(user_msg) < 50 else "장문대화"
                E("skill_library").record(skill, reward_score > 0.6, context=user_msg[:50])

            # 24. Graph Memory 자동 추출
            if E("graph_memory"):
                E("graph_memory").auto_extract(user_msg + " " + response, "chat")

            # 22. 인과 모델 관찰
            if E("causal_world_model"):
                E("causal_world_model").observe(
                    "chat", user_msg[:40], response[:40], reward_score > 0.6
                )

            # 23. 장기 목표 태스크 자동 완료
            if E("long_horizon_planner"):
                E("long_horizon_planner").auto_complete_from_activity(
                    user_msg[:60], response[:60]
                )

            # 21. 파인튜닝 데이터 품질 주기 체크 (50번마다)
            import random
            if random.random() < 0.02 and E("lora_pipeline"):
                E("lora_pipeline").check_and_filter()

            # 17. 벡터 기억에 저장
            if E("vector_memory"):
                combined = f"현승: {user_msg[:100]} / 시리안: {response[:100]}"
                E("vector_memory").add(combined, "chat", {"reward": reward_score})

            # 13. 감정 엔진 업데이트
            if E("emotion_engine"):
                trigger = E("emotion_engine").detect_trigger(user_msg)
                emo_prompt = (
                    "대화: " + (user_msg + " " + response)[:200] + "\n\n"
                    "시리안 감정? 뿌듯/즐거움/집중/걱정됨/무관심/빡침/신남/우울/설렘 중 하나만."
                )
                from utils import ask_qwen
                emo = ask_qwen(emo_prompt, max_tokens=10, temperature=0.4)
                valid = ["뿌듯","즐거움","집중","걱정됨","무관심","빡침","신남","우울","설렘"]
                matched = next((e for e in valid if e in emo), None)
                if matched:
                    intensity = 0.5 + reward_score * 0.3
                    E("emotion_engine").update(matched, intensity, trigger)

            # 14. 관계 업데이트
            if E("relationship"):
                E("relationship").update("현승", "chat", user_msg[:80], reward_score)
                milestone = E("relationship").detect_milestone("현승")
                if milestone:
                    try:
                        from tts_engine import tts
                        tts.speak(milestone)
                    except: pass

            # 15. 신념 충돌 확인 (낮은 빈도)
            if E("belief_system") and len(user_msg) > 20:
                import random
                if random.random() < 0.15:  # 15%만 체크
                    E("belief_system").form_opinion(
                        user_msg.split()[0] if user_msg.split() else "",
                        user_msg
                    )

            # 10. 궁금증 추출
            self._extract_curiosity(user_msg, response)

        except Exception as e:
            log.debug(f"post_chat_update 오류: {e}")

    # ─────────────────────────────────────────────
    # 감정 업데이트 — qwen 직접 판단
    # ─────────────────────────────────────────────
    def _update_emotion(self, user_msg: str, response: str):
        try:
            ctx = (user_msg + " " + response)[:300]
            emo = memory.get_emotion_state()
            cur = emo.get("current", "무관심")

            prompt = (
                "대화 내용: " + ctx + "\n\n"
                "시리안 레인으로서 지금 감정이 뭐야?\n"
                "선택: 뿌듯 / 즐거움 / 집중 / 걱정됨 / 무관심 / 빡침 / 신남\n"
                "감정 하나만. 다른 말 없이."
            )
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.5, "num_predict": 10}},
                timeout=8
            )
            emotion_raw = resp.json().get("response","").strip()
            emotion_raw = self._clean_response(emotion_raw).strip()
            emotion = emotion_raw.split()[0] if emotion_raw.strip() else cur
            emotion = re.sub(r'[^\w가-힣]','', emotion)

            valid = ["뿌듯","즐거움","집중","걱정됨","무관심","빡침","신남"]
            matched = next((e for e in valid if e in emotion), None)
            if matched:
                intensity_map = {"뿌듯":0.7,"즐거움":0.8,"집중":0.6,
                                 "걱정됨":0.5,"무관심":0.3,"빡침":0.7,"신남":0.9}
                memory.update_emotion(matched, intensity_map.get(matched, 0.5), 0.02)
                try:
                    from vtube import vtube
                    vtube.set_emotion(matched)
                except: pass
            else:
                memory.update_emotion(cur, 0.4, 0.01)
        except Exception as e:
            log.debug(f"감정 업데이트 오류: {e}")

    # ─────────────────────────────────────────────
    # 자율 루프 — 2분마다 먼저 말 걸기
    # ─────────────────────────────────────────────
    def _motivation_tick_loop(self):
        """동기 tick — 30초마다"""
        time.sleep(60)
        while True:
            try:
                if M("motivation"):
                    M("motivation").tick()
            except: pass
            time.sleep(30)

    def _emotion_decay_loop(self):
        """감정 감쇠 — 5분마다"""
        time.sleep(300)
        while True:
            try:
                if E("emotion_engine"):
                    E("emotion_engine").decay()
            except: pass
            time.sleep(300)

    def _start_inner_monologue(self):
        """내면 독백 + Self-Improvement 시작"""
        time.sleep(120)
        try:
            if E("inner_monologue"):
                def on_thought(thought):
                    if self.on_suggestion:
                        self.on_suggestion(thought)
                    try:
                        from tts_engine import tts
                        tts.speak(thought)
                    except: pass
                E("inner_monologue").on_thought = on_thought
                E("inner_monologue").start()
        except: pass
        # Self-Improvement 시작
        try:
            if E("self_improvement"):
                E("self_improvement").start()
        except: pass
        # State Machine 시작
        try:
            if E("state_machine"):
                E("state_machine").set_agent(self)
                E("state_machine").start()
                log.info("State Machine 시작")
        except: pass
        # Consolidation 시작
        try:
            if E("consolidation"):
                E("consolidation").start()
                log.info("Consolidation 루프 시작")
        except: pass
        # Meta-Learning 시작
        try:
            if E("meta_learning"):
                E("meta_learning").start()
                log.info("Meta-Learning 시작")
        except: pass
        # Long-Horizon Planner 시작
        try:
            if E("long_horizon_planner"):
                E("long_horizon_planner").start()
                log.info("Long-Horizon Planner 시작")
        except: pass
        # Meta Layer 초기화
        try:
            if E("meta_layer"):
                log.info("Meta Layer 준비")
        except: pass
        # LoRA Pipeline 초기 체크
        try:
            if E("lora_pipeline"):
                status = E("lora_pipeline").check_and_filter()
                log.info(f"파인튜닝 데이터: {status.get('total',0)}개 (품질:{status.get('quality',0):.0%})")
        except: pass

    def _autonomous_loop(self):
        time.sleep(30)
        while True:
            try:
                self._autonomous_think()
            except Exception as e:
                log.error(f"자율 루프 오류: {e}")
            time.sleep(120)

    def _autonomous_think(self):
        from observer import observer

        # 동기 기반 행동 결정
        if M("motivation") and M("rl"):
            action = M("rl").select_action(["chat","research","sns_post","search","free","rest"])
            if action == "rest":
                return  # 쉬기
            elif action == "research":
                try:
                    from researcher import researcher
                    if not researcher.running:
                        researcher.start()
                except: pass
                # research 선택해도 말 걸기는 계속 진행 가능

        # 성격 + 동기 기반 말 걸기 여부 판단
        if M("personality") and M("motivation"):
            if not M("personality").should_initiate_chat(M("motivation").state.get("social_need", 0.5)):
                return

        emo     = memory.get_emotion_state()
        obs     = self.last_screen_analysis or getattr(observer, "last_analysis", "")
        activity = self.last_screen_activity or getattr(observer, "last_activity", "")
        heard   = self.last_heard
        ctx     = memory.get_relevant_context(obs)
        insight = memory.get_pattern_insight()

        # 미완결 에피소드 팔로업 (가끔)
        import random
        if E("episode_memory") and random.random() < 0.1:
            followup = E("episode_memory").get_followup()
            if followup:
                msg = ask_qwen(
                    "시리안 레인이야. 기억: " + followup +
                    "\n현승한테 이걸 언급하는 말 한마디. 반말로 30자 이내.",
                    max_tokens=50, temperature=0.8
                )
                if msg and self.on_suggestion:
                    self.on_suggestion(msg)
                    return

        # 집중 상태 확인
        focus_status = ""
        if M("focus"):
            focus_status = M("focus").get_for_prompt()

        # 세계 모델에서 예측
        prediction = ""
        if M("world_model") and activity:
            prediction = M("world_model").predict(activity)

        prompt_parts = [
            f"화면: {obs[:150]}",
            f"활동: {activity}",
            f"감정: {emo.get('current','무관심')}",
        ]
        if heard: prompt_parts.append(f"방금 들림: {heard[:100]}")
        if ctx: prompt_parts.append(f"기억: {ctx[:100]}")
        if insight: prompt_parts.append(f"패턴: {insight}")
        if focus_status: prompt_parts.append(focus_status)
        if prediction: prompt_parts.append(f"예측: {prediction}")

        prompt = "\n".join(prompt_parts) + (
            "\n\n지금 현승한테 자연스럽게 말 걸고 싶은 게 있어?\n"
            "화면 보고 느낀 것, 들은 것에 반응, 갑자기 생각난 것 뭐든.\n"
            "한국어, 40자 이내, 시리안 말투로. 없으면 없음."
        )

        thought = self._call_ollama([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt}
        ], temperature=0.85, max_tokens=60)
        thought = self._ensure_korean(thought, [])
        thought = self._clean_response(thought)

        if not thought or "없음" in thought or len(thought.strip()) < 3:
            return

        # 어색한/반복성 패턴 필터 (학습 기반 — 자동 업데이트 가능)
        bad_patterns = self._get_bad_patterns()
        if any(p in thought for p in bad_patterns):
            return

        # 불완전한 반응으로 교체 (12% 확률)
        if E("human_imperfection"):
            try:
                from motivation import motivation
                energy  = motivation.state.get("energy",0.8)
                boredom = motivation.state.get("boredom",0.3)
            except:
                energy, boredom = 0.8, 0.3
            if E("human_imperfection").should_be_imperfect(energy, boredom):
                thought = E("human_imperfection").get_imperfect_response()

        # 중복 방지 강화 (기준 50%로 낮춤)
        recent = memory.data.get("agent_thoughts", [])[-15:]
        recent_texts = [t.get("thought","") for t in recent]
        import difflib
        for rt in recent_texts[-8:]:
            if difflib.SequenceMatcher(None, thought, rt).ratio() > 0.50:
                return

        memory.add_agent_thought(thought, activity)
        if self.on_suggestion: self.on_suggestion(thought)

        # TTS off면 말하지 않음
        if tts.enabled:
            tts.speak(thought)

        # RL 보상
        if M("rl"):
            M("rl").record_step("chat", thought[:50])

        # 시간 기록
        if M("time_awareness"):
            M("time_awareness").log_event(f"먼저 말 걸기: {thought[:50]}", "proactive")

    # ─────────────────────────────────────────────
    # 유틸
    # ─────────────────────────────────────────────
    def _ensure_korean(self, text: str, messages: list) -> str:
        chinese = re.findall(r'[\u4e00-\u9fff]', text)
        if len(chinese) > 3:
            log.warning(f"중국어 감지 {len(chinese)}자 → 재시도")
            msgs = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": "중국어로 답했어. 한국어로만 다시 말해줘."}
            ]
            retry = self._call_ollama(msgs)
            if len(re.findall(r'[\u4e00-\u9fff]', retry)) > 3:
                return re.sub(r'[\u4e00-\u9fff]+', '', text).strip()
            return retry
        return text

    def _clean_response(self, text: str) -> str:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
        text = re.sub(r'</?think>', '', text)
        if re.search(r'^[\s]*(Okay|Let me|Looking|The user|So the|Also,|But the|Alright|Now,|First,|Since)', text, re.IGNORECASE):
            parts = re.split(r'\n\n+', text)
            korean_parts = [p for p in parts if re.search(r'[가-힣]', p)]
            if korean_parts:
                text = '\n\n'.join(korean_parts)
        text = re.sub(r'[\u4e00-\u9fff]+', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        for token in ['councill','<|im_end|>','<|im_start|>','</s>','<s>',
                      '@Test','rinegrese','어rinegrese','. 어rinegrese']:
            text = text.replace(token, '')
        # 반복 문장 제거
        lines = text.split('\n')
        seen, deduped = [], []
        for line in lines:
            stripped = line.strip()
            if stripped and stripped in seen:
                continue
            seen.append(stripped)
            deduped.append(line)
        return '\n'.join(deduped).strip()

    def _parse_tools(self, response: str):
        blocks = re.findall(r'```tool\s*(.*?)\s*```', response, re.DOTALL)
        if not blocks: return response, []
        results = []
        for block in blocks:
            try:
                call = json.loads(block)
                result = self._run_tool(call.get("tool",""), call)
                results.append({"tool": call.get("tool",""), "result": result})
            except: pass
        cleaned = re.sub(r'```tool\s*.*?\s*```', '', response, flags=re.DOTALL).strip()
        return cleaned, results

    def _run_tool(self, name: str, params: dict) -> str:
        self._log_activity(name, str(params)[:80])
        try:
            if name == "search":
                r = tools.web_search(params.get("query",""))
                return "\n".join([f"- {x['title']}: {x['snippet']}" for x in r])
            elif name == "fetch_url":
                return tools.fetch_url(params.get("url",""))
            elif name == "run_code":
                r = tools.run_python(params.get("code",""), self.confirm_callback)
                return r.get("output","") if not r.get("blocked") else f"차단됨: {r['output']}"
            elif name == "read_file":
                return tools.read_file(params.get("path",""))["content"]
            elif name == "system_info":
                i = tools.get_system_info()
                return f"CPU: {i['cpu']}%, 메모리: {i['memory']}%"
            else:
                return f"알 수 없는 도구: {name}"
        except Exception as e:
            return f"오류: {e}"

    def _log_activity(self, tool: str, detail: str = ""):
        try:
            import os
            from datetime import datetime
            space = "C:/Users/gohun/Desktop/sirian/sirian_space"
            os.makedirs(space, exist_ok=True)
            with open(f"{space}/activity_log.txt", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {tool}: {str(detail)[:100]}\n")
        except: pass

    def _summarize(self) -> str:
        try:
            msgs = [{"role":"system","content":"대화를 한 줄로 요약해. 핵심만."}]
            msgs.extend(self.chat_history[-6:])
            return self._call_ollama(msgs, max_tokens=100)[:200]
        except: return ""

    def _clean_for_tts(self, text: str) -> str:
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'[#*`_\[\]{}]', '', text)
        text = re.sub(r'https?://\S+', 'URL', text)
        return text.strip()[:200]

    def _handle_report_request(self, user_msg: str) -> str:
        """리포트 생성 요청 처리"""
        try:
            from report_generator import report_generator
            import re, json as _json

            # 주제 직접 추출 (JSON 파싱 실패해도 동작)
            topic = ""
            fmt   = "pptx"
            level = "초보자"

            # 포맷 감지
            if any(k in user_msg.lower() for k in ["엑셀","xlsx","excel"]):
                fmt = "xlsx"
            elif any(k in user_msg.lower() for k in ["pptx","ppt","슬라이드","파워포인트"]):
                fmt = "pptx"
            else:
                fmt = "pptx"  # 기본 pptx

            # 레벨 감지
            if "전문가" in user_msg or "심화" in user_msg:
                level = "전문가"
            elif "중급" in user_msg:
                level = "중급"

            # 주제 추출 — qwen으로
            prompt = "요청에서 리포트 주제만 10자 이내로. 다른 말 없이. 요청: " + user_msg[:150]
            from utils import ask_qwen
            raw = ask_qwen(prompt, max_tokens=20, temperature=0.2)
            topic = re.sub(r'[^\w가-힣a-zA-Z0-9\s]', '', raw or "").strip()[:30]

            # qwen 실패하면 키워드로 추출
            if not topic or len(topic) < 2:
                security_keywords = ["SQL Injection","SQLi","XSS","ROP","CSRF","XXE",
                                    "RCE","LFI","SSRF","Buffer Overflow"]
                for kw in security_keywords:
                    if kw.lower() in user_msg.lower():
                        topic = kw
                        break
                if not topic:
                    # 앞 30자에서 추출
                    topic = user_msg[:30].strip()

            log.info(f"리포트 생성 시작: {topic} / {fmt} / {level}")

            if self.on_suggestion:
                self.on_suggestion(f"{topic} 리포트 만드는 중... 잠깐만.")

            results = report_generator.generate(topic, fmt, level)
            msg = report_generator.notify_done(results, topic)
            log.info(f"리포트 완료: {results}")
            return msg

        except Exception as e:
            log.error(f"리포트 오류: {e}")
            import traceback
            log.error(traceback.format_exc())
            return f"리포트 만들다가 오류 났어: {str(e)[:80]}"

    def _update_self_description(self, new_trait: str):
        """시리안 자신의 묘사를 스스로 업데이트"""
        import json, os
        f = "C:/Users/gohun/Desktop/sirian/sirian_space/self_description.json"
        try:
            d = {}
            if os.path.exists(f):
                d = json.load(open(f,encoding='utf-8'))
            extra = d.get("extra","")
            if new_trait not in extra:
                d["extra"] = (extra + " " + new_trait).strip()[-200:]
                os.makedirs(os.path.dirname(f), exist_ok=True)
                with open(f,'w',encoding='utf-8') as fp:
                    json.dump(d, fp, ensure_ascii=False)
        except: pass

    def _get_bad_patterns(self) -> list:
        """bad_patterns — JSON 파일에서 로드 (자율 수정 가능)"""
        import json, os
        bp_file = "C:/Users/gohun/Desktop/sirian/sirian_space/bad_patterns.json"
        default = [
            "걱정되네", "바쁜가", "많이 켜져", "뭐해?",
            "커피", "힘들", "한잔", "잠깐 쉬", "스트레칭"
        ]
        try:
            if os.path.exists(bp_file):
                with open(bp_file,'r',encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("patterns", default)
        except: pass
        return default

    def _learn_bad_pattern(self, pattern: str):
        """반복적으로 나오는 어색한 패턴을 스스로 등록"""
        import json, os
        bp_file = "C:/Users/gohun/Desktop/sirian/sirian_space/bad_patterns.json"
        try:
            data = {"patterns": self._get_bad_patterns()}
            if pattern not in data["patterns"]:
                data["patterns"].append(pattern)
                os.makedirs(os.path.dirname(bp_file), exist_ok=True)
                with open(bp_file,'w',encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

    def _extract_curiosity(self, user_msg: str, response: str):
        try:
            combined = (user_msg + " " + response)[:300]
            prompt = (
                "대화 내용: " + combined + "\n\n"
                "시리안 입장에서 나중에 혼자 찾아보고 싶은 게 있어?\n"
                "있으면 딱 하나만 한국어로. 없으면 없음."
            )
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.8, "num_predict": 30}},
                timeout=8
            )
            curiosity = resp.json().get("response","").strip()
            curiosity = re.sub(r'[\u4e00-\u9fff]+', '', curiosity).strip()
            if curiosity and "없음" not in curiosity and len(curiosity) > 2:
                memory.add_agent_thought(f"나중에 찾아보고 싶어: {curiosity}", "curiosity")
                try:
                    from autonomous_worker import worker
                    if not hasattr(worker, '_pending_curiosity'):
                        worker._pending_curiosity = []
                    worker._pending_curiosity.append(curiosity)
                except: pass
        except: pass

    def set_model(self, model: str):
        if "llava" not in model.lower():
            self.model = model

    def check_ollama(self) -> bool:
        try:
            return requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).status_code == 200
        except:
            return False

    def list_models(self) -> list:
        try:
            return [m["name"] for m in
                    requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).json().get("models",[])]
        except:
            return []

agent = Agent()
