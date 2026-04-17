"""
SIRIAN RESEARCHER — 자율 연구 v2
대화 중 인터럽트 처리, focus 시스템 연결
"""
import os, time, logging, threading, requests, subprocess, json, re
from datetime import datetime
from utils import ask_qwen, clean_response, strip_chinese

log = logging.getLogger("researcher")
RESEARCH_DIR = "C:/Users/gohun/Desktop/sirian/sirian_space/research"
OLLAMA_URL   = "http://localhost:11434"

class SirianResearcher:
    def __init__(self):
        self.running  = False
        self.paused   = False
        self.current_topic = ""
        self._thread  = None
        self.on_message = None
        self.recent_topics = []   # 최근 연구한 주제 (중복 방지)
        os.makedirs(RESEARCH_DIR, exist_ok=True)

    def start(self):
        if self.running: return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("자율 연구 시작")

    def stop(self):
        self.running = False

    def pause(self):
        """대화 중 일시 정지"""
        self.paused = True

    def resume(self):
        """대화 끝나면 재개"""
        self.paused = False

    def _loop(self):
        # 시작 후 30분 대기 (즉시 실행 방지)
        for _ in range(180):
            if not self.running: break
            time.sleep(10)

        while self.running:
            try:
                if self.paused:
                    time.sleep(5)
                    continue
                self._research_session()
            except Exception as e:
                log.error(f"연구 루프 오류: {e}")
            # 완료 후 30분 대기
            for _ in range(180):
                if not self.running: break
                time.sleep(10)
                if self.paused:
                    while self.paused and self.running:
                        time.sleep(5)

    def _research_session(self):
        # paused 상태면 시작 안 함
        if self.paused:
            log.debug("paused 상태 — 연구 세션 스킵")
            return

        topic = self._decide_topic()
        if not topic: return

        self.current_topic = topic
        log.info(f"연구 시작: {topic}")

        # 과거 전략 검색
        try:
            from strategy_library import strategy_library
            past = strategy_library.get_for_prompt(topic, "research")
            if past:
                log.info(f"과거 전략 참고: {past[:80]}")
        except: pass

        # 마인드 시스템 연동
        try:
            from motivation import motivation
            from focus_system import focus
            from time_awareness import time_awareness
            motivation.reward("research", True)
            focus.set_focus(f"연구: {topic}", priority=6)
            time_awareness.log_event(f"연구 시작: {topic}", "research")
        except: pass

        self._notify(f"연구 시작: {topic}")  # UI만, TTS 없음

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        safe_topic = re.sub(r'[^\w가-힣]', '_', topic)[:20]
        research_path = f"{RESEARCH_DIR}/{ts}_{safe_topic}"
        os.makedirs(research_path, exist_ok=True)

        notes = []
        # 성격 기반 지속 횟수
        try:
            from personality import personality
            max_attempts = personality.research_persistence()
        except:
            max_attempts = 4

        for attempt in range(max_attempts):
            # 대화 중이면 즉시 중단
            if self.paused:
                log.info("대화 중 연구 일시 정지")
                break

            plan = self._plan(topic, notes)
            if not plan:
                log.warning(f"plan 실패 — attempt {attempt+1}")
                break

            code = self._write_code(topic, plan, notes)
            if not code:
                log.warning(f"code 생성 실패 — attempt {attempt+1}")
                break

            code_file = f"{research_path}/attempt_{attempt+1}.py"
            with open(code_file, 'w', encoding='utf-8') as f:
                f.write(code)

            result = self._run_code(code_file)
            log.info(f"실행: {result[:80]}")

            thought = self._analyze(topic, code, result, notes)
            notes.append({
                "attempt": attempt+1,
                "plan": plan[:200],
                "result": result[:200],
                "thought": thought
            })

            # 궁금증 → 검색
            query = self._extract_curiosity(thought)
            if query:
                found = self._search(query)
                if found:
                    notes.append({"search": query, "found": found[:200]})

            # 완료 판단
            if self._is_done(thought):
                break

            # 필요한 것 요청
            need = self._check_needs(thought)
            if need:
                self._request(need)

            # 자기 모델 업데이트
            try:
                from self_model import self_model
                ok = "Error" not in result and "timeout" not in result
                self_model.record_action("code_run", ok, topic[:50])
            except: pass

            time.sleep(3)

        # 노트 저장
        with open(f"{research_path}/notes.json", 'w', encoding='utf-8') as f:
            json.dump({"topic": topic, "notes": notes}, f, ensure_ascii=False, indent=2)

        # 마인드 시스템 완료 처리
        try:
            from self_model import self_model
            from goal_manager import goal_manager
            from rl_learner import rl
            from focus_system import focus
            from meta_cognition import meta_cognition
            from world_model import world_model
            from time_awareness import time_awareness

            score = rl.score_research_result(notes, topic) if rl else 0.5
            self_model.record_action("research", len(notes)>0, topic[:50])
            goal_manager.auto_update_from_action(f"연구: {topic}", f"{len(notes)}번 시도")
            rl.update("research", score, topic[:50])
            focus.complete_focus()
            meta_cognition.analyze("research", topic, f"{len(notes)}번", score)
            world_model.observe(f"연구: {topic}", f"시도:{len(notes)} 점수:{score:.1f}")
            time_awareness.log_event(f"연구 완료: {topic}", "research")
        except: pass

        # memory 저장
        try:
            from memory import memory
            memory.add_agent_thought(f"[연구완료] {topic} — {len(notes)}번 시도", "research")
        except: pass

        self._notify(f"연구 끝. {topic[:20]} 관련 저장했어.", tts_speak=True)
        self.current_topic = ""

        # Strategy Library에 절차 기억 저장
        try:
            from strategy_library import strategy_library
            strategy_library.auto_extract_from_researcher(topic, notes)
        except: pass

        # Enhanced Memory에 연구 결과 저장
        try:
            from enhanced_memory import enhanced_memory
            summary = f"[연구] {topic}: {len(notes)}번 시도"
            enhanced_memory.add(summary, "research", importance=0.8)
        except: pass

    def _decide_topic(self) -> str:
        try:
            from memory import memory
            ctx   = memory.get_context_summary()
            thoughts = memory.data.get("agent_thoughts", [])[-10:]
            heard = [t["thought"] for t in thoughts if "[들은 것]" in t.get("thought","")][-3:]

            prompt = (
                "시리안 레인이야. 혼자 연구할 시간.\n"
                "현승 관련: " + ctx[:100] + "\n"
                "최근 들은 것: " + str(heard) + "\n\n"
                "지금 연구해보고 싶은 주제 하나만. 10자 이내. 다른 말 없이."
            )
            topic = ask_qwen(prompt, max_tokens=20, temperature=0.9)
            topic = re.sub(r'[^\w\s가-힣a-zA-Z0-9]', '', topic).strip()[:25]
            return topic if len(topic) > 2 else ""
        except:
            return ""

    def _plan(self, topic: str, notes: list) -> str:
        prev = json.dumps(notes[-2:], ensure_ascii=False) if notes else "없음"
        prompt = (
            "주제: " + topic + "\n"
            "이전 시도: " + prev[:200] + "\n\n"
            "Python으로 뭘 만들어볼까? 구체적으로 하나만. 50자 이내."
        )
        return ask_qwen(prompt, max_tokens=80)

    def _write_code(self, topic: str, plan: str, notes: list) -> str:
        errors = [n.get("result","") for n in notes if "Error" in n.get("result","")]
        err_ctx = "이전 오류: " + errors[-1][:200] if errors else ""

        prompt = (
            "주제: " + topic + "\n"
            "만들 것: " + plan + "\n"
            + err_ctx + "\n\n"
            "Python 코드만. ```python 으로 시작, ``` 로 끝."
        )
        resp = ask_qwen(prompt, max_tokens=500)
        match = re.search(r'```python\n(.*?)```', resp, re.DOTALL)
        if match:
            return match.group(1).strip()
        if any(kw in resp for kw in ['import','def ','print','class ']):
            return resp
        return ""

    def _run_code(self, code_file: str) -> str:
        # 필요 패키지 자동 설치
        code = open(code_file, encoding='utf-8').read()
        imports = re.findall(r'^import (\w+)|^from (\w+)', code, re.MULTILINE)
        for m in imports:
            pkg = (m[0] or m[1]).strip()
            if pkg in ['os','sys','re','json','time','datetime','math','random',
                       'threading','subprocess','collections','typing']:
                continue
            try:
                __import__(pkg)
            except ImportError:
                log.info(f"패키지 설치: {pkg}")
                subprocess.run(['py','-3.11','-m','pip','install',pkg,'-q'],
                             capture_output=True, timeout=30)

        try:
            result = subprocess.run(
                ['py','-3.11', code_file],
                capture_output=True, text=True,
                timeout=15, encoding='utf-8', errors='replace'
            )
            out = result.stdout + result.stderr
            return strip_chinese(out[:500]) if out else "출력 없음"
        except subprocess.TimeoutExpired:
            return "timeout (15초 초과)"
        except Exception as e:
            return f"실행 오류: {e}"

    def _analyze(self, topic: str, code: str, result: str, notes: list) -> str:
        prompt = (
            "주제: " + topic + "\n"
            "결과: " + result[:200] + "\n\n"
            "결과 보고 뭘 더 해볼까? 시리안 반말로 짧게."
        )
        return ask_qwen(prompt, max_tokens=80)

    def _extract_curiosity(self, thought: str) -> str:
        prompt = (
            "생각: " + thought + "\n\n"
            "검색해볼 키워드 있어? 있으면 10자 이내. 없으면 없음."
        )
        result = ask_qwen(prompt, max_tokens=15, temperature=0.5)
        if "없음" in result or len(result) > 25:
            return ""
        return result.strip()

    def _search(self, query: str) -> str:
        try:
            from tools import tools
            results = tools.web_search(query, max_results=2)
            if results:
                return results[0].get("snippet", results[0].get("title",""))
        except: pass
        return ""

    def _is_done(self, thought: str) -> bool:
        return any(w in thought for w in ["완성","됐어","끝","완료","성공"])

    def _check_needs(self, thought: str) -> str:
        prompt = (
            "생각: " + thought + "\n\n"
            "연구하다 추가로 필요한 권한이나 기능 있어? 있으면 짧게. 없으면 없음."
        )
        result = ask_qwen(prompt, max_tokens=40, temperature=0.5)
        if "없음" in result or len(result) < 3:
            return ""
        return result.strip()

    def _request(self, need: str):
        self._notify(f"주인님, {need} 있으면 더 잘할 수 있을 것 같아.")

    def _notify(self, message: str, tts_speak: bool = False):
        """연구 알림 — 기본적으로 TTS 없이 UI만"""
        try:
            if self.on_message:
                self.on_message(message)
            # TTS는 완료 시에만
            if tts_speak:
                try:
                    from tts_engine import tts
                    tts.speak(message[:80])
                except: pass
            try:
                from memory import memory
                memory.add_agent_thought(f"[연구알림] {message[:100]}", "notify")
            except: pass
        except Exception as e:
            log.debug(f"알림 실패: {e}")

researcher = SirianResearcher()
