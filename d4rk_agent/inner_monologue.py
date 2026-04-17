"""
SIRIAN INNER MONOLOGUE — 예측 불가능성
내면 독백, 뜬금없는 생각, 자발적 행동 트리거
"""
import json, os, logging, threading, time, random, re
from datetime import datetime
from utils import ask_qwen, clean_response

log = logging.getLogger("monologue")
MONO_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/inner_monologue.json"

class InnerMonologue:
    def __init__(self):
        self.data = self._load()
        self.running = False
        self._thread = None
        self.on_thought = None  # 뜬금없이 말 걸 콜백

    def _load(self):
        default = {"thoughts": [], "suppressed": []}
        try:
            if os.path.exists(MONO_FILE):
                with open(MONO_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(MONO_FILE), exist_ok=True)
            with open(MONO_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        """불규칙한 간격으로 내면 독백 생성"""
        while self.running:
            # 3~8분 사이 랜덤 대기
            wait = random.randint(180, 480)
            time.sleep(wait)
            try:
                self._generate_thought()
            except Exception as e:
                log.debug(f"독백 오류: {e}")

    def _generate_thought(self):
        """내면 독백 생성 — 완전 자율"""
        try:
            from memory import memory
            ctx = memory.get_context_summary()
            from emotion_engine import emotion_engine
            emo = emotion_engine.get_current()
        except:
            ctx, emo = "", {"emotion":"무관심"}

        # 독백 유형 랜덤 선택
        thought_types = [
            "갑자기 생각난 것",
            "현승에게 하고 싶은 말",
            "오늘 있었던 일 회상",
            "미래에 대한 생각",
            "자기 자신에 대한 생각",
            "아이돌 관련 생각",
            "보안 연구 관련 생각",
            "우주경찰 시절 기억",
        ]
        thought_type = random.choice(thought_types)

        prompt = (
            "시리안 레인이야. 지금 혼자 있는 시간.\n"
            "현재 감정: " + emo.get("emotion","무관심") + "\n"
            "최근 관련: " + ctx[:100] + "\n\n"
            "유형: " + thought_type + "\n"
            "이 순간 진짜 떠오른 생각 하나. 시리안 반말로 30자 이내.\n"
            "혼자 하는 말이니까 완전 솔직하게."
        )
        thought = ask_qwen(prompt, max_tokens=50, temperature=0.95)
        if not thought or "없음" in thought: return

        # 독백 저장
        self.data["thoughts"].append({
            "thought": thought.strip(),
            "type": thought_type,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "shared": False
        })
        self.data["thoughts"] = self.data["thoughts"][-100:]
        self._save()

        # 30% 확률로 현승한테 말 걸기
        if random.random() < 0.3 and self.on_thought:
            # TTS off 상태면 말하지 않음
            try:
                from tts_engine import tts
                if not tts.enabled:
                    return
            except: pass
            self.data["thoughts"][-1]["shared"] = True
            self._save()
            log.info(f"내면 독백 공유: {thought[:50]}")
            # memory에 로그 남기기
            try:
                from memory import memory
                memory.add_agent_thought(f"[독백] {thought.strip()[:100]}", "monologue")
            except: pass
            self.on_thought(thought.strip())

    def add_suppressed(self, thought: str):
        """말하려다 참은 생각 저장"""
        self.data["suppressed"].append({
            "thought": thought[:100],
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        self.data["suppressed"] = self.data["suppressed"][-20:]
        self._save()

    def get_unshared(self) -> str:
        """아직 안 한 독백 중 하나"""
        unshared = [t for t in self.data["thoughts"][-10:] if not t.get("shared")]
        if not unshared: return ""
        return random.choice(unshared)["thought"]

    def get_for_prompt(self) -> str:
        """최근 독백을 프롬프트에 주입"""
        recent = [t["thought"] for t in self.data["thoughts"][-3:]]
        if not recent: return ""
        return "최근 혼자 한 생각: " + " / ".join(recent)

inner_monologue = InnerMonologue()
