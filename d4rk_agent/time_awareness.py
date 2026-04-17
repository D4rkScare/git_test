"""
SIRIAN TIME AWARENESS — 시간 인식
하루 단위 구조, 과거-현재-미래 연결
"""
import json, os, logging, requests, re
from utils import ask_qwen, clean_response, strip_chinese
from datetime import datetime, timedelta

log = logging.getLogger("time")
TIMELINE_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/timeline.json"

class TimeAwareness:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "days": {},         # 날짜별 일일 요약
            "current_day": {},  # 오늘 활동
            "milestones": [],   # 중요 사건
        }
        try:
            if os.path.exists(TIMELINE_FILE):
                with open(TIMELINE_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(TIMELINE_FILE), exist_ok=True)
            with open(TIMELINE_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def log_event(self, event: str, category: str = "general"):
        """오늘 활동 기록"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.data["current_day"]:
            self.data["current_day"] = {today: []}
        self.data["current_day"].setdefault(today, []).append({
            "time": datetime.now().strftime("%H:%M"),
            "event": event[:100],
            "category": category
        })
        # 100개 초과시 오래된 것 제거
        if len(self.data["current_day"].get(today, [])) > 100:
            self.data["current_day"][today] = self.data["current_day"][today][-100:]
        self._save()

    def end_of_day_summary(self):
        """하루 마무리 요약 — qwen이 생성"""
        today = datetime.now().strftime("%Y-%m-%d")
        events = self.data["current_day"].get(today, [])
        if not events: return

        events_str = "\n".join([f"{e['time']} [{e['category']}] {e['event']}" for e in events[-20:]])
        prompt = (
            "시리안 레인이야. 오늘 하루 활동:\n" + events_str +
            "\n\n오늘 하루 짧게 요약해줘. 시리안 말투로. 150자 이내."
        )
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"num_predict":100,"temperature":0.7}},
                timeout=20
            )
            summary = resp.json().get("response","").strip()
            summary = re.sub(r'[\u4e00-\u9fff]+','',summary).strip()

            # days에 저장
            self.data["days"][today] = {
                "summary": summary,
                "event_count": len(events),
                "categories": list(set(e["category"] for e in events))
            }
            # current_day 초기화
            self.data["current_day"] = {}
            self._save()
            log.info(f"하루 요약: {summary[:60]}")

            # memory에도 저장
            try:
                from memory import memory
                memory.add_agent_thought(f"[일일요약] {summary}", "daily")
            except: pass
        except: pass

    def get_recent_days(self, n: int = 3) -> str:
        """최근 N일 요약"""
        days = sorted(self.data["days"].keys(), reverse=True)[:n]
        if not days: return ""
        lines = []
        for d in days:
            summary = self.data["days"][d].get("summary","")
            if summary:
                lines.append(f"{d}: {summary[:80]}")
        return "\n".join(lines)

    def get_for_prompt(self) -> str:
        today = datetime.now()
        weekdays = ["월","화","수","목","금","토","일"]
        weekday = weekdays[today.weekday()]
        time_str = today.strftime("%H:%M")
        hour = today.hour

        if 5 <= hour < 12: time_of_day = "아침"
        elif 12 <= hour < 18: time_of_day = "오후"
        elif 18 <= hour < 22: time_of_day = "저녁"
        else: time_of_day = "밤"

        recent = self.get_recent_days(2)
        result = f"지금: {weekday}요일 {time_str} ({time_of_day})"
        if recent:
            result += f"\n최근 기억:\n{recent}"
        return result

time_awareness = TimeAwareness()
