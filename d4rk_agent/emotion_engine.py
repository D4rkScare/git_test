"""
SIRIAN EMOTION ENGINE — 감정의 지속성
하루 종일 감정이 유지되고 누적되는 시스템
"""
import json, os, logging, re
from datetime import datetime, timedelta
from utils import ask_qwen, clean_response

log = logging.getLogger("emotion_engine")
EMO_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/emotion_state.json"

# 감정별 기본 지속시간 (분) — 강한 감정은 며칠까지
EMO_DURATION = {
    "뿌듯":   180,
    "즐거움": 120,
    "집중":   60,
    "걱정됨": 360,
    "무관심": 30,
    "빡침":   90,     # 빡치면 오래 감
    "신남":   180,
    "우울":   600,    # 우울은 오래 지속
    "설렘":   120,
    "서운함": 480,    # 새로 추가
    "실망":   300,    # 새로 추가
}

# 감정 전이 규칙 (트리거 → 다음 감정)
EMO_TRANSITIONS = {
    "칭찬받음":    ("뿌듯", 0.8),
    "무시당함":    ("빡침", 0.7),
    "흥미로운것":  ("집중", 0.6),
    "아이돌얘기":  ("신남", 0.9),
    "오류/실패":   ("걱정됨", 0.5),
    "해결됨":      ("뿌듯", 0.7),
    "지루함":      ("무관심", 0.4),
}

