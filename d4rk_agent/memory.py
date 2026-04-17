"""
SIRIAN AGENT — Memory System
"""
import json, os
from datetime import datetime
from collections import Counter

MEMORY_FILE = "d4rk_memory.json"

class Memory:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE,"r",encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return self._default()

    def _default(self):
        return {
            "observations": [],
            "activity_patterns": {},
            "tool_usage": {},
            "interests": [],
            "conversations": [],
            "chat_logs": [],
            "collected": [],
            "user_profile": {"name":"현승","role":"보안 연구원","tools":[],"preferences":[]},
            "agent_thoughts": [],
            "pending_suggestions": [],
            "relationship": {"intimacy": 0.1, "total_conversations": 0},
            "emotion": {
                "current": "무관심",
                "intensity": 0.3,
                "history": [],
                "mood_notes": []
            }
        }

    def save(self):
        # 누락된 키 보완
        for key, val in self._default().items():
            if key not in self.data:
                self.data[key] = val
        with open(MEMORY_FILE,"w",encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_observation(self, desc, detected_tools, activity):
        now = datetime.now()
        self.data["observations"].append({
            "time": now.strftime("%Y-%m-%d %H:%M"),
            "hour": now.hour, "activity": activity,
            "tools": detected_tools, "desc": desc[:200]
        })
        if len(self.data["observations"]) > 200:
            self.data["observations"] = self.data["observations"][-200:]
        h = str(now.hour)
        self.data["activity_patterns"].setdefault(h, []).append(activity)
        for t in detected_tools:
            self.data["tool_usage"][t] = self.data["tool_usage"].get(t,0) + 1
        self.save()

    def add_conversation_summary(self, summary):
        self.data["conversations"].append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "summary": summary
        })
        if len(self.data["conversations"]) > 100:
            self.data["conversations"] = self.data["conversations"][-100:]
        self.save()

    def add_chat_log(self, user_msg, response):
        """실제 대화 저장 (Fine-tuning 데이터용)"""
        self.data["chat_logs"].append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "user": user_msg[:500],
            "sirian": response[:500]
        })
        if len(self.data["chat_logs"]) > 1000:
            self.data["chat_logs"] = self.data["chat_logs"][-1000:]
        self.save()

    def add_collected(self, entry):
        """자율 수집 내용 저장 (껐다켜도 유지)"""
        self.data["collected"].append(entry)
        if len(self.data["collected"]) > 200:
            self.data["collected"] = self.data["collected"][-200:]
        self.save()

    def add_agent_thought(self, thought, category="general"):
        self.data["agent_thoughts"].append({
            "time": datetime.now().strftime("%H:%M"),
            "thought": thought, "category": category
        })
        if len(self.data["agent_thoughts"]) > 100:
            self.data["agent_thoughts"] = self.data["agent_thoughts"][-100:]
        self.save()

    def add_interest(self, topic):
        if topic not in self.data["interests"]:
            self.data["interests"].append(topic)
            self.save()

    def update_emotion(self, emotion, intensity=None, relationship_delta=0):
        e = self.data["emotion"]
        prev = e.get("current","무관심")
        e["current"] = emotion
        if intensity is not None:
            e["intensity"] = max(0.0, min(1.0, intensity))
        rel = self.data["relationship"]
        rel["intimacy"] = max(0.0, min(1.0, rel.get("intimacy",0.1) + relationship_delta))
        if prev != emotion:
            e.setdefault("history",[]).append({
                "time": datetime.now().strftime("%H:%M"),
                "from": prev, "to": emotion
            })
            if len(e["history"]) > 50:
                e["history"] = e["history"][-50:]
        self.save()

    def get_emotion_state(self):
        return self.data.get("emotion", {"current":"무관심","intensity":0.3,"history":[]})

    def get_relationship(self):
        return self.data.get("relationship", {"intimacy":0.1,"total_conversations":0})

    def get_emotion(self):
        return self.get_emotion_state()

    def get_relevant_context(self, user_msg):
        msg_lower = user_msg.lower()
        categories = {
            "보안/해킹": ["hack","cve","exploit","xss","sqli","ctf","dreamhack","hackthebox",
                         "tryhackme","burp","ida","ghidra","리버싱","취약점","웹해킹","rop","pwn"],
            "취업/면접": ["면접","취업","라온","라스컴","이력서","포트폴리오","회사","채용"],
            "코딩":      ["코드","python","javascript","버그","에러","함수","git"],
            "일상/휴식": ["밥","먹","자","피곤","쉬","게임","유튜브","영화","음악","아이돌"],
            "공부":      ["공부","학습","강의","문제","이해","모르"],
        }
        matched = None
        for cat, kws in categories.items():
            if any(k in msg_lower for k in kws):
                matched = cat; break

        obs = self.data.get("observations",[])
        convs = self.data.get("conversations",[])
        interests = self.data.get("interests",[])

        if matched:
            kws = categories[matched]
            rel_obs   = [o["desc"][:80] for o in obs[-30:] if any(k in o.get("desc","").lower() for k in kws)][:2]
            rel_convs = [c["summary"] for c in convs[-30:] if any(k in c.get("summary","").lower() for k in kws)][:2]
            rel_int   = [i for i in interests if any(k in i.lower() for k in kws)][:4]
        else:
            rel_obs   = [o["desc"][:60] for o in obs[-3:]]
            rel_convs = [c["summary"] for c in convs[-2:]]
            rel_int   = interests[-3:]

        top_tools = sorted(self.data.get("tool_usage",{}).items(), key=lambda x:x[1], reverse=True)[:3]
        parts = []
        if rel_int:   parts.append(f"관련 관심사: {', '.join(rel_int)}")
        if rel_convs: parts.append(f"관련 대화: {' / '.join(rel_convs[:2])}")
        if rel_obs:   parts.append(f"관련 활동: {rel_obs[0]}")
        if top_tools: parts.append(f"자주 쓰는 툴: {', '.join([t[0] for t in top_tools])}")
        if not parts: return ""
        return "[관련 기억]\n" + "\n".join(f"- {p}" for p in parts)

    def get_context_summary(self):
        obs = self.data.get("observations",[])[-10:]
        top_tools = sorted(self.data.get("tool_usage",{}).items(), key=lambda x:x[1], reverse=True)[:5]
        recent_activities = list(set([o["activity"] for o in obs if o.get("activity")]))[:5]
        recent_convs = self.data.get("conversations",[])[-5:]
        interests = self.data.get("interests",[])[-8:]
        thoughts = self.data.get("agent_thoughts",[])[-3:]
        hour = datetime.now().hour
        hour_pattern = self.data.get("activity_patterns",{}).get(str(hour),[])
        common = Counter(hour_pattern).most_common(1)
        time_p = f"이 시간대엔 주로 {common[0][0]}" if common else ""
        return (
            "[현승에 대해 알고 있는 것]\n"
            f"- 자주 쓰는 툴: {', '.join([t[0] for t in top_tools]) or '없음'}\n"
            f"- 최근 활동: {', '.join(recent_activities) or '없음'}\n"
            f"- 관심 주제: {', '.join(interests) or '없음'}\n"
            f"- {time_p}\n"
            f"- 최근 대화: {' / '.join([c['summary'] for c in recent_convs]) or '없음'}\n"
            f"- 시리안 생각: {' / '.join([t['thought'] for t in thoughts]) or '없음'}\n"
            "자연스럽게 대화에 녹여. 티 나게 말하지 마."
        ).strip()

    def get_pattern_insight(self):
        hour = str(datetime.now().hour)
        pattern = self.data.get("activity_patterns",{}).get(hour,[])
        if not pattern: return ""
        common = Counter(pattern).most_common(1)
        return f"이 시간대엔 주로 {common[0][0]} 하더라" if common else ""

    def get_recent_observations(self, n=5):
        return self.data.get("observations",[])[-n:]

    def add_mood_note(self, note):
        self.data["emotion"].setdefault("mood_notes",[]).append({
            "time": datetime.now().strftime("%H:%M"), "note": note
        })
        self.save()

memory = Memory()
