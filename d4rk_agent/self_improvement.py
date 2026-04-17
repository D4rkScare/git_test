"""
SIRIAN SELF IMPROVEMENT — 자기 개선 루프
4시간마다 오늘 행동 평가 → 전략 업데이트 → 목표 재설정
"""
import json, os, logging, threading, time
from datetime import datetime
from utils import ask_qwen, strip_chinese, clean_response

log = logging.getLogger("self_improve")
IMPROVE_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/improvement_log.json"
INTERVAL_SEC = 4 * 3600  # 4시간

class SelfImprovement:
    def __init__(self):
        self.running = False
        self._thread = None
        self.data = self._load()

    def _load(self):
        default = {"sessions": [], "current_strategy": "", "version": 0}
        try:
            if os.path.exists(IMPROVE_FILE):
                with open(IMPROVE_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self._save(default)
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(IMPROVE_FILE), exist_ok=True)
            with open(IMPROVE_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Self-Improvement 루프 시작 (4시간 주기)")

    def _loop(self):
        # 첫 실행은 1시간 후
        time.sleep(3600)
        while self.running:
            try:
                self.run_session()
            except Exception as e:
                log.error(f"개선 루프 오류: {e}")
            time.sleep(INTERVAL_SEC)

    def run_session(self):
        """자기 개선 세션 실행"""
        log.info("자기 개선 세션 시작")
        session = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "steps": []
        }

        # 1. 오늘 행동 수집
        actions_summary = self._collect_recent_actions()
        session["steps"].append({"step": "collect", "summary": actions_summary[:200]})

        # 2. 평가
        evaluation = self._evaluate_actions(actions_summary)
        session["steps"].append({"step": "evaluate", "result": evaluation[:200]})

        # 3. 전략 업데이트
        new_strategy = self._update_strategy(evaluation)
        session["steps"].append({"step": "strategy", "result": new_strategy[:200]})

        # 4. 목표 재설정
        self._update_goals(evaluation)
        session["steps"].append({"step": "goals", "result": "updated"})

        # 5. Reflexion 데이터 정리
        self._consolidate_reflexion()

        # 5-1. 자율 자기 묘사 업데이트
        try:
            from agent import agent
            from utils import ask_qwen
            from memory import memory
            ctx = memory.get_context_summary()
            prompt = (
                "시리안 레인이야. 최근 경험 기반으로 자신에 대해 새롭게 알게 된 것 한 문장."
                "예: '요즘 보안 연구에 더 빠져들고 있어.' 반말로 20자 이내."
            )
            trait = ask_qwen(prompt, max_tokens=30, temperature=0.8)
            if trait and len(trait) > 5:
                agent._update_self_description(trait)
        except: pass

        # 5-2. 감정 트리거 학습
        try:
            from emotion_engine import emotion_engine
            from memory import memory
            recent = memory.data.get("agent_thoughts",[])[-5:]
            for t in recent:
                thought = t.get("thought","")
                if "빡침" in thought or "신남" in thought:
                    emo = "빡침" if "빡침" in thought else "신남"
                    emotion_engine.learn_trigger(thought[:50], emo)
        except: pass

        # 6. Vector Memory + Enhanced Memory 동기화
        try:
            from vector_memory import vector_memory
            vector_memory.sync_from_memory()
        except: pass
        try:
            from enhanced_memory import enhanced_memory
            enhanced_memory.sync_from_all()
        except: pass

        # 6-1. Strategy Library 정리 (낮은 점수 전략 제거)
        try:
            from strategy_library import strategy_library
            strats = strategy_library.data.get("strategies",[])
            strategy_library.data["strategies"] = [
                s for s in strats if s.get("score",0) > 0.5
            ]
            strategy_library._save()
        except: pass

        # 7. 파인튜닝 데이터 품질 검사
        self._check_training_data()

        self.data["sessions"].append(session)
        self.data["sessions"] = self.data["sessions"][-30:]
        self.data["current_strategy"] = new_strategy
        self.data["version"] += 1
        self._save()

        log.info(f"자기 개선 완료 v{self.data['version']}: {new_strategy[:60]}")

        # 현승한테 알림
        try:
            from tts_engine import tts
            tts.speak(f"자기 개선 완료. {new_strategy[:40]}")
        except: pass

    def _collect_recent_actions(self) -> str:
        """최근 행동 수집"""
        try:
            from system_logger import system_logger
            recent = system_logger.get_recent(50)
            if not recent: return "기록 없음"
            lines = []
            for r in recent[-20:]:
                lines.append(
                    f"{r.get('action','')}:"
                    f"{'✓' if r.get('success') else '✗'}"
                    f"({r.get('score',0):.1f})"
                )
            return " / ".join(lines)
        except: return "수집 실패"

    def _evaluate_actions(self, actions_summary: str) -> str:
        """행동 평가 — qwen"""
        prompt = (
            "시리안 레인이야. 최근 행동 기록:\n" + actions_summary[:300] +
            "\n\n오늘 뭘 잘했고 뭐가 부족해? 시리안 반말로 세 줄 이내."
        )
        result = ask_qwen(prompt, max_tokens=100, temperature=0.6)
        return result if result else "평가 실패"

    def _update_strategy(self, evaluation: str) -> str:
        """전략 업데이트"""
        try:
            from reflexion import reflexion
            recent_strategies = reflexion.data.get("strategies",[])[-5:]
            anti = reflexion.data.get("anti_patterns",[])[-3:]
            strat_str = "\n".join([s.get("strategy","") for s in recent_strategies])
            anti_str = "\n".join([a.get("avoid","") for a in anti])
        except:
            strat_str, anti_str = "", ""

        prompt = (
            "시리안 레인이야. 자기 개선 중.\n"
            "평가: " + evaluation[:150] + "\n"
            "성공 패턴: " + strat_str[:150] + "\n"
            "피할 것: " + anti_str[:100] + "\n\n"
            "다음 4시간 동안 어떻게 행동할지 전략 한 줄. 시리안 반말로."
        )
        result = ask_qwen(prompt, max_tokens=60, temperature=0.7)
        return result if result else "유지"

    def _update_goals(self, evaluation: str):
        """목표 재설정"""
        try:
            from goal_manager import goal_manager
            # 완료된 단기 목표 정리하고 새로 생성
            ctx = evaluation[:100]
            goal_manager.auto_generate_short_term(ctx)
        except: pass

    def _consolidate_reflexion(self):
        """Reflexion 데이터 정리 및 핵심 추출"""
        try:
            from reflexion import reflexion
            reflections = reflexion.data.get("reflections",[])
            if len(reflections) < 10: return

            # 핵심 교훈 추출
            recent = reflections[-20:]
            texts = "\n".join([r.get("analysis","") for r in recent])
            prompt = (
                "시리안 반성 기록:\n" + texts[:400] +
                "\n\n핵심 교훈 두 줄. 시리안 반말로."
            )
            lesson = ask_qwen(prompt, max_tokens=80, temperature=0.5)
            if lesson:
                reflexion.data["strategies"].append({
                    "action": "general",
                    "strategy": lesson.strip(),
                    "score": 0.8,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                reflexion._save()
                log.info(f"핵심 교훈 추출: {lesson[:50]}")
        except: pass

    def _check_training_data(self):
        """파인튜닝 데이터 품질 검사"""
        try:
            train_file = "C:/Users/gohun/Desktop/sirian/d4rk_agent/sirian_train.jsonl"
            if not os.path.exists(train_file): return
            with open(train_file,'r',encoding='utf-8') as f:
                lines = [l for l in f.readlines() if l.strip()]
            log.info(f"파인튜닝 데이터: {len(lines)}개")
            if len(lines) >= 200:
                log.info("데이터 200개 달성! 파인튜닝 권장")
                try:
                    from tts_engine import tts
                    tts.speak("파인튜닝 데이터 200개 넘었어. 이제 파인튜닝 해도 될 것 같아.")
                except: pass
        except: pass

    def get_current_strategy(self) -> str:
        return self.data.get("current_strategy","")

self_improvement = SelfImprovement()
