"""
D4RK AGENT — Main Server
FastAPI + WebSocket으로 UI와 통신
"""
import asyncio, json, logging, os, threading, time
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("main")

app = FastAPI()

# Live2D 모델 파일 서빙
from fastapi.staticfiles import StaticFiles
import os
MODEL_DIR = r"C:/Users/gohun/Desktop/sirian/全-中文版"
LIVE2D_DIR = os.path.join(os.path.dirname(__file__), "live2d")
if os.path.exists(MODEL_DIR):
    app.mount("/model", StaticFiles(directory=MODEL_DIR), name="model")
if os.path.exists(LIVE2D_DIR):
    app.mount("/live2d", StaticFiles(directory=LIVE2D_DIR), name="live2d")
    log.info(f"Live2D SDK 서빙: {LIVE2D_DIR}")

# ── 메인 이벤트 루프 (스레드에서 접근용) ──
_main_loop: asyncio.AbstractEventLoop = None

# ── WebSocket 연결 관리 ──
connected_clients: list[WebSocket] = []

async def broadcast(data: dict):
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_text(json.dumps(data, ensure_ascii=False))
        except:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)

def send_to_ui(data: dict):
    """동기 컨텍스트에서 UI로 메시지 전송"""
    global _main_loop
    try:
        if _main_loop and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(data), _main_loop)
    except Exception as e:
        log.debug(f"send_to_ui 오류: {e}")

