"""
SIRIAN EAR — 청각 시스템
Whisper로 시스템 오디오 인식
게임/TV 소리 필터링 강화
"""
import whisper, numpy as np, threading, time, logging, re
import soundcard as sc
from memory import memory
from utils import clean_response, ask_qwen

log = logging.getLogger("ear")

SAMPLE_RATE  = 48000
CHUNK_SEC    = 15
DEVICE_NAME  = "Realtek(R) Audio"

# 의미없는 소음 패턴 (게임, TV, 반복음)
NOISE_PATTERNS = [
    r'^[ㄱ-ㅎㅏ-ㅣ\s]+$',          # 자음/모음만
    r'^\W+$',                        # 특수문자만
    r'^(.)\1{4,}$',                  # 같은 글자 반복 (ㅋㅋㅋㅋ 등은 OK지만 너무 길면 노이즈)
    r'^[a-zA-Z\s]{1,3}$',           # 영어 1~3자만
]

# 게임 용어 (궁금증 등록은 하되 말 걸지 않음)
GAME_KEYWORDS = ['챔피언','스킬','쿨타임','딜','힐','탱커','서포터','미드','정글',
                 '갱킹','로밍','오브젝트','드래곤','바론','타워','팀파이트']

class SirianEar:
    def __init__(self):
        self.model = None
        self.device = None
        self.running = False
        self._thread = None
        self.on_heard = None        # 들은 내용 콜백
        self.on_curiosity = None    # 궁금증 등록 콜백
        self._heard_buffer = []     # 최근 들은 것들 (중복 방지)

    def start(self):
        self._thread = threading.Thread(target=self._init_and_run, daemon=True)
        self._thread.start()

    def _init_and_run(self):
        log.info("Whisper 모델 로딩 중... (base)")
        self.model = whisper.load_model("base")
        log.info("Whisper base 로드 완료")

        # COM 초기화 (Windows 필수)
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except: pass

        # 장치 탐색 — soundcard 먼저, 실패하면 pyaudiowpatch
        try:
            import time as _t
            _t.sleep(1)  # COM 초기화 대기
            mics = sc.all_microphones(include_loopback=True)
            for mic in mics:
                if DEVICE_NAME in mic.name and "Loopback" in mic.name:
                    self.device = mic
                    log.info(f"오디오 장치: {mic.name}")
                    break
            if not self.device:
                for mic in mics:
                    if "Loopback" in mic.name:
                        self.device = mic
                        log.info(f"오디오 장치 (fallback): {mic.name}")
                        break
        except Exception as e:
            log.warning(f"soundcard 실패: {e} → pyaudiowpatch 시도")

        if self.device:
            self.running = True
            log.info("시리안 청각 시작 (soundcard)")
            self._listen_loop()
        else:
            # pyaudiowpatch 폴백
            self._listen_pyaudio()

    def _listen_pyaudio(self):
        """pyaudiowpatch 방식 루프백 캡처"""
        try:
            import pyaudiowpatch as pyaudio
            import wave, struct
        except ImportError:
            log.error("pyaudiowpatch 없음 — pip install pyaudiowpatch")
            return

        try:
            p = pyaudio.PyAudio()
            # 루프백 장치 탐색
            target_device = None
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if DEVICE_NAME in info.get("name","") and info.get("isLoopbackDevice", False):
                    target_device = info
                    break
            if not target_device:
                # 첫 번째 루프백
                for i in range(p.get_device_count()):
                    info = p.get_device_info_by_index(i)
                    if info.get("isLoopbackDevice", False):
                        target_device = info
                        break

            if not target_device:
                log.error("pyaudiowpatch 루프백 장치 없음")
                p.terminate()
                return

            log.info(f"오디오 장치 (pyaudio): {target_device['name']}")
            self.running = True
            log.info("시리안 청각 시작 (pyaudiowpatch)")

            CHUNK = int(SAMPLE_RATE * CHUNK_SEC)
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=target_device["maxInputChannels"],
                rate=int(target_device["defaultSampleRate"]),
                input=True,
                input_device_index=target_device["index"],
                frames_per_buffer=1024
            )

            while self.running:
                try:
                    frames = []
                    for _ in range(0, int(SAMPLE_RATE / 1024 * CHUNK_SEC)):
                        data = stream.read(1024, exception_on_overflow=False)
                        frames.append(data)
                    audio = np.frombuffer(b''.join(frames), dtype=np.float32)

                    rms = np.sqrt(np.mean(audio**2))
                    if rms < 0.002:
                        continue

                    result = self.model.transcribe(
                        audio, language="ko", fp16=False,
                        no_speech_threshold=0.6
                    )
                    text = result.get("text","").strip()
                    if text and self._is_meaningful(text):
                        from utils import clean_response
                        text = clean_response(text)
                        if text:
                            self._process_heard(text)
                except Exception as e:
                    log.debug(f"청각 오류: {e}")

            stream.stop_stream()
            stream.close()
            p.terminate()

        except Exception as e:
            log.error(f"pyaudiowpatch 오류: {e}")

    def _listen_loop(self):
        while self.running:
            try:
                with self.device.recorder(samplerate=SAMPLE_RATE) as mic:
                    data = mic.record(numframes=SAMPLE_RATE * CHUNK_SEC)
                    audio = data[:, 0] if data.ndim > 1 else data
                    audio = audio.astype(np.float32)

                    # 음량 체크 (너무 조용하면 스킵)
                    rms = np.sqrt(np.mean(audio**2))
                    if rms < 0.002:
                        continue

                    result = self.model.transcribe(
                        audio, language="ko", fp16=False,
                        no_speech_threshold=0.6,
                        logprob_threshold=-1.0
                    )
                    text = result.get("text","").strip()

                    if text and self._is_meaningful(text):
                        text = clean_response(text)
                        if text:
                            self._process_heard(text)

            except Exception as e:
                log.debug(f"청각 오류: {e}")
                time.sleep(2)

    def _is_meaningful(self, text: str) -> bool:
        """의미있는 소리인지 판단"""
        # 너무 짧음
        if len(text.strip()) < 4:
            return False

        # 노이즈 패턴
        for pattern in NOISE_PATTERNS:
            if re.match(pattern, text.strip()):
                return False

        # 중복 (최근 3개와 비교)
        import difflib
        for prev in self._heard_buffer[-3:]:
            if difflib.SequenceMatcher(None, text, prev).ratio() > 0.8:
                return False

        return True

    def _process_heard(self, text: str):
        """들은 내용 처리"""
        log.info(f"들림: {text[:60]}")
        self._heard_buffer.append(text)
        if len(self._heard_buffer) > 20:
            self._heard_buffer = self._heard_buffer[-20:]

        # memory 저장
        memory.add_agent_thought(f"[들은 것] {text[:100]}", "heard")

        # 콜백
        if self.on_heard:
            self.on_heard(text)

        # 궁금증 추출 (게임 소리는 궁금증 등록 억제)
        is_game = any(kw in text for kw in GAME_KEYWORDS)
        if not is_game:
            self._extract_curiosity(text)

    def _extract_curiosity(self, text: str):
        """들은 내용에서 궁금증 추출"""
        prompt = (
            "들린 내용: " + text[:100] + "\n\n"
            "시리안 레인 입장에서 나중에 검색해보고 싶은 것 있어?\n"
            "있으면 10자 이내 키워드만. 없으면 없음."
        )
        result = ask_qwen(prompt, max_tokens=20, temperature=0.6)
        if result and "없음" not in result and len(result) <= 20:
            log.info(f"궁금증 등록: {result}")
            if self.on_curiosity:
                self.on_curiosity(result)
            try:
                from autonomous_worker import worker
                if not hasattr(worker, '_pending_curiosity'):
                    worker._pending_curiosity = []
                worker._pending_curiosity.append(result)
            except: pass

ear = SirianEar()
