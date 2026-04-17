"""
SIRIAN EPISODE MEMORY — 진짜 연속성
중요 사건을 에피소드로 저장, 시간이 지나도 이어지는 기억
"""
import json, os, logging, re
from datetime import datetime, timedelta
from utils import ask_qwen, clean_response

log = logging.getLogger("episode")
EP_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/episodes.json"

class EpisodeMemory:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {"episodes": [], "pending": []}
        try:
            if os.path.exists(EP_FILE):
                with open(EP_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(EP_FILE), exist_ok=True)
            with open(EP_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def record(self, user_msg: str, response: str, reward: float):
        """대화를 에피소드 후보로 등록"""
        if reward < 0.6: return  # 평범한 건 스킵
        self.data["pending"].append({
            "user": user_msg[:200],
            "response": response[:200],
            "reward": reward,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        self.data["pending"] = self.data["pending"][-20:]
        # 10개 쌓이면 에피소드 추출
        if len(self.data["pending"]) >= 5:
            self._extract_episode()
        self._save()

    def _extract_episode(self):
        """pending에서 기억할 만한 에피소드 추출"""
        pending = self.data["pending"][-10:]
        conv = "\n".join([f"현승: {p['user'][:80]}\n시리안: {p['response'][:80]}" for p in pending])
        prompt = (
            "시리안 레인이야. 최근 대화:\n" + conv +
            "\n\n이 중에서 나중에도 기억할 만한 중요한 순간이 있어?\n"
            "있으면 JSON: {\"event\": \"한 줄 요약\", \"emotion\": \"감정\", \"importance\": 0.0~1.0}\n"
            "없으면 null"
        )
        result = ask_qwen(prompt, max_tokens=80, temperature=0.5)
        if not result or "null" in result.lower(): return
        match = re.search(r'\{[^}]+\}', result)
        if match:
            try:
                ep = json.loads(match.group())
                ep["time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.data["episodes"].append(ep)
                self.data["episodes"] = self.data["episodes"][-200:]
                self.data["pending"] = []
                log.info(f"에피소드 저장: {ep.get('event','')[:50]}")
            except: pass

    def get_relevant(self, context: str, n: int = 3) -> str:
        """현재 맥락과 관련된 과거 에피소드 반환"""
        episodes = self.data.get("episodes", [])
        if not episodes: return ""

        # 최근 + 관련도 높은 것
        recent = episodes[-20:]
        scored = []
        ctx_words = set(context.lower().split())
        for ep in recent:
            event = ep.get("event","").lower()
            overlap = len(ctx_words & set(event.split()))
            # 최근성 점수
            try:
                t = datetime.strptime(ep["time"], "%Y-%m-%d %H:%M")
                days_ago = (datetime.now() - t).days
                recency = max(0, 1 - days_ago / 30)
            except:
                recency = 0.5
            score = overlap * 0.5 + recency * 0.5 + ep.get("importance", 0.5) * 0.3
            scored.append((score, ep))

        scored.sort(reverse=True)
        top = scored[:n]
        if not top: return ""

        lines = []
        for _, ep in top:
            t = ep.get("time","")[:10]
            lines.append(f"[{t}] {ep.get('event','')} (감정:{ep.get('emotion','')})")
        return "과거 기억:\n" + "\n".join(lines)

    def get_followup(self) -> str:
        """미완결 에피소드 — 나중에 물어볼 것"""
        recent = self.data.get("episodes", [])[-5:]
        unresolved = [e for e in recent if e.get("importance", 0) > 0.7]
        if not unresolved: return ""
        ep = unresolved[-1]
        # 3일 이상 지난 미완결
        try:
            t = datetime.strptime(ep["time"], "%Y-%m-%d %H:%M")
            if (datetime.now() - t).days >= 1:
                return ep.get("event","")
        except: pass
        return ""

episode_memory = EpisodeMemory()
