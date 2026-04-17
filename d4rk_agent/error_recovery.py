"""
SIRIAN ERROR RECOVERY — 에러 복구 + Fallback 전략
try/except pass 대신 체계적 복구
"""
import logging, time, functools, traceback
from datetime import datetime
from collections import defaultdict

log = logging.getLogger("recovery")

class ErrorRecovery:
    def __init__(self):
        self._error_counts  = defaultdict(int)
        self._error_history = []
        self._fallbacks     = {}    # module → fallback function

    def register_fallback(self, module: str, fn):
        self._fallbacks[module] = fn

    def safe_call(self, module: str, fn, *args, fallback=None, **kwargs):
        """안전 호출 — 실패 시 fallback 실행"""
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            self._record_error(module, e)
            # 등록된 fallback
            if module in self._fallbacks:
                try:
                    return self._fallbacks[module](*args, **kwargs)
                except: pass
            # 직접 fallback
            if fallback is not None:
                return fallback
            return None

    def _record_error(self, module: str, error: Exception):
        self._error_counts[module] += 1
        entry = {
            "module": module,
            "error":  str(error)[:100],
            "count":  self._error_counts[module],
            "time":   datetime.now().strftime("%H:%M:%S")
        }
        self._error_history.append(entry)
        self._error_history = self._error_history[-100:]

        level = logging.WARNING if self._error_counts[module] < 3 else logging.ERROR
        log.log(level, f"[{module}] 오류 #{self._error_counts[module]}: {error}")

    def retry(self, max_attempts: int = 3, delay: float = 1.0):
        """재시도 데코레이터"""
        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(max_attempts):
                    try:
                        return fn(*args, **kwargs)
                    except Exception as e:
                        last_error = e
                        if attempt < max_attempts - 1:
                            time.sleep(delay * (attempt + 1))
                self._record_error(fn.__name__, last_error)
                return None
            return wrapper
        return decorator

    def get_health_report(self) -> dict:
        """모듈 건강 보고서"""
        report = {}
        for module, count in self._error_counts.items():
            recent = [e for e in self._error_history
                     if e["module"] == module][-3:]
            report[module] = {
                "error_count": count,
                "recent":      [e["error"] for e in recent],
                "status":      "위험" if count > 5 else "경고" if count > 2 else "정상"
            }
        return report

    def get_for_prompt(self) -> str:
        """심각한 에러만 프롬프트에"""
        critical = [m for m, c in self._error_counts.items() if c > 5]
        if not critical: return ""
        return f"⚠️ 불안정 모듈: {', '.join(critical[:3])}"

error_recovery = ErrorRecovery()


def safe(module: str, fallback=None):
    """간단한 안전 데코레이터"""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return error_recovery.safe_call(module, fn, *args,
                                           fallback=fallback, **kwargs)
        return wrapper
    return decorator