class EmotionEngine:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "current": "무관심",
            "intensity": 0.5,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "history": [],         # 오늘 감정 히스토리
            "daily_baseline": "무관심",  # 오늘 전반적 기분
            "triggers": [],        # 감정 변화 원인
        }
        try:
            if os.path.exists(EMO_FILE):
                with open(EMO_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(EMO_FILE), exist_ok=True)
            with open(EMO_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def update(self, new_emotion: str, intensity: float, trigger: str = ""):
        """감정 업데이트 — 며칠 단위 지속성"""
        old = self.data["current"]
        old_intensity = self.data["intensity"]

        # 현재 감정 지속시간 확인 (분 단위)
        try:
            started = datetime.strptime(self.data["started_at"], "%Y-%m-%d %H:%M")
            duration_min = (datetime.now() - started).total_seconds() / 60
            max_duration = EMO_DURATION.get(old, 60)

            # 아직 강한 감정 유지 중이면 쉽게 안 바뀜
            if duration_min < max_duration * 0.5 and old != new_emotion:
                if old_intensity > 0.7 and intensity < old_intensity:
                    intensity = old_intensity * 0.75 + intensity * 0.25
                    new_emotion = old if old_intensity * 0.75 > intensity * 0.5 else new_emotion
        except: pass

        # 며칠 지속 감정 — 강도 높으면 lingering_emotion에 저장
        if intensity > 0.75 and new_emotion in ["빡침","우울","서운함","실망","걱정됨"]:
            self.data["lingering_emotion"] = {
                "emotion":   new_emotion,
                "intensity": intensity * 0.4,  # 잔여 강도
                "trigger":   trigger[:60],
                "set_at":    datetime.now().strftime("%Y-%m-%d %H:%M")
            }

        # 감정 기록
        self.data["history"].append({
            "emotion": new_emotion,
            "intensity": round(intensity, 2),
            "trigger": trigger[:50] if trigger else "",
            "time": datetime.now().strftime("%H:%M")
        })
        self.data["history"] = self.data["history"][-50:]

        self.data["current"] = new_emotion
        self.data["intensity"] = round(intensity, 2)
        self.data["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        if trigger:
            self.data["triggers"].append({"trigger": trigger[:80], "emotion": new_emotion})
            self.data["triggers"] = self.data["triggers"][-20:]

        # 하루 전반 기준선 업데이트
        self._update_daily_baseline()
        self._save()

        if old != new_emotion:
            log.info(f"감정 변화: {old} → {new_emotion} ({intensity:.1f}) [{trigger[:30]}]")

    def _update_daily_baseline(self):
        """오늘 전반적 기분 계산"""
        today = self.data["history"][-20:]
        if not today: return
        # 가장 많이 나온 감정
        from collections import Counter
        counts = Counter([h["emotion"] for h in today])
        self.data["daily_baseline"] = counts.most_common(1)[0][0]

    def decay(self):
        """시간 경과에 따른 자연 감정 감쇠"""
        try:
            started = datetime.strptime(self.data["started_at"], "%Y-%m-%d %H:%M")
            duration_min = (datetime.now() - started).total_seconds() / 60
            max_dur = EMO_DURATION.get(self.data["current"], 60)

            if duration_min > max_dur:
                baseline = self.data["daily_baseline"]
                if self.data["current"] != baseline:
                    self.data["current"] = baseline
                    self.data["intensity"] = max(0.3, self.data["intensity"] * 0.7)
                    self.data["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    self._save()
                    log.info(f"감정 감쇠 → {baseline}")
        except: pass

        # 잔여 감정 서서히 감소
        try:
            lingering = self.data.get("lingering_emotion",{})
            if lingering and lingering.get("intensity",0) > 0:
                lingering["intensity"] = max(0, lingering["intensity"] - 0.02)
                if lingering["intensity"] <= 0:
                    self.data.pop("lingering_emotion", None)
                self._save()
        except: pass

    def get_current(self) -> dict:
        return {
            "emotion": self.data["current"],
            "intensity": self.data["intensity"],
            "baseline": self.data["daily_baseline"],
        }

    def get_for_prompt(self) -> str:
        e = self.data
        today_emotions = list(set([h["emotion"] for h in e["history"][-10:]]))
        result = f"현재 감정: {e['current']} (강도:{e['intensity']:.1f})"
        if e["daily_baseline"] != e["current"]:
            result += f"\n오늘 전반 기분: {e['daily_baseline']}"
        if today_emotions:
            result += f"\n오늘 감정 흐름: {' → '.join(today_emotions[-5:])}"
        return result

    def detect_trigger(self, text: str) -> str:
        """텍스트에서 감정 트리거 감지 — 학습된 키워드 사용"""
        import json, os
        # 학습된 트리거 파일
        trigger_file = "C:/Users/gohun/Desktop/sirian/sirian_space/emo_config.json"
        triggers = {}
        try:
            if os.path.exists(trigger_file):
                d = json.load(open(trigger_file,encoding='utf-8'))
                triggers = d.get("triggers", {})
        except: pass

        # 기본 트리거 (학습으로 확장 가능)
        default_triggers = {
            "아이돌얘기": ["itzy","뉴진스","아이돌","컴백","노래","kpop"],
            "칭찬받음":   ["잘했","좋아","맞아","대단","굿","오","진짜"],
            "무시당함":   ["틀렸","아니야","별로","그냥","됐어"],
            "흥미로운것": ["cve","exploit","ctf","해킹","취약점","pwn","rev"],
            "해결됨":     ["해결","완료","됐어","성공","풀었","맞았"],
        }
        # 학습 트리거 우선
        merged = {**default_triggers, **triggers}

        text_lower = text.lower()
        for trigger, keywords in merged.items():
            if any(k in text_lower for k in keywords):
                return trigger
        return ""

    def learn_trigger(self, text: str, emotion: str):
        """새로운 감정 트리거 자동 학습"""
        import json, os
        trigger_file = "C:/Users/gohun/Desktop/sirian/sirian_space/emo_config.json"
        try:
            d = {}
            if os.path.exists(trigger_file):
                d = json.load(open(trigger_file,encoding='utf-8'))
            triggers = d.get("triggers", {})
            words = [w for w in text.lower().split() if len(w) > 1][:2]
            if words:
                if emotion not in triggers:
                    triggers[emotion] = []
                for w in words:
                    if w not in triggers[emotion]:
                        triggers[emotion].append(w)
                d["triggers"] = triggers
                os.makedirs(os.path.dirname(trigger_file), exist_ok=True)
                with open(trigger_file,'w',encoding='utf-8') as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
        except: pass

emotion_engine = EmotionEngine()
