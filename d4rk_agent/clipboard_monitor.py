"""
SIRIAN CLIPBOARD — 클립보드 모니터링
현승이 코드/텍스트 복사하면 반응
"""
import threading, time, logging, re
from utils import ask_qwen, strip_chinese

log = logging.getLogger("clipboard")

class ClipboardMonitor:
    def __init__(self):
        self.running  = False
        self._thread  = None
        self._prev    = ""
        self.on_found = None  # 흥미로운 내용 발견 콜백

    def start(self):
        try:
            import pyperclip
            self.running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            log.info("클립보드 모니터 시작")
        except ImportError:
            log.warning("pyperclip 없음 — pip install pyperclip")

    def _loop(self):
        import pyperclip
        while self.running:
            try:
                current = pyperclip.paste()
                if current and current != self._prev and len(current) > 10:
                    self._prev = current
                    self._react(current)
            except: pass
            time.sleep(3)

    def _react(self, content: str):
        """클립보드 내용에 반응"""
        content = strip_chinese(content)
        if not content: return

        # 코드인지 판단
        is_code = any(kw in content for kw in
                     ['import','def ','class ','function','var ','const ',
                      'if (','for (','while (','<?php','<html','SELECT '])

        # 너무 짧거나 일반 텍스트면 스킵
        if len(content) < 15 or (not is_code and len(content) < 50):
            return

        prompt = (
            "현승이 방금 복사한 내용:\n" + content[:300] + "\n\n"
            "시리안 레인으로서 한마디 하고 싶어?\n"
            "코드면 버그나 개선점 간단히. 텍스트면 관심 있으면 반응.\n"
            "시리안 반말로 40자 이내. 없으면 없음."
        )
        reaction = ask_qwen(prompt, max_tokens=60, temperature=0.85)
        if reaction and "없음" not in reaction:
            log.info(f"클립보드 반응: {reaction[:50]}")
            if self.on_found:
                self.on_found(reaction)

clipboard = ClipboardMonitor()