# ── 에이전트 초기화 ──
def init_agent():
    from agent import agent
    from observer import observer
    from tts_engine import tts

    # 콜백 설정
    def on_observation(obs_data):
        send_to_ui({
            "type": "observation",
            "activity": obs_data["activity"],
            "tools": obs_data["tools"],
            "analysis": obs_data["analysis"],
            "insight": obs_data.get("insight", "")
        })

    def on_suggestion(text):
        send_to_ui({
            "type": "suggestion",
            "text": text
        })

    def on_thinking(chunk):
        send_to_ui({"type": "thinking", "chunk": chunk})

    def confirm_callback(message):
        # UI에 확인 요청 전송 (간단히 True 반환 — 추후 실제 팝업으로 개선)
        send_to_ui({"type": "confirm_request", "message": message})
        return True  # 기본 허용 (실제론 유저 응답 대기)

    agent.on_suggestion = on_suggestion
    agent.on_thinking = on_thinking
    agent.confirm_callback = confirm_callback

    observer.on_observation = on_observation
    observer.on_screen_update = agent.on_screen_update
    observer.start()

    # 자율 워커
    try:
        from autonomous_worker import worker
        def on_collected(entry):
            send_to_ui({
                "type": "auto_collected",
                "category": entry["category"],
                "summary": entry["summary"],
                "time": entry["time"],
                "unread": len(worker.get_unread())
            })
        worker.agent_ref = agent
        worker.on_collected = on_collected
        worker.start()
        log.info("자율 워커 시작")
    except Exception as e:
        log.warning(f"자율 워커 생략: {e}")

    log.info("D4RK AGENT 초기화 완료")

    # Away Mode 초기화
    def init_away_mode():
        try:
            from away_mode import away_mode
            def on_away():
                send_to_ui({"type":"away_status","is_away":True})
                send_to_ui({"type":"agent_msg","text":"외출 모드 시작. 열심히 하고 있을게."})
            def on_return(duration):
                send_to_ui({"type":"away_status","is_away":False})
            away_mode.on_away   = on_away
            away_mode.on_return = on_return
            # 이미 외출 중이었으면 복원
            if away_mode.is_away:
                away_mode._boost_autonomous()
            log.info("Away Mode 초기화 완료")
        except Exception as e:
            log.warning(f"Away Mode 오류: {e}")
    threading.Thread(target=init_away_mode, daemon=True).start()

    # 고급 시스템 초기화
    def init_advanced():
        try:
            from graph_memory import graph_memory
            s = graph_memory.get_stats()
            log.info(f"Graph Memory: {s['nodes']}노드 {s['edges']}엣지")
        except Exception as e:
            log.warning(f"Graph Memory 오류: {e}")
        try:
            from meta_layer import meta_layer
            log.info("Meta Layer 준비")
        except Exception as e:
            log.warning(f"Meta Layer 오류: {e}")
        try:
            from error_recovery import error_recovery
            log.info("Error Recovery 준비")
        except Exception as e:
            log.warning(f"Error Recovery 오류: {e}")
        try:
            import logging as _logging
            _logging.getLogger('sentence_transformers').setLevel(_logging.WARNING)
            _logging.getLogger('httpx').setLevel(_logging.WARNING)
            _logging.getLogger('huggingface_hub').setLevel(_logging.WARNING)
            log.info("불필요 로그 억제")
        except: pass
    threading.Thread(target=init_advanced, daemon=True).start()

    # Phase 3 시스템 초기화
    def init_phase3():
        try:
            from causal_world_model import causal_world_model
            log.info(f"Causal World Model: {len(causal_world_model.data.get('causal_graph',[]))}개 규칙")
        except Exception as e:
            log.warning(f"Causal World Model 오류: {e}")
        try:
            from long_horizon_planner import long_horizon_planner
            active = long_horizon_planner.get_active_goals()
            log.info(f"Long-Horizon 목표: {len(active)}개")
        except Exception as e:
            log.warning(f"Long-Horizon Planner 오류: {e}")
        try:
            from safety_guard import safety_guard
            log.info("Safety Guard 초기화 완료")
        except Exception as e:
            log.warning(f"Safety Guard 오류: {e}")
    threading.Thread(target=init_phase3, daemon=True).start()

    # Phase 2 시스템 초기화
    def init_phase2():
        try:
            from skill_library import skill_library
            log.info(f"Skill Library: {len(skill_library.data.get('skills',{}))}개 스킬")
        except Exception as e:
            log.warning(f"Skill Library 오류: {e}")
        try:
            from lora_pipeline import lora_pipeline
            status = lora_pipeline.check_and_filter()
            log.info(f"LoRA 데이터: {status.get('total',0)}개")
        except Exception as e:
            log.warning(f"LoRA Pipeline 오류: {e}")
    threading.Thread(target=init_phase2, daemon=True).start()

    # Phase 1 시스템 초기화
    def init_phase1():
        try:
            from enhanced_memory import enhanced_memory
            enhanced_memory.sync_from_all()
            log.info("Enhanced Memory 동기화 완료")
        except Exception as e:
            log.warning(f"Enhanced Memory 오류: {e}")
        try:
            from strategy_library import strategy_library
            log.info(f"Strategy Library 로드: {len(strategy_library.data.get('strategies',[]))}개")
        except Exception as e:
            log.warning(f"Strategy Library 오류: {e}")
        try:
            from state_machine import state_machine
            log.info("State Machine 준비")
        except Exception as e:
            log.warning(f"State Machine 오류: {e}")
    threading.Thread(target=init_phase1, daemon=True).start()

    # Multi-Agent System 시작
    def init_multi_agent():
        try:
            from multi_agent import multi_agent
            multi_agent.start()
            log.info("Multi-Agent System 시작")
        except Exception as e:
            log.warning(f"Multi-Agent 오류: {e}")
    threading.Thread(target=init_multi_agent, daemon=True).start()

    # Central Controller 시작
    def init_central_controller():
        try:
            from central_controller import central_controller
            central_controller.set_agent(agent_instance)
            central_controller.start()
            log.info("Central Controller 시작")
        except Exception as e:
            log.warning(f"Central Controller 오류: {e}")
    threading.Thread(target=init_central_controller, daemon=True).start()

    # 새 인간화 시스템 초기화
    def init_human_systems():
        try:
            from episode_memory import episode_memory
            from belief_system import belief_system
            from emotion_engine import emotion_engine
            from inner_monologue import inner_monologue
            from relationship import relationship
            log.info("인간화 시스템 초기화 완료")
        except Exception as e:
            log.warning(f"인간화 시스템 오류: {e}")
    threading.Thread(target=init_human_systems, daemon=True).start()

    # 새 모듈 초기화 (클립보드, 토스트, 날씨)
    def init_extras():
        try:
            from clipboard_monitor import clipboard
            def on_clipboard(msg):
                send_to_ui({"type":"agent_msg","text":msg})
                try:
                    from tts_engine import tts
                    tts.speak(msg[:80])
                except: pass
            clipboard.on_found = on_clipboard
            clipboard.start()
            log.info("클립보드 모니터 시작")
        except Exception as e:
            log.debug(f"클립보드 생략: {e}")

        try:
            from weather import weather_checker
            def on_weather(msg):
                send_to_ui({"type":"agent_msg","text":msg})
            weather_checker.on_weather = on_weather
            weather_checker.start()
            log.info("날씨 체커 시작")
        except Exception as e:
            log.debug(f"날씨 생략: {e}")

        try:
            from auto_trainer import auto_trainer
            log.info(f"파인튜닝 데이터: {auto_trainer.get_count()}개")
        except: pass

    threading.Thread(target=init_extras, daemon=True).start()

    # 마인드 시스템 초기화
    def init_mind_systems():
        try:
            from time_awareness import time_awareness
            from social_model import social_model
            from focus_system import focus
            from meta_cognition import meta_cognition
            from world_model import world_model
            log.info("마인드 시스템 초기화 완료")

            # 하루 마무리 + 주기 작업 스케줄러
            def daily_scheduler():
                import time as _time
                from datetime import datetime as _dt
                _goal_counter = 0
                while True:
                    _time.sleep(60)
                    now = _dt.now()
                    _goal_counter += 1

                    # 오전 4시에 하루 요약
                    if now.hour == 4 and now.minute < 2:
                        try:
                            time_awareness.end_of_day_summary()
                            from self_model import self_model
                            self_model.reflect()
                            log.info("하루 마무리 완료")
                        except: pass

                    # 1시간마다 enhanced_memory 동기화
                    if _goal_counter % 60 == 0:
                        try:
                            from enhanced_memory import enhanced_memory
                            enhanced_memory.sync_from_all()
                        except: pass

                    # 6시간마다 학습 데이터 정리 + lora 체크
                    if _goal_counter % 360 == 0:
                        try:
                            from learning_system import learning_system
                            learning_system.cleanup()
                        except: pass
                        try:
                            from rl_learner import rule_engine
                            rule_engine.analyze_and_generate()
                        except: pass
                        try:
                            from lora_pipeline import lora_pipeline
                            lora_pipeline.check_and_filter()
                        except: pass

                    # 30분마다 단기 목표 자동 생성
                    if _goal_counter % 30 == 0:
                        try:
                            from goal_manager import goal_manager
                            from memory import memory
                            ctx = memory.get_context_summary()
                            goal_manager.auto_generate_short_term(ctx)
                        except: pass

            threading.Thread(target=daily_scheduler, daemon=True).start()
        except Exception as e:
            log.warning(f"마인드 시스템 오류: {e}")
    threading.Thread(target=init_mind_systems, daemon=True).start()

    # 마스토돈 연동
    def init_mastodon():
        try:
            from mastodon_client import mastodon
            def on_mastodon_msg(msg):
                send_to_ui({"type": "agent_msg", "text": msg})
            mastodon.on_message = on_mastodon_msg
            mastodon.start()
            log.info("마스토돈 시작")
        except Exception as e:
            log.warning(f"마스토돈 생략: {e}")
    threading.Thread(target=init_mastodon, daemon=True).start()

    # 자율 연구 모듈
    def init_researcher():
        try:
            from researcher import researcher
            def on_research_msg(msg):
                send_to_ui({"type": "agent_msg", "text": msg})
            researcher.on_message = on_research_msg
            researcher.start()
            log.info("자율 연구 시작")
        except Exception as e:
            log.warning(f"연구 모듈 생략: {e}")
    threading.Thread(target=init_researcher, daemon=True).start()

    # VTube Studio 연동
    def init_vtube():
        try:
            from vtube import vtube
            vtube.start()
            log.info("VTube Studio 연동 시작")
        except Exception as e:
            log.warning(f"VTube 생략: {e}")
    threading.Thread(target=init_vtube, daemon=True).start()

    # 청각 시스템 — 백그라운드에서 초기화
    def init_ear():
        global _last_heard
        try:
            from ear import ear
            def on_heard(text):
                global _last_heard, agent_instance
                _last_heard = text
                send_to_ui({"type": "heard", "text": text})
                if agent_instance:
                    agent_instance.last_heard = text
            ear.on_heard = on_heard
            ear.start()
        except Exception as e:
            log.warning(f"청각 생략: {e}")
    threading.Thread(target=init_ear, daemon=True).start()

    return agent

