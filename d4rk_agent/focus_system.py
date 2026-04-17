"""
SIRIAN FOCUS SYSTEM — 집중 시스템
한 번에 하나만 집중, 나머지는 큐
"""
import logging, threading, time
from utils import ask_qwen, clean_response, strip_chinese
from collections import deque
from datetime import datetime

log = logging.getLogger("focus")

class FocusSystem:
    def __init__(self):
        self.current_focus = None   # 지금 집중 중인 것
        self.focus_start = None
        self.queue = deque(maxlen=10)  # 대기 큐
        self._lock = threading.Lock()

    def set_focus(self, task: str, priority: int = 5) -> bool:
        """집중 설정 — 이미 집중 중이면 큐에 추가"""
        with self._lock:
            if self.current_focus is None:
                self.current_focus = task
                self.focus_start = datetime.now()
                log.info(f"집중 시작: {task}")
                return True
            else:
                # 우선순위 높으면 현재 것 큐로 밀고 새로 집중
                if priority > 8:
                    self.queue.appendleft(self.current_focus)
                    self.current_focus = task
                    self.focus_start = datetime.now()
                    log.info(f"집중 전환 (긴급): {task}")
                    return True
                else:
                    self.queue.append({"task": task, "priority": priority})
                    log.info(f"큐 추가: {task} (현재: {self.current_focus})")
                    return False

    def complete_focus(self) -> str:
        """집중 완료 — 다음 큐 항목으로"""
        with self._lock:
            completed = self.current_focus
            if self.queue:
                next_item = self.queue.popleft()
                if isinstance(next_item, dict):
                    self.current_focus = next_item["task"]
                else:
                    self.current_focus = next_item
                self.focus_start = datetime.now()
                log.info(f"다음 집중: {self.current_focus}")
            else:
                self.current_focus = None
                self.focus_start = None
            return completed

    def is_focused(self) -> bool:
        return self.current_focus is not None

    def can_do(self, task: str) -> bool:
        """이 작업 지금 해도 되는지"""
        with self._lock:
            if self.current_focus is None: return True
            if self.current_focus == task: return True
            return False

    def get_focus_duration(self) -> float:
        """현재 집중 시간 (분)"""
        if not self.focus_start: return 0
        return (datetime.now() - self.focus_start).seconds / 60

    def get_status(self) -> str:
        if not self.current_focus:
            return "집중 없음"
        duration = self.get_focus_duration()
        queue_info = f" | 대기: {len(self.queue)}개" if self.queue else ""
        return f"집중: {self.current_focus} ({duration:.1f}분){queue_info}"

    def get_for_prompt(self) -> str:
        if self.current_focus:
            return f"지금 집중 중: {self.current_focus}"
        return ""

focus = FocusSystem()
