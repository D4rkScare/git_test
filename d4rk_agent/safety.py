"""
D4RK AGENT — Safety Layer
AI가 절대 할 수 없는 것들을 코드 레벨에서 하드락.
"""
import os, re, logging
from datetime import datetime

log = logging.getLogger("safety")

# ══ 절대 금지 패턴 (어떤 상황에도 실행 불가) ══
FORBIDDEN_PATTERNS = [
    # 파일/폴더 삭제
    r'\bos\.remove\b', r'\bos\.unlink\b', r'\bshutil\.rmtree\b',
    r'\bos\.rmdir\b', r'\brmdir\b', r'\brm\s+-rf?\b',
    r'\bdel\s+/', r'\bdelete\b.*\bfile\b',
    # 레지스트리
    r'\bwinreg\b', r'\bOpenKey\b', r'\bSetValueEx\b',
    # 시스템 종료
    r'\bshutdown\b', r'\breboot\b', r'\bos\.system\b.*\bshutdown\b',
    r'\bpoweroff\b', r'\bhalt\b',
    # 포맷
    r'\bformat\s+[a-zA-Z]:\b', r'\bdiskpart\b',
    # 악성코드 패턴
    r'\bsubprocess.*\bshell=True\b.*\brm\b',
    r'\beval\(.*os\b', r'\bexec\(.*__import__\b',
]

# ══ 확인 필요 패턴 (팝업으로 물어봄) ══
CONFIRM_PATTERNS = [
    r'\bopen\(.*["\']w["\']',      # 파일 쓰기
    r'\bsubprocess\b',              # 외부 프로세스
    r'\brequests\.(post|put|delete)\b',  # 외부 전송
    r'\bpyautogui\b',              # 마우스/키보드 제어
    r'\bos\.makedirs\b',           # 폴더 생성
    r'\bsmtplib\b',                # 이메일
    r'\bsocket\b',                 # 소켓
]

class SafetyViolation(Exception):
    pass

class SafetyLayer:
    def __init__(self):
        self.action_log = []
        self.pending_confirmations = {}

    def check_code(self, code: str) -> dict:
        """코드 실행 전 안전성 검사"""
        code_lower = code.lower()

        # 절대 금지 체크
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                self._log("BLOCKED", f"금지 패턴 감지: {pattern}", code[:100])
                return {
                    "safe": False,
                    "blocked": True,
                    "reason": f"🚫 금지된 작업 포함: {pattern}\n이 작업은 영구적으로 차단됩니다.",
                    "needs_confirm": False
                }

        # 확인 필요 체크
        needs_confirm = []
        for pattern in CONFIRM_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                needs_confirm.append(pattern)

        if needs_confirm:
            self._log("CONFIRM_NEEDED", f"확인 필요: {needs_confirm}", code[:100])
            return {
                "safe": True,
                "blocked": False,
                "reason": f"⚠ 다음 작업에 대한 확인이 필요합니다: {', '.join(needs_confirm)}",
                "needs_confirm": True,
                "patterns": needs_confirm
            }

        self._log("ALLOWED", "코드 안전 확인", code[:50])
        return {"safe": True, "blocked": False, "needs_confirm": False}

    def check_action(self, action_type: str, detail: str) -> dict:
        """특정 행동 전 안전성 검사"""
        forbidden_actions = {
            "delete_file": "🚫 파일 삭제는 영구 차단됩니다.",
            "delete_folder": "🚫 폴더 삭제는 영구 차단됩니다.",
            "system_shutdown": "🚫 시스템 종료는 차단됩니다.",
            "registry_edit": "🚫 레지스트리 수정은 차단됩니다.",
            "format_drive": "🚫 드라이브 포맷은 차단됩니다.",
        }
        confirm_actions = {
            "write_file": f"파일 수정: {detail}",
            "run_code": f"코드 실행: {detail}",
            "mouse_control": f"마우스/키보드 제어: {detail}",
            "network_request": f"네트워크 요청: {detail}",
            "create_folder": f"폴더 생성: {detail}",
        }

        if action_type in forbidden_actions:
            self._log("BLOCKED", action_type, detail)
            return {"allowed": False, "blocked": True, "reason": forbidden_actions[action_type]}

        if action_type in confirm_actions:
            self._log("CONFIRM_NEEDED", action_type, detail)
            return {"allowed": False, "blocked": False, "needs_confirm": True,
                    "message": confirm_actions[action_type]}

        self._log("ALLOWED", action_type, detail)
        return {"allowed": True, "blocked": False, "needs_confirm": False}

    def _log(self, level: str, action: str, detail: str):
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "action": action,
            "detail": detail
        }
        self.action_log.append(entry)
        if len(self.action_log) > 500:
            self.action_log = self.action_log[-500:]
        log.info(f"[{level}] {action}: {detail[:60]}")

    def get_log(self, last_n=20):
        return self.action_log[-last_n:]

safety = SafetyLayer()