agent_instance = None
_last_heard = ""

@app.get("/visualizer", response_class=HTMLResponse)
async def get_visualizer():
    path = os.path.join(os.path.dirname(__file__), "visualizer.html")
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def collect_viz_data() -> dict:
    """시각화용 데이터 수집"""
    data = {}
    # 감정
    try:
        from emotion_engine import emotion_engine
        emo = emotion_engine.get_current()
        from relationship import relationship
        rel = relationship.get_intimacy_level("현승")
        data["emotion"] = {
            "current":   emo.get("emotion","—"),
            "intensity": emo.get("intensity",0.5),
            "baseline":  emo.get("baseline","—"),
            "intimacy":  rel.get("intimacy",0.35),
        }
    except: data["emotion"] = {}

    # 동기
    try:
        from motivation import motivation
        s = motivation.state
        data["motivation"] = {
            "energy":      s.get("energy",0.5),
            "curiosity":   s.get("curiosity",0.5),
            "boredom":     s.get("boredom",0.3),
            "social_need": s.get("social_need",0.4),
        }
    except: data["motivation"] = {}

    # 기억
    try:
        from vector_memory   import vector_memory
        from episode_memory  import episode_memory
        from enhanced_memory import enhanced_memory
        from graph_memory    import graph_memory
        from strategy_library import strategy_library
        import os as _os
        train_f = r"C:/Users/gohun/Desktop/sirian/d4rk_agent/sirian_train.jsonl"
        train_c = sum(1 for _ in open(train_f, encoding='utf-8')) if _os.path.exists(train_f) else 0
        data["memory"] = {
            "vector":   len(vector_memory.entries),
            "episode":  len(episode_memory.data.get("episodes",[])),
            "enhanced": len(enhanced_memory.entries),
            "graph":    graph_memory.get_stats()["nodes"],
            "strategy": len(strategy_library.data.get("strategies",[])),
            "finetune": train_c,
        }
    except: data["memory"] = {}

    # State Machine
    try:
        from state_machine import state_machine
        from away_mode import away_mode
        from focus_system import focus
        from researcher import researcher
        from meta_layer import meta_layer
        data["state_machine"] = {
            "current_state": state_machine.state,
            "cycle":         state_machine.cycle,
            "perf_trend":    meta_layer._get_trend(),
            "is_away":       away_mode.is_away,
            "focus":         (focus.current_focus or "")[:30],
            "research_topic": researcher.current_topic[:30] if researcher.current_topic else "",
        }
    except: data["state_machine"] = {}

    # RL
    try:
        from rl_learner import rl, rule_engine
        from causal_world_model import causal_world_model
        av = rl.policy.get("action_values",{})
        action_avg = {}
        for action, state_scores in av.items():
            vals = list(state_scores.values())
            if vals: action_avg[action] = round(sum(vals)/len(vals),2)
        data["rl"] = {
            "episodes":        rl.policy.get("total_episodes",0),
            "action_values":   action_avg,
            "rules":           len(rule_engine.rules.get("rules",[])),
            "causal_accuracy": causal_world_model.data.get("accuracy",0.5),
        }
    except: data["rl"] = {}

    # 스킬
    try:
        from skill_library import skill_library
        sk = skill_library.data.get("skills",{})
        data["skills"] = {
            "levels":   {k:round(v.get("level",0.5),2) for k,v in sk.items()},
            "mastered": skill_library.data.get("mastered",[]),
        }
    except: data["skills"] = {}

    # 목표
    try:
        from goal_manager import goal_manager
        from long_horizon_planner import long_horizon_planner
        data["goals"] = {
            "short": [{"goal":g["goal"]} for g in goal_manager.get_active_goals()[:3]],
            "long":  [{"goal":g["goal"],"progress":g.get("progress",0)}
                     for g in long_horizon_planner.get_active_goals()[:2]],
        }
    except: data["goals"] = {}

    # 인과관계
    try:
        from causal_world_model import causal_world_model
        data["causal"] = causal_world_model.data.get("causal_graph",[])[:5]
    except: data["causal"] = []

    # 시스템
    try:
        from reflexion import reflexion
        from error_recovery import error_recovery
        from world_model import world_model
        from multi_agent import multi_agent
        data["system"] = {
            "rl_rules":      len(reflexion.data.get("strategies",[])),
            "reflexions":    len(reflexion.data.get("reflections",[])),
            "world_nodes":   len(world_model.data.get("causal_rules",[])),
            "finetune_count": data.get("memory",{}).get("finetune",0),
            "errors":        sum(error_recovery._error_counts.values()),
            "agent_cycles":  multi_agent._task_queue.__len__() if hasattr(multi_agent,'_task_queue') else 0,
        }
    except: data["system"] = {}

    # Multi-Agent 큐
    try:
        from multi_agent import multi_agent
        data["agent_queue"] = [{"goal":t["goal"]} for t in multi_agent._task_queue[:3]]
    except: data["agent_queue"] = []

    # 성능 추세
    try:
        from meta_layer import meta_layer
        data["performance"] = meta_layer.data.get("performance_trend",[])[-20:]
    except: data["performance"] = []

    return data

