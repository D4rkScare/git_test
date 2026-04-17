"""
SIRIAN WEATHER — 날씨 체크
아침마다 청주 날씨 확인 + 현승한테 알려줌
"""
import requests, logging, threading, time
from datetime import datetime
from utils import strip_chinese, ask_qwen

log = logging.getLogger("weather")

CITY    = "Cheongju"
COUNTRY = "KR"

class WeatherChecker:
    def __init__(self):
        self.running     = False
        self.last_check  = None
        self._thread     = None
        self.on_weather  = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("날씨 체커 시작")

    def _loop(self):
        while self.running:
            now = datetime.now()
            # 아침 7~9시 사이, 하루 한 번
            if 7 <= now.hour <= 9:
                today = now.strftime("%Y-%m-%d")
                if self.last_check != today:
                    self.last_check = today
                    self._check_and_notify()
            time.sleep(600)  # 10분마다 확인

    def _check_and_notify(self):
        weather = self.get_weather()
        if not weather: return

        prompt = (
            "시리안 레인이야. 오늘 청주 날씨 정보:\n" + weather +
            "\n\n현승한테 날씨 알려주는 말 한 마디. 반말로 40자 이내."
        )
        msg = ask_qwen(prompt, max_tokens=60)
        if msg:
            log.info(f"날씨 알림: {msg[:50]}")
            if self.on_weather:
                self.on_weather(msg)
            try:
                from tts_engine import tts
                tts.speak(msg)
            except: pass
            try:
                from memory import memory
                memory.add_agent_thought(f"[날씨] {msg}", "weather")
            except: pass

    def get_weather(self) -> str:
        """Open-Meteo API (무료, 키 불필요)"""
        try:
            # 청주 좌표
            lat, lon = 36.6424, 127.4890
            resp = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,weathercode,windspeed_10m,precipitation",
                    "timezone": "Asia/Seoul"
                },
                timeout=10
            )
            data = resp.json().get("current",{})
            temp  = data.get("temperature_2m","?")
            wind  = data.get("windspeed_10m","?")
            rain  = data.get("precipitation", 0)
            code  = data.get("weathercode", 0)

            # 날씨 코드 → 설명
            weather_desc = {
                0:"맑음", 1:"대체로 맑음", 2:"구름 조금", 3:"흐림",
                45:"안개", 48:"서리 안개",
                51:"가는 비", 53:"보통 비", 55:"강한 비",
                61:"소나기", 63:"보통 비", 65:"강한 비",
                71:"눈", 73:"보통 눈", 75:"강한 눈",
                80:"소나기", 81:"강한 소나기", 82:"폭우",
                95:"뇌우", 96:"우박 뇌우"
            }.get(int(code), f"코드{code}")

            return f"온도:{temp}°C, 날씨:{weather_desc}, 바람:{wind}km/h, 강수:{rain}mm"
        except Exception as e:
            log.debug(f"날씨 오류: {e}")
            return ""

weather_checker = WeatherChecker()
