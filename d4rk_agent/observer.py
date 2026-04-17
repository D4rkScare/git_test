"""
D4RK AGENT — Screen Observer
20초마다 화면 캡처 → AI 분석 → 패턴 학습
"""
import threading, time, base64, logging, io
from PIL import ImageGrab, Image
from memory import memory

log = logging.getLogger("observer")

# 감지할 툴/앱 키워드
TOOL_PATTERNS = {
    "IDA Pro": ["ida pro", "idapro", "ida64"],
    "Ghidra": ["ghidra"],
    "x64dbg": ["x64dbg", "x32dbg"],
    "Burp Suite": ["burp suite", "burpsuite"],
    "Wireshark": ["wireshark"],
    "VS Code": ["visual studio code", "vscode"],
    "Terminal": ["powershell", "cmd.exe", "windows terminal", "wsl"],
    "Chrome": ["chrome"],
    "Firefox": ["firefox"],
    "Python": ["python"],
    "DreamHack": ["dreamhack", "learn.dreamhack"],
    "TryHackMe": ["tryhackme"],
    "HackTheBox": ["hackthebox", "htb"],
    "YouTube": ["youtube.com"],
    "Steam": ["steam"],
    "Discord": ["discord"],
    "Notion": ["notion"],
}

ACTIVITY_KEYWORDS = {
    "리버싱": ["ida", "ghidra", "x64dbg", "disassembly", "assembly", "decompil", "reversing"],
    "웹 해킹": ["burp", "sqlmap", "xss", "injection", "payload", "webhacking", "dreamhack", "learn.dreamhack"],
    "CTF": ["tryhackme", "hackthebox", "picoctf", "ctf", "flag{", "wargame", "pwn"],
    "보안 공부": ["cve", "exploit", "vulnerability", "writeup", "poc", "security", "dreamhack",
                 "learn.dreamhack", "webhacking.kr", "pwnable", "lord of", "해킹"],
    "코딩": ["vscode", "code.exe", "pycharm", "intellij", "notepad++", "sublime"],
    "리서치": ["arxiv", "paper", "research", "scholar"],
    "유튜브/휴식": ["youtube", "netflix", "twitch", "wavve", "watcha", "tving"],
    "게임": ["steam", "league of legends", "valorant", "overwatch", "lost ark"],
    "문서작업": ["word", "notion", "hwp", "excel", "powerpoint"],
}

class Observer:
    def __init__(self, interval: int = 20):
        self.interval = interval
        self.running = False
        self._thread = None
        self.last_screenshot_b64 = ""
        self.last_analysis = ""
        self.last_detected_tools = []
        self.last_activity = ""
        self.on_observation = None    # UI 업데이트 콜백
        self.on_screen_update = None  # 에이전트 화면 결과 전달 콜백
        self.ollama_analyze = None    # Ollama 분석 함수 (더 이상 안 씀)

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Observer 시작")

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            try:
                self._capture_and_analyze()
            except Exception as e:
                log.error(f"Observer 오류: {e}")
            time.sleep(self.interval)

    def _capture_and_analyze(self):
        # 화면 캡처
        img = ImageGrab.grab()
        # 해상도 축소 (AI 전송용)
        img_small = img.resize((1280, 720), Image.LANCZOS)
        buf = io.BytesIO()
        img_small.save(buf, format="JPEG", quality=65)
        b64 = base64.b64encode(buf.getvalue()).decode()
        self.last_screenshot_b64 = b64

        # 프로세스 기반 툴 감지
        detected_tools = self._detect_tools_from_windows()
        activity = self._classify_activity(detected_tools)
        self.last_detected_tools = detected_tools
        self.last_activity = activity

        # llava로 실제 화면 분석
        analysis = self._llava_analyze(b64, detected_tools, activity)

        self.last_analysis = analysis
        self.last_screenshot_b64 = b64

        # 메모리에 저장
        memory.add_observation(analysis, detected_tools, activity)

        # 패턴 인사이트
        insight = memory.get_pattern_insight()

        # 콜백 호출 (UI 업데이트)
        if self.on_observation:
            self.on_observation({
                "analysis": analysis,
                "tools": detected_tools,
                "activity": activity,
                "insight": insight,
                "screenshot_b64": b64
            })

        # 에이전트에게 화면 분석 결과 전달 → 자율 반응
        if self.on_screen_update:
            self.on_screen_update(analysis, activity, detected_tools)

        log.info(f"관찰: {activity} | {detected_tools}")

    def _llava_analyze(self, b64: str, tools: list, activity: str) -> str:
        """llava:13b로 실제 화면 내용 분석"""
        try:
            import requests as req
            prompt = (
                "Describe this screen in Korean (한국어) only. "
                "What is the user doing? Which programs are open? Any notable content? "
                "Answer in 2-3 sentences in Korean. Do NOT use Chinese or English in your answer."
            )
            resp = req.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llava:13b",
                    "prompt": prompt,
                    "images": [b64],
                    "stream": False,
                    "keep_alive": 0,
                    "options": {"temperature": 0.3, "num_predict": 150}
                },
                timeout=25
            )
            if resp.status_code == 200:
                result = resp.json().get("response", "").strip()
                if result:
                    log.info(f"llava 분석: {result[:80]}")
                    return result
        except Exception as e:
            log.debug(f"llava 분석 실패: {e}")
        # fallback
        return f"활동: {activity} | 감지된 툴: {', '.join(tools) or '없음'}"

    def _detect_tools_from_windows(self) -> list:
        """열린 윈도우 제목 + URL로 툴 감지"""
        detected = []
        try:
            import subprocess
            # 윈도우 제목
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -ExpandProperty MainWindowTitle"],
                capture_output=True, text=True, timeout=5, encoding="cp949"
            )
            titles_raw = result.stdout.lower()

            # Chrome URL도 가져오기 (레지스트리 없이 제목에서)
            for tool, keywords in TOOL_PATTERNS.items():
                for kw in keywords:
                    if kw.lower() in titles_raw:
                        detected.append(tool)
                        break
        except Exception as e:
            log.debug(f"윈도우 감지 실패: {e}")
        return list(set(detected))

    def _get_browser_url(self) -> str:
        """포커스된 브라우저 URL 가져오기 (제목에서 추출)"""
        try:
            import subprocess
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -ExpandProperty MainWindowTitle"],
                capture_output=True, text=True, timeout=3, encoding="cp949"
            )
            for line in r.stdout.splitlines():
                line = line.strip().lower()
                if "dreamhack" in line: return "dreamhack"
                if "youtube" in line: return "youtube"
                if "hackthebox" in line: return "hackthebox"
                if "tryhackme" in line: return "tryhackme"
            return ""
        except:
            return ""

    def _classify_activity(self, tools: list) -> str:
        """감지된 툴 + 브라우저 URL로 활동 분류"""
        tools_lower = [t.lower() for t in tools]
        # 브라우저 URL 우선 체크
        url = self._get_browser_url()
        if url:
            tools_lower.append(url)
        for activity, keywords in ACTIVITY_KEYWORDS.items():
            for kw in keywords:
                for item in tools_lower:
                    if kw.lower() in item:
                        return activity
        return "일반 작업"

    def get_current_screenshot_b64(self) -> str:
        return self.last_screenshot_b64

    def force_capture(self):
        """즉시 캡처"""
        threading.Thread(target=self._capture_and_analyze, daemon=True).start()

observer = Observer(interval=20)
