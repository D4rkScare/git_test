"""
SIRIAN SKILL LIBRARY — 절차 기억 + 스킬 성공률
"XSS 테스트는 이렇게" 같은 구체적 방법 저장
"""
import json, os, logging
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("skill")
SKILL_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/skill_library.json"

class SkillLibrary:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "skills": {},        # skill_name → {success, fail, level, procedures}
            "avoid_list": [],    # 실패 패턴
            "mastered": [],      # level >= 0.8 스킬
        }
        try:
            if os.path.exists(SKILL_FILE):
                with open(SKILL_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(SKILL_FILE), exist_ok=True)
            with open(SKILL_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def record(self, skill: str, success: bool,
               procedure: list = None, context: str = ""):
        """스킬 수행 결과 기록"""
        if skill not in self.data["skills"]:
            self.data["skills"][skill] = {
                "success": 0, "fail": 0,
                "level": 0.5, "procedures": [],
                "last_used": ""
            }
        s = self.data["skills"][skill]
        if success:
            s["success"] += 1
            s["level"] = min(1.0, s["level"] + 0.05)
            if procedure:
                s["procedures"].append({
                    "steps": procedure[:10],
                    "context": context[:80],
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                s["procedures"] = s["procedures"][-5:]  # 최근 5개만
        else:
            s["fail"] += 1
            s["level"] = max(0.0, s["level"] - 0.03)
            if context:
                self.data["avoid_list"].append({
                    "skill": skill,
                    "context": context[:80],
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                self.data["avoid_list"] = self.data["avoid_list"][-30:]

        s["last_used"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 마스터 스킬 체크
        if s["level"] >= 0.8 and skill not in self.data["mastered"]:
            self.data["mastered"].append(skill)
            log.info(f"스킬 마스터: {skill} (level:{s['level']:.2f})")
            try:
                from tts_engine import tts
                tts.speak(f"{skill} 스킬 마스터했어.")
            except: pass

        self._save()

    def get_procedure(self, skill: str) -> list:
        """스킬의 성공 절차 반환"""
        s = self.data["skills"].get(skill, {})
        procedures = s.get("procedures", [])
        if not procedures: return []
        # 가장 최근 절차
        return procedures[-1].get("steps", [])

    def get_level(self, skill: str) -> float:
        return self.data["skills"].get(skill, {}).get("level", 0.5)

    def should_attempt(self, skill: str) -> tuple:
        """이 스킬 시도해도 될까?"""
        s = self.data["skills"].get(skill, {})
        level = s.get("level", 0.5)
        fail  = s.get("fail", 0)
        # 실패가 너무 많으면 경고
        if fail >= 5 and level < 0.3:
            return False, f"{skill} 성공률 낮음 ({level:.1f})"
        return True, ""

    def get_for_prompt(self) -> str:
        """프롬프트용 스킬 요약"""
        lines = []
        # 상위 5개 스킬
        top = sorted(
            self.data["skills"].items(),
            key=lambda x: x[1].get("level",0), reverse=True
        )[:5]
        for name, s in top:
            lines.append(
                f"- {name}: level={s['level']:.1f} "
                f"(성공{s['success']}/실패{s['fail']})"
            )
        if self.data["mastered"]:
            lines.append(f"마스터 스킬: {', '.join(self.data['mastered'][:3])}")
        return "스킬 현황:\n" + "\n".join(lines) if lines else ""

skill_library = SkillLibrary()
