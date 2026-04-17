"""
SIRIAN META-LEARNING — 자기 수정 + 약점 분석
"어떤 모듈을 강화해야 할까?" 자율 판단 루프
"""
import json, os, logging, threading, time
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("meta_learn")
META_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/meta_learning.json"
INTERVAL  = 8 * 3600  # 8시간마다

class MetaLearning:
    def __init__(self):
        self.running = False
        self._thread = None
        self.data    = self._load()

    def _load(self):
        default = {
            "sessions":       [],
            "weak_modules":   [],   # 약한 모듈 리스트
            "strong_modules": [],   # 강한 모듈
            "self_prompt":    "",   # 자기 수정 프롬프트
            "version":        0,
        }
        try:
            if os.path.exists(META_FILE):
                with open(META_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(META_FILE), exist_ok=True)
            with open(META_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Meta-Learning 시작")

    def _loop(self):
        time.sleep(3600)  # 1시간 후 첫 실행
        while self.running:
            try:
                self.analyze()
            except Exception as e:
                log.error(f"Meta-Learning 오류: {e}")
            time.sleep(INTERVAL)

    def analyze(self):
        """약점 분석 + 자기 수정"""
        log.info("Meta-Learning 분석 시작")
        session = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "steps": {}}

        # 1. 모듈별 성능 수집
        module_stats = self._collect_module_stats()
        session["steps"]["stats"] = module_stats

        # 2. 약점 식별
        weak = self._identify_weak(module_stats)
        self.data["weak_modules"]   = weak
        session["steps"]["weak"]    = weak

        # 3. 강점 식별
        strong = self._identify_strong(module_stats)
        self.data["strong_modules"] = strong

        # 4. 자기 수정 프롬프트 생성
        self_prompt = self._generate_self_prompt(weak, strong)
        self.data["self_prompt"] = self_prompt
        session["steps"]["self_prompt"] = self_prompt[:200]

        # 5. 약점 모듈 강화 지시
        self._reinforce_weak(weak)

        # 6. 개선 보고
        report = self._generate_report(weak, strong, self_prompt)
        session["steps"]["report"] = report

        self.data["sessions"].append(session)
        self.data["sessions"] = self.data["sessions"][-20:]
        self.data["version"] += 1
        self._save()

        log.info(f"Meta-Learning v{self.data['version']}: 약점={weak}")

        # 현승한테 보고
        try:
            from memory import memory
            memory.add_agent_thought(f"[메타학습] {report[:100]}", "meta")
        except: pass

    def _collect_module_stats(self) -> dict:
        stats = {}
        # RL 성공률
        try:
            from rl_learner import rl
            av = rl.policy.get("action_values", {})
            for action, state_scores in av.items():
                scores = list(state_scores.values())
                if scores:
                    stats[f"rl_{action}"] = sum(scores)/len(scores)
        except: pass

        # Skill Library
        try:
            from skill_library import skill_library
            for name, s in skill_library.data.get("skills",{}).items():
                stats[f"skill_{name}"] = s.get("level", 0.5)
        except: pass

        # 예측 정확도
        try:
            from causal_world_model import causal_world_model
            stats["causal_accuracy"] = causal_world_model.data.get("accuracy", 0.5)
        except: pass

        # 연구 성공률
        try:
            from system_logger import system_logger
            recent = system_logger.get_recent(50)
            research = [l for l in recent if l.get("action") == "research"]
            if research:
                stats["research_success"] = sum(
                    1 for l in research if l.get("success")
                ) / len(research)
        except: pass

        return stats

    def _identify_weak(self, stats: dict) -> list:
        return [k for k, v in stats.items() if v < 0.4]

    def _identify_strong(self, stats: dict) -> list:
        return [k for k, v in stats.items() if v > 0.7]

    def _generate_self_prompt(self, weak: list, strong: list) -> str:
        """시리안 자신을 위한 개선 프롬프트"""
        prompt = (
            "시리안 레인이야. 자기 분석.\n"
            "약한 부분: " + str(weak[:3]) + "\n"
            "강한 부분: " + str(strong[:3]) + "\n\n"
            "다음 행동 전략 개선 방향 두 줄. 반말로."
        )
        result = ask_qwen(prompt, max_tokens=80, temperature=0.6)
        return result or ""

    def _reinforce_weak(self, weak: list):
        """약한 모듈 강화 지시"""
        for module in weak[:2]:
            if "research" in module:
                # 연구 전략 개선
                try:
                    from strategy_library import strategy_library
                    strategy_library.add_avoid(
                        "research", "일반",
                        "연구 결과 낮음 — 더 구체적인 주제 선택 필요"
                    )
                except: pass
            elif "rl_" in module:
                # RL 탐험 강제
                try:
                    from rl_learner import rl
                    action = module.replace("rl_","")
                    rl.policy["action_values"].setdefault(action, {})
                    log.info(f"RL 탐험 강제: {action}")
                except: pass

    def _generate_report(self, weak: list, strong: list, self_prompt: str) -> str:
        prompt = (
            "약점: " + str(weak) + "\n"
            "강점: " + str(strong) + "\n"
            "개선 방향: " + self_prompt[:100] + "\n\n"
            "한 줄 요약. 시리안 반말."
        )
        return ask_qwen(prompt, max_tokens=40, temperature=0.5) or "분석 완료"

    def get_self_prompt(self) -> str:
        return self.data.get("self_prompt", "")

    def get_weak_modules(self) -> list:
        return self.data.get("weak_modules", [])

meta_learning = MetaLearning()
