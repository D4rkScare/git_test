"""
SIRIAN CONSOLIDATION — 기억 통합 + 주간 리포트
중요한 것만 장기기억으로 승격, 개선점 리포트 생성
"""
import json, os, logging, threading, time
from datetime import datetime, timedelta
from utils import ask_qwen, strip_chinese

log = logging.getLogger("consolidation")
REPORT_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/weekly_report.json"
INTERVAL    = 6 * 3600  # 6시간마다 (컴퓨터 켜있을 때)

class Consolidation:
    def __init__(self):
        self.running = False
        self._thread = None
        self.reports = self._load()

    def _load(self):
        try:
            if os.path.exists(REPORT_FILE):
                with open(REPORT_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        return {"reports": [], "last_run": ""}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
            with open(REPORT_FILE,'w',encoding='utf-8') as f:
                json.dump(self.reports, f, ensure_ascii=False, indent=2)
        except: pass

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Consolidation 루프 시작")

    def _loop(self):
        time.sleep(7200)  # 2시간 후 첫 실행
        while self.running:
            try:
                self.run()
            except Exception as e:
                log.error(f"Consolidation 오류: {e}")
            time.sleep(INTERVAL)

    def run(self):
        log.info("Consolidation 시작")
        report = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "steps": {}
        }

        # 1. 최근 에피소드 요약
        episode_summary = self._summarize_episodes()
        report["steps"]["episodes"] = episode_summary

        # 2. 중요한 것 → 장기기억 승격
        promoted = self._promote_to_longterm()
        report["steps"]["promoted"] = promoted

        # 3. 개선점 리포트 생성
        improvement = self._generate_improvement_report()
        report["steps"]["improvement"] = improvement

        # 4. meta_cognition 업데이트
        self._update_meta(improvement)

        # 5. 오래된 저품질 기억 정리
        cleaned = self._cleanup_old_memories()
        report["steps"]["cleaned"] = cleaned

        self.reports["reports"].append(report)
        self.reports["reports"] = self.reports["reports"][-30:]
        self.reports["last_run"] = report["time"]
        self._save()

        log.info(f"Consolidation 완료: {improvement[:60]}")
        try:
            from memory import memory
            memory.add_agent_thought(f"[통합] {improvement[:100]}", "consolidation")
        except: pass

    def _summarize_episodes(self) -> str:
        try:
            from episode_memory import episode_memory
            episodes = episode_memory.data.get("episodes", [])[-10:]
            if not episodes: return "없음"

            ep_str = "\n".join([
                f"- {e.get('time','')[:10]}: {e.get('event','')} ({e.get('emotion','')})"
                for e in episodes
            ])
            prompt = (
                "시리안 레인의 최근 에피소드:\n" + ep_str +
                "\n\n핵심 3줄 요약. 시리안 반말로."
            )
            return ask_qwen(prompt, max_tokens=100, temperature=0.5) or "요약 실패"
        except: return "실패"

    def _promote_to_longterm(self) -> str:
        """중요도 높은 기억을 enhanced_memory에 승격"""
        promoted = 0
        try:
            from enhanced_memory import enhanced_memory
            from episode_memory import episode_memory

            for ep in episode_memory.data.get("episodes", [])[-20:]:
                imp = ep.get("importance", 0)
                if imp > 0.7:
                    enhanced_memory.add(
                        ep.get("event",""),
                        "longterm",
                        ep.get("emotion",""),
                        importance=min(1.0, imp + 0.1)
                    )
                    promoted += 1
        except: pass
        return f"{promoted}개 승격"

    def _generate_improvement_report(self) -> str:
        """개선점 리포트"""
        try:
            from system_logger import system_logger
            from skill_library import skill_library

            recent_logs = system_logger.get_recent(50)
            failures = [l for l in recent_logs if not l.get("success", True)]
            skill_info = skill_library.get_for_prompt()

            fail_str = "\n".join([
                f"- {l.get('action','')}: {l.get('reason','')[:40]}"
                for l in failures[-5:]
            ])

            prompt = (
                "시리안 레인이야. 자기 개선 분석.\n"
                "최근 실패:\n" + fail_str + "\n"
                "스킬 현황:\n" + skill_info[:200] + "\n\n"
                "이번 주 개선점 3가지. 시리안 반말로."
            )
            return ask_qwen(prompt, max_tokens=120, temperature=0.6) or "분석 실패"
        except: return "실패"

    def _update_meta(self, improvement: str):
        try:
            from meta_cognition import meta_cognition
            meta_cognition.analyze("consolidation", "주간 통합", improvement, 0.7)
        except: pass

    def _cleanup_old_memories(self) -> str:
        """오래된 저품질 기억 정리"""
        cleaned = 0
        cutoff = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        try:
            from enhanced_memory import enhanced_memory
            before = len(enhanced_memory.entries)
            enhanced_memory.entries = [
                e for e in enhanced_memory.entries
                if e.get("time","") >= cutoff or e.get("importance",0) >= 0.7
            ]
            enhanced_memory._save()
            cleaned = before - len(enhanced_memory.entries)
        except: pass
        return f"{cleaned}개 정리"

    def get_last_report(self) -> dict:
        reports = self.reports.get("reports", [])
        return reports[-1] if reports else {}

consolidation = Consolidation()