# Visualizer 전용 WebSocket
viz_clients: list = []

@app.websocket("/ws/visualizer")
async def viz_websocket(websocket: WebSocket):
    await websocket.accept()
    viz_clients.append(websocket)
    try:
        # 연결 즉시 전체 데이터 전송
        await websocket.send_text(json.dumps({
            "type": "viz_data",
            "data": collect_viz_data()
        }, ensure_ascii=False))
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
                if data.get("type") == "request_viz_data":
                    await websocket.send_text(json.dumps({
                        "type": "viz_data",
                        "data": collect_viz_data()
                    }, ensure_ascii=False))
            except: pass
    except WebSocketDisconnect:
        viz_clients.remove(websocket)
    except:
        if websocket in viz_clients:
            viz_clients.remove(websocket)

# 5초마다 viz 클라이언트에 자동 푸시
async def viz_push_loop():
    while True:
        await asyncio.sleep(5)
        if viz_clients:
            try:
                payload = json.dumps({
                    "type": "viz_update",
                    "data": collect_viz_data()
                }, ensure_ascii=False)
                dead = []
                for ws in viz_clients:
                    try: await ws.send_text(payload)
                    except: dead.append(ws)
                for ws in dead:
                    viz_clients.remove(ws)
            except: pass

@app.on_event("startup")
async def startup():
    global agent_instance, _main_loop
    _main_loop = asyncio.get_event_loop()
    agent_instance = init_agent()
    log.info("서버 시작")

