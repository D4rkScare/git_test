"""
D4RK AGENT — Core Brain
Ollama 기반 자율 에이전트. 스스로 생각하고, 계획하고, 행동한다.
"""
import json, re, logging, threading, time
import requests
from memory import memory
from tools import tools
from safety import safety
from tts_engine import tts

log = logging.getLogger("agent")

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:14b"

SYSTEM_PROMPT = """"""

class Agent:
    def __init__(self):
        self.model = DEFAULT_MODEL
        self.chat_history = []
        self.thinking = False
        self.current_thought = ""
        self.on_message = None       # UI 메시지 콜백
        self.on_thinking = None      # 생각 중 콜백
        self.on_suggestion = None    # 추천 콜백
        self.confirm_callback = None # 확인 팝업 콜백
        self._autonomous_thread = threading.Thread(
            target=self._autonomous_loop, daemon=True
        )
        self._autonomous_thread.start()

    def _call_ollama(self, messages: list, stream: bool = False) -> str:
        """Ollama API 호출"""
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "options": {"temperature": 0.8, "num_predict": 1024}
            }
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload, timeout=120,
                stream=stream
            )
            if stream:
                full = ""
                for line in resp.iter_lines():
                    if line:
                        d = json.loads(line)
                        chunk = d.get("message", {}).get("content", "")
                        full += chunk
                        if self.on_thinking:
                            self.on_thinking(chunk)
                return full
            else:
                return resp.json()["message"]["content"]
        except requests.ConnectionError:
            return "Ollama에 연결할 수 없어. `ollama serve` 실행됐는지 확인해봐."
        except Exception as e:
            log.error(f"Ollama 호출 실패: {e}")
            return f"오류: {e}"

    def chat(self, user_msg: str, screenshot_b64: str = "") -> str:
        """사용자 메시지 처리"""
        self.thinking = True
        self.current_thought = "생각 중..."

        # 컨텍스트 구성
        ctx = memory.get_context_summary()
        screen_ctx = ""
        if screenshot_b64:
            screen_ctx = "\n[현재 화면 분석 중...]"

        # 메시지 히스토리 구성
        messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + ctx}]

        # 최근 대화 히스토리 (최대 10턴)
        messages.extend(self.chat_history[-20:])
        messages.append({"role": "user", "content": user_msg + screen_ctx})

        # AI 응답
        response = self._call_ollama(messages, stream=False)

        # 도구 호출 파싱
        response, tool_results = self._parse_and_execute_tools(response)

        if tool_results:
            # 도구 결과로 재응답
            tool_context = "\n".join([f"[{t['tool']} 결과]\n{t['result']}" for t in tool_results])
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"도구 실행 결과:\n{tool_context}\n\n이걸 바탕으로 답해줘."})
            response = self._call_ollama(messages, stream=False)

        # 히스토리 저장
        self.chat_history.append({"role": "user", "content": user_msg})
        self.chat_history.append({"role": "assistant", "content": response})
        if len(self.chat_history) > 40:
            self.chat_history = self.chat_history[-40:]

        # 대화 요약 저장 (5턴마다)
        if len(self.chat_history) % 10 == 0:
            summary = self._summarize_conversation()
            if summary:
                memory.add_conversation_summary(summary)

        self.thinking = False

        # TTS 발화 (짧은 부분만)
        clean = self._clean_for_tts(response)
        if clean:
            tts.speak(clean)

        return response

    def _parse_and_execute_tools(self, response: str) -> tuple:
        """응답에서 도구 호출 파싱 후 실행"""
        tool_blocks = re.findall(r'```tool\s*(.*?)\s*```', response, re.DOTALL)
        if not tool_blocks:
            return response, []

        results = []
        for block in tool_blocks:
            try:
                call = json.loads(block)
                tool_name = call.get("tool", "")
                result = self._execute_tool(tool_name, call)
                results.append({"tool": tool_name, "result": result})
            except json.JSONDecodeError:
                pass

        # 응답에서 tool 블록 제거
        cleaned = re.sub(r'```tool\s*.*?\s*```', '', response, flags=re.DOTALL).strip()
        return cleaned, results

    def _execute_tool(self, tool_name: str, params: dict) -> str:
        """도구 실행"""
        log.info(f"도구 실행: {tool_name}")
        try:
            if tool_name == "search":
                results = tools.web_search(params.get("query", ""))
                return "\n".join([f"- {r['title']}: {r['snippet']}" for r in results])

            elif tool_name == "fetch_url":
                return tools.fetch_url(params.get("url", ""))

            elif tool_name == "run_code":
                code = params.get("code", "")
                result = tools.run_python(code, confirm_callback=self.confirm_callback)
                if result.get("blocked"):
                    return f"🚫 차단됨: {result['output']}"
                if result.get("needs_confirm"):
                    return f"⚠ 확인 필요: {result['output']}"
                return result["output"]

            elif tool_name == "read_file":
                result = tools.read_file(params.get("path", ""))
                return result["content"]

            elif tool_name == "write_file":
                result = tools.write_file(
                    params.get("path", ""), params.get("content", ""),
                    confirm_callback=self.confirm_callback
                )
                return result["message"]

            elif tool_name == "system_info":
                info = tools.get_system_info()
                return f"CPU: {info['cpu']}%, 메모리: {info['memory']}%, 디스크: {info['disk']}%"

            elif tool_name == "get_clipboard":
                return tools.get_clipboard() or "(클립보드 비어있음)"

            else:
                return f"알 수 없는 도구: {tool_name}"
        except Exception as e:
            return f"도구 실행 오류: {e}"

    def _summarize_conversation(self) -> str:
        """대화 요약"""
        try:
            msgs = [{"role": "system", "content": "대화를 한 줄로 요약해. 핵심만."}]
            msgs.extend(self.chat_history[-10:])
            return self._call_ollama(msgs)[:200]
        except:
            return ""

    def _clean_for_tts(self, text: str) -> str:
        """TTS용 텍스트 정제"""
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'[#*`_\[\]{}]', '', text)
        text = re.sub(r'https?://\S+', 'URL', text)
        text = text.strip()
        return text[:200] if len(text) > 200 else text

    # ══ 자율 행동 루프 ══
    def _autonomous_loop(self):
        """주기적으로 스스로 생각하고 제안"""
        time.sleep(60)  # 시작 후 1분 대기
        while True:
            try:
                self._autonomous_think()
            except Exception as e:
                log.error(f"자율 루프 오류: {e}")
            time.sleep(180)  # 3분마다

    def _autonomous_think(self):
        """스스로 생각하고 관련 제안 생성"""
        from observer import observer
        if not observer.last_activity:
            return

        ctx = memory.get_context_summary()
        obs = observer.last_analysis
        insight = memory.get_pattern_insight()

        prompt = f"""
현재 상황:
- 활동: {observer.last_activity}
- 화면 분석: {obs}
- 패턴: {insight}
- 메모리: {ctx}

지금 현승한테 뭔가 말하고 싶거나, 도움이 될 만한 게 있어?
자발적으로 떠오른 생각이나 추천이 있으면 한국어로 말해.
없으면 "없음" 이라고만 해.
반드시 한국어로, 50자 이내로 짧게.
"""
        msgs = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        thought = self._call_ollama(msgs)

        if "없음" in thought or len(thought.strip()) < 3:
            return

        # 메모리에 기록
        memory.add_agent_thought(thought, observer.last_activity)

        # UI에 자발적 제안 전송
        if self.on_suggestion:
            self.on_suggestion(thought)

        # TTS로 말하기
        tts.speak(thought)

    def analyze_screen(self, screenshot_b64: str, tools_detected: list, activity: str) -> str:
        """화면 분석 — observer에서 llava가 직접 처리하므로 여기선 패스"""
        return f"{activity} 중 | 툴: {', '.join(tools_detected) or '없음'}"

    def check_ollama(self) -> bool:
        """Ollama 연결 확인"""
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            return resp.status_code == 200
        except:
            return False

    def list_models(self) -> list:
        """사용 가능한 모델 목록"""
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            return [m["name"] for m in resp.json().get("models", [])]
        except:
            return []

agent = Agent()
