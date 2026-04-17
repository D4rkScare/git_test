"""
SIRIAN TOAST — Windows 토스트 알림
TTS 없이 조용하게 알림
"""
import logging, threading
from utils import strip_chinese

log = logging.getLogger("toast")

class ToastNotifier:
    def __init__(self):
        self._available = self._check()

    def _check(self) -> bool:
        try:
            from win10toast import ToastNotifier as _T
            return True
        except:
            return False

    def notify(self, title: str, message: str, duration: int = 5):
        if not self._available: return
        message = strip_chinese(message)
        title   = strip_chinese(title)
        def _send():
            try:
                from win10toast import ToastNotifier as _T
                _T().show_toast(title, message[:200], duration=duration, threaded=True)
            except: pass
        threading.Thread(target=_send, daemon=True).start()

    def sirian_notify(self, message: str):
        self.notify("시리안 레인 🌟", message)

toast = ToastNotifier()