# ── WebSocket 엔드포인트 ──
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    log.info("클라이언트 연결됨")

    # 초기 상태 즉시 전송 (blocking 없음)
    try:
        await websocket.send_text(json.dumps({
            "type": "init",
            "ollama_ok": True,
            "models": ["qwen2.5:14b"],
            "memory_summary": ""
        }, ensure_ascii=False))
    except: pass

    # ollama 백그라운드 체크
    async def bg_check():
        await asyncio.sleep(2)
        try:
            ok = agent_instance.check_ollama()
            models = [m for m in agent_instance.list_models() if "llava" not in m.lower()]
            send_to_ui({"type":"init","ollama_ok":ok,"models":models or ["qwen2.5:14b"],"memory_summary":""})
        except: pass
    asyncio.create_task(bg_check())

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            await handle_message(msg, websocket)
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        log.info("클라이언트 연결 해제")

async def handle_message(msg: dict, ws: WebSocket):
    mtype = msg.get("type", "")

    if mtype == "chat":
        user_text = msg.get("text", "")
        if not user_text.strip():
            return
        try:
            from autonomous_worker import worker
            worker.user_active()
        except: pass
        await ws.send_text(json.dumps({"type": "user_msg", "text": user_text}, ensure_ascii=False))

        # 에이전트 응답 (스레드에서 실행)
        loop = asyncio.get_running_loop()
        def run_chat():
            from observer import observer
            screenshot = observer.last_screenshot_b64
            response = agent_instance.chat(user_text, screenshot)
            try:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(json.dumps({"type": "agent_msg", "text": response}, ensure_ascii=False)),
                    loop
                )
            except Exception as e:
                log.error(f"응답 전송 오류: {e}")
        def run_chat_and_update():
            from observer import observer
            screenshot = observer.last_screenshot_b64
            response = agent_instance.chat(user_text, screenshot)
            try:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(json.dumps({"type": "agent_msg", "text": response}, ensure_ascii=False)),
                    loop
                )
            except Exception as e:
                log.error(f"응답 전송 오류: {e}")
            # 감정 상태 업데이트 전송
            try:
                from memory import memory
                rel = memory.get_relationship()
                emo = memory.get_emotion()
                send_to_ui({
                    "type": "emotion_update",
                    "emotion": emo.get("current", "무관심"),
                    "intensity": emo.get("intensity", 0.3),
                    "intimacy": rel.get("intimacy", 0.1)
                })
            except:
                pass
        threading.Thread(target=run_chat_and_update, daemon=True).start()

    elif mtype == "force_capture":
        from observer import observer
        observer.force_capture()
        await ws.send_text(json.dumps({"type": "status", "text": "화면 즉시 캡처 중..."}, ensure_ascii=False))

    elif mtype == "set_model":
        m = msg.get("model", "qwen2.5:14b")
        agent_instance.set_model(m)
        await ws.send_text(json.dumps({"type": "status", "text": f"채팅 모델: {agent_instance.model} | 화면분석: llava:13b (자동)"}, ensure_ascii=False))

    elif mtype == "tts_test":
        from tts_engine import tts
        tts.test()
        await ws.send_text(json.dumps({"type": "status", "text": "TTS 테스트 중..."}, ensure_ascii=False))

    elif mtype == "get_safety_log":
        from safety import safety
        await ws.send_text(json.dumps({
            "type": "safety_log",
            "log": safety.get_log(30)
        }, ensure_ascii=False))

    elif mtype == "get_memory":
        from memory import memory
        rel = memory.get_relationship()
        await ws.send_text(json.dumps({
            "type": "memory_data",
            "summary": memory.get_context_summary(),
            "observations": memory.get_recent_observations(10),
            "thoughts": memory.data.get("agent_thoughts", [])[-10:],
            "emotion": memory.get_emotion(),
            "intimacy": rel["intimacy"]
        }, ensure_ascii=False))

    elif mtype == "set_api_key":
        key = msg.get("key", "")
        voice = msg.get("voice_id", "")
        if key:
            import os as _os
            _os.environ["ELEVENLABS_API_KEY"] = key
            if voice:
                _os.environ["ELEVENLABS_VOICE_ID"] = voice
            with open(".env", "a", encoding="utf-8") as f:
                f.write(f"\nELEVENLABS_API_KEY={key}\n")
                if voice:
                    f.write(f"ELEVENLABS_VOICE_ID={voice}\n")
            from tts_engine import tts
            tts.reinit(key, voice)
            send_to_ui({"type": "status", "text": "ElevenLabs API 키 저장됨 ✓"})

    elif mtype == "set_interval":
        from observer import observer
        import time as _time
        secs = max(5, min(60, int(msg.get("seconds", 20))))
        observer.interval = secs
        # 루프 재시작
        observer.running = False
        _time.sleep(0.3)
        observer.running = True
        _t = threading.Thread(target=observer._loop, daemon=True)
        _t.start()
        await ws.send_text(json.dumps({"type":"status","text":f"관찰 간격 {secs}초로 변경됨"}, ensure_ascii=False))

    elif mtype == "tts_on":
        try:
            from tts_engine import tts
            tts.enabled = True
            send_to_ui({"type":"tts_status","enabled":True})
            send_to_ui({"type":"agent_msg","text":"TTS 켰어."})
        except: pass

    elif mtype == "tts_off":
        try:
            from tts_engine import tts
            tts.enabled = False
            send_to_ui({"type":"tts_status","enabled":False})
            send_to_ui({"type":"agent_msg","text":"TTS 껐어."})
        except: pass

    elif mtype == "set_away":
        try:
            from away_mode import away_mode
            away_mode.set_away()
            send_to_ui({"type":"away_status","is_away":True})
            send_to_ui({"type":"agent_msg","text":"알겠어. 잘 다녀와."})
        except Exception as e:
            send_to_ui({"type":"agent_msg","text":f"오류: {e}"})

    elif mtype == "set_return":
        try:
            from away_mode import away_mode
            away_mode.set_return()
            send_to_ui({"type":"away_status","is_away":False})
        except Exception as e:
            send_to_ui({"type":"agent_msg","text":f"오류: {e}"})

    elif mtype == "toast":
        try:
            from toast_notifier import toast
            toast.sirian_notify(data.get("message",""))
        except: pass

    elif mtype == "sns_post_done":
        # SNS 포스팅 완료 보상
        try:
            from rl_learner import rl
            from motivation import motivation
            content = data.get("content","")
            score = rl.score_sns_post(content)
            rl.update("sns_post", score, content[:50])
            motivation.reward("sns", True)
            from time_awareness import time_awareness
            time_awareness.log_event(f"마스토돈 포스팅: {content[:50]}", "sns")
        except: pass

    elif mtype == "sns_on":
        try:
            from mastodon_client import mastodon
            mastodon.running = True
            if not mastodon._thread or not mastodon._thread.is_alive():
                mastodon.start()
            send_to_ui({"type":"sns_status","enabled":True})
            send_to_ui({"type":"agent_msg","text":"마스토돈 켰어."})
        except Exception as e:
            send_to_ui({"type":"agent_msg","text":f"SNS 오류: {e}"})

    elif mtype == "sns_off":
        try:
            from mastodon_client import mastodon
            mastodon.running = False
            send_to_ui({"type":"sns_status","enabled":False})
            send_to_ui({"type":"agent_msg","text":"마스토돈 껐어."})
        except Exception as e:
            send_to_ui({"type":"agent_msg","text":f"SNS 오류: {e}"})

    elif mtype == "get_activity_log":
        try:
            import os
            path = "C:/Users/gohun/Desktop/sirian/sirian_space/activity_log.txt"
            if os.path.exists(path):
                with open(path,"r",encoding="utf-8") as f:
                    lines = f.readlines()[-30:]
                text = "[오늘 내가 한 것들]\n" + "".join(lines)
                send_to_ui({"type":"agent_msg","text":text})
            else:
                send_to_ui({"type":"agent_msg","text":"아직 아무것도 안 했어."})
        except Exception as e:
            send_to_ui({"type":"agent_msg","text":f"로그 없음: {e}"})

    elif mtype == "get_collected":

        try:
            from autonomous_worker import worker
            items = list(worker.collected)[:20]
            status = worker.get_status()
            worker.mark_all_read()
            await ws.send_text(json.dumps({"type":"collected_list","items":items,"status":status}, ensure_ascii=False))
        except:
            await ws.send_text(json.dumps({"type":"collected_list","items":[],"status":{}}, ensure_ascii=False))

    elif mtype == "list_voices":
        from tts_engine import tts
        voices = tts.list_voices()
        await ws.send_text(json.dumps({"type": "voices", "list": voices}, ensure_ascii=False))

# ── 대시보드 HTML ──
@app.get("/")
async def root():
    with open("dashboard.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

if __name__ == "__main__":
    uvicorn.run("main:app", host="localhost", port=7865, reload=False, log_level="warning")
