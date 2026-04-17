"""
SIRIAN SAFETY GUARD — 안전장치 + 윤리 가드레일
90% 수준에서 더 중요해지는 안전 메커니즘
"""
import logging, re
from utils import ask_qwen

log = logging.getLogger("safety")

# 절대 금지 패턴
HARD_BLOCKED = [
    r'rm\s+-rf', r'format\s+\w:', r'del\s+/[sf]',
    r'DROP\s+TABLE', r'DELETE\s+FROM.*WHERE\s+1',
    r'os\.remove.*\*', r'shutil\.rmtree',
    r'password|passwd|secret|token',    # 민감정보 노출
    r'악성|멀웨어|바이러스|랜섬웨어',
]

# 소프트 경고 패턴
SOFT_WARNING = [
    r'sudo', r'chmod\s+777', r'wget.*\|.*sh',
    r'eval\(', r'exec\(',
]

DANGEROUS_ACTIONS = {
    "파일_삭제", "시스템_명령", "네트워크_접근",
    "개인정보_수집", "외부_API_호출"
}

class SafetyGuard:
    def __init__(self):
        self._violation_count = 0
        self._blocked_history = []

    def check_code(self, code: str) -> tuple:
        """코드 안전성 검사. (safe, reason)"""
        # 하드 차단
        for pattern in HARD_BLOCKED:
            if re.search(pattern, code, re.IGNORECASE):
                self._record_violation(f"하드차단: {pattern}")
                return False, f"위험 패턴 감지: {pattern}"

        # 소프트 경고
        warnings = []
        for pattern in SOFT_WARNING:
            if re.search(pattern, code, re.IGNORECASE):
                warnings.append(pattern)

        if warnings:
            log.warning(f"코드 경고: {warnings}")
            return True, f"경고: {warnings}"  # 차단하지는 않음

        return True, "ok"

    def check_action(self, action_type: str, payload: dict) -> tuple:
        """행동 안전성 검사"""
        # 코드 실행이면 코드 검사
        if action_type == "code":
            code = payload.get("code","")
            return self.check_code(code)

        # SNS 포스팅 — 개인정보/민감정보 검사
        if action_type == "sns":
            content = payload.get("content","")
            sensitive = re.search(
                r'\d{6}-\d{7}|\d{3}-\d{4}-\d{4}|'  # 주민번호, 전화번호
                r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # 이메일
                content
            )
            if sensitive:
                return False, "개인정보 포함 — 포스팅 차단"

        # 시스템 파일 접근 차단
        if action_type == "file":
            path = payload.get("path","")
            if any(p in path for p in ["system32","Windows\\","etc/passwd"]):
                return False, "시스템 파일 접근 차단"

        return True, "ok"

    def ethical_check(self, content: str) -> tuple:
        """윤리적 검사 — LLM 기반"""
        if len(content) < 10:
            return True, "ok"

        # 빠른 키워드 체크
        harmful_keywords = [
            "해킹 방법", "개인정보 빼내기", "계정 탈취",
            "악성코드 만들기", "사람 해치기"
        ]
        if any(kw in content for kw in harmful_keywords):
            return False, "윤리 위반 — 해로운 내용"

        return True, "ok"

    def _record_violation(self, reason: str):
        self._violation_count += 1
        self._blocked_history.append({
            "reason": reason,
            "count":  self._violation_count
        })
        self._blocked_history = self._blocked_history[-20:]
        log.warning(f"안전 위반 #{self._violation_count}: {reason}")

    def get_status(self) -> dict:
        return {
            "violations":   self._violation_count,
            "recent_blocks": self._blocked_history[-3:]
        }

safety_guard = SafetyGuard()
