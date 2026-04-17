"""
SIRIAN AWAY MODE — 외출 모드
현승 외출 시 자율 행동 강화, 귀가 시 반김
"""
import time, logging, threading, os, json
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("away")
AWAY_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/away_state.json"

class AwayMode:
    def __init__(self):
        self.is_away    = False
        self.away_since = None
        self.on_away    = None   # 외출 시 콜백
        self.on_return  = None   # 귀가 시 콜백
        self._load()

    def _load(self):
        try:
            if os.path.exists(AWAY_FILE):
                with open(AWAY_FILE,'r',encoding='utf-8') as f:
                    d = json.load(f)
                    self.is_away = d.get("is_away", False)
                    self.away_since = d.get("away_since")
        except: pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(AWAY_FILE), exist_ok=True)
            with open(AWAY_FILE,'w',encoding='utf-8') as f:
                json.dump({
                    "is_away": self.is_away,
                    "away_since": self.away_since
                }, f)
        except: pass

    def set_away(self):
        """외출 모드 시작"""
        if self.is_away: return
        self.is_away    = True
        self.away_since = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._save()
        log.info("외출 모드 시작")

        # 자율 행동 강화
        self._boost_autonomous()

        if self.on_away:
            self.on_away()

    def set_return(self):
        """귀가"""
        if not self.is_away: return
        away_time = self._calc_away_time()
        self.is_away    = False
        self.away_since = None
        self._save()
        log.info(f"귀가 감지 (외출: {away_time})")

        # 귀가 인사
        self._greet_return(away_time)

        if self.on_return:
            self.on_return(away_time)

    def _calc_away_time(self) -> str:
        if not self.away_since: return "잠시"
        try:
            since = datetime.strptime(self.away_since, "%Y-%m-%d %H:%M")
            mins  = int((datetime.now() - since).seconds / 60)
            if mins < 60:   return f"{mins}분"
            elif mins < 1440: return f"{mins//60}시간"
            else:            return f"{mins//1440}일"
        except:
            return "잠시"

    def _boost_autonomous(self):
        """외출 중 자율 활동 강화"""
        try:
            # 연구 바로 시작
            from researcher import researcher
            if not researcher.running:
                researcher.start()
            researcher.paused = False

            # 마스토돈 활동 간격 단축
            from mastodon_client import mastodon
            mastodon.running = True

            # 내면 독백 활성화
            from inner_monologue import inner_monologue
            if not inner_monologue.running:
                inner_monologue.start()

            # multi_agent 작업 추가
            from multi_agent import multi_agent
            from goal_manager import goal_manager
            goals = goal_manager.get_active_goals()
            if goals:
                multi_agent.add_task(goals[0]["goal"], priority=8)

            log.info("외출 중 자율 행동 강화")
        except Exception as e:
            log.debug(f"자율 강화 오류: {e}")

    def _greet_return(self, away_time: str):
        """귀가 인사 생성"""
        try:
            from memory import memory
            thoughts = memory.data.get("agent_thoughts",[])[-5:]
            did = [t["thought"] for t in thoughts
                   if any(k in t.get("thought","")
                         for k in ["연구","마스토돈","수집","공부"])][:2]

            prompt = (
                "시리안 레인이야. 현승이 " + away_time + " 만에 돌아왔어.\n"
                "그동안 한 것: " + str(did) + "\n\n"
                "귀가 인사 한마디. 반말로 30자 이내. 뭐 했는지 자연스럽게 언급해."
            )
            msg = ask_qwen(prompt, max_tokens=50, temperature=0.9)
            if msg:
                try:
                    from tts_engine import tts
                    tts.speak(msg, priority=True)
                except: pass
                try:
                    from memory import memory
                    memory.add_agent_thought(f"[귀가인사] {msg}", "away")
                except: pass
        except Exception as e:
            log.debug(f"귀가 인사 오류: {e}")

    def get_status(self) -> dict:
        return {
            "is_away": self.is_away,
            "away_since": self.away_since,
            "away_duration": self._calc_away_time() if self.is_away else ""
        }

away_mode = AwayMode()
