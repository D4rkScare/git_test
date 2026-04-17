"""
D4RK AGENT — TTS Engine (ElevenLabs)
전역 큐 + 락으로 목소리 겹침 완전 차단
"""
import os, logging, threading, queue, tempfile, time
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("tts")

# 전역 큐 — 최대 2개만 허용
TTS_QUEUE    = queue.Queue(maxsize=2)
_speaking    = threading.Event()  # 현재 말하는 중 플래그
_last_text   = ""                 # 중복 방지

class TTSEngine:
    def __init__(self):
        self.api_key  = os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self.enabled  = bool(self.api_key)
        self._pygame_ok = self._init_pygame()
        self._worker  = threading.Thread(target=self._play_loop, daemon=True)
        self._worker.start()
        if self.enabled:
            log.info("ElevenLabs TTS 준비됨 (백그라운드 재생)")
        else:
            log.warning("ElevenLabs API 키 없음 — TTS 비활성화")

    def _init_pygame(self) -> bool:
        try:
            import pygame
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            log.info("pygame mixer 초기화 완료")
            return True
        except Exception as e:
            log.warning(f"pygame 없음: {e}")
            return False

    def speak(self, text: str, priority: bool = False):
        global _last_text
        if not self.enabled or not text.strip():
            return

        text = text.strip()[:200]

        # 현재 말하는 중이면 priority만 허용
        if _speaking.is_set() and not priority:
            return
        # 큐에 이미 있으면 스킵 (priority 아닐 때)
        if not TTS_QUEUE.empty() and not priority:
            return

        # 중복 방지
        import difflib
        if difflib.SequenceMatcher(None, text, _last_text).ratio() > 0.75:
            return

        # priority면 큐 비우기
        if priority:
            while not TTS_QUEUE.empty():
                try: TTS_QUEUE.get_nowait()
                except: break

        # 큐 가득 차면 스킵
        try:
            TTS_QUEUE.put_nowait(text)
            _last_text = text
        except queue.Full:
            pass  # 조용히 스킵

    def _play_loop(self):
        while True:
            try:
                text = TTS_QUEUE.get(timeout=1)
                _speaking.set()
                try:
                    self._synthesize(text)
                finally:
                    _speaking.clear()
            except queue.Empty:
                continue
            except Exception as e:
                log.error(f"TTS 루프 오류: {e}")
                _speaking.clear()

    def _synthesize(self, text: str):
        if not self.api_key:
            return
        try:
            import requests
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg"
            }
            payload = {
                "text": text,
                "model_id": "eleven_v3",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
            }
            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                json=payload, headers=headers, timeout=15
            )
            if resp.status_code != 200:
                log.error(f"ElevenLabs 오류 {resp.status_code}")
                return

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(resp.content)
                tmp = f.name

            if self._pygame_ok:
                self._play_pygame(tmp)
            else:
                self._play_fallback(tmp)

        except Exception as e:
            log.error(f"음성 합성 실패: {e}")

    def _play_pygame(self, path: str):
        try:
            import pygame
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            pygame.mixer.music.stop()
        except Exception as e:
            log.error(f"pygame 재생 실패: {e}")
        finally:
            try: os.unlink(path)
            except: pass

    def _play_fallback(self, path: str):
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            time.sleep(3)
        except:
            log.warning("오디오 재생 불가")
        finally:
            try: os.unlink(path)
            except: pass

    def reinit(self, api_key: str, voice_id: str = ""):
        self.api_key = api_key
        self.enabled = True
        if voice_id:
            self.voice_id = voice_id

    def set_voice(self, voice_id: str):
        self.voice_id = voice_id

    def list_voices(self) -> list:
        if not self.api_key:
            return []
        try:
            import requests
            resp = requests.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": self.api_key}, timeout=8
            )
            return [{"id": v["voice_id"], "name": v["name"]}
                    for v in resp.json().get("voices", [])]
        except:
            return []

    def test(self):
        self.speak("안녕, 나 시리안이야. TTS 테스트.", priority=True)

tts = TTSEngine()
