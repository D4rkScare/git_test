"""
SIRIAN ENHANCED MEMORY — Memory-to-Action 연결 강화
semantic + emotional + recency + importance 종합 스코어링
"""
import json, os, logging, numpy as np
from datetime import datetime
from utils import strip_chinese

log = logging.getLogger("enhanced_mem")
EMH_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/enhanced_memory.json"

class EnhancedMemory:
    def __init__(self):
        self.entries = []
        self._model  = None
        self._load()
        self._init_model()

    def _load(self):
        try:
            if os.path.exists(EMH_FILE):
                with open(EMH_FILE,'r',encoding='utf-8') as f:
                    self.entries = json.load(f).get("entries",[])
                log.info(f"Enhanced Memory 로드: {len(self.entries)}개")
        except: pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(EMH_FILE), exist_ok=True)
            with open(EMH_FILE,'w',encoding='utf-8') as f:
                json.dump({"entries": self.entries[-1000:]}, f, ensure_ascii=False)
        except: pass

    def _init_model(self):
        try:
            from utils import get_sentence_model
            self._model = get_sentence_model()
        except: pass

    def add(self, text: str, category: str = "general",
            emotion: str = "", importance: float = 0.5):
        """기억 추가 — 감정 태그 + 중요도 포함"""
        text = strip_chinese(text).strip()
        if not text or len(text) < 5: return

        entry = {
            "text":       text[:300],
            "category":   category,
            "emotion":    emotion,
            "importance": importance,
            "time":       datetime.now().strftime("%Y-%m-%d %H:%M"),
            "access_count": 0
        }
        if self._model:
            try:
                entry["vector"] = self._model.encode([text])[0].tolist()
            except: pass

        self.entries.append(entry)
        self.entries = self.entries[-1000:]
        self._save()

    def search(self, query: str, emotion: str = "",
               top_k: int = 5, min_importance: float = 0.0) -> list:
        """
        종합 스코어링 검색:
        - semantic similarity (0.4)
        - emotional relevance (0.2)
        - recency (0.2)
        - importance (0.2)
        """
        candidates = [e for e in self.entries
                     if e.get("importance",0) >= min_importance]
        if not candidates: return []

        q_vec = None
        if self._model:
            try:
                q_vec = self._model.encode([query])[0]
            except: pass

        scored = []
        now = datetime.now()

        for e in candidates:
            # 1. Semantic similarity
            sem = 0.3
            if q_vec is not None and "vector" in e:
                v = np.array(e["vector"])
                sem = float(np.dot(q_vec,v) /
                           (np.linalg.norm(q_vec)*np.linalg.norm(v)+1e-9))
            else:
                q_words = set(query.lower().split())
                e_words = set(e["text"].lower().split())
                sem = len(q_words & e_words) / max(len(q_words),1) * 0.5

            # 2. Emotional relevance
            emo_score = 0.5
            if emotion and e.get("emotion"):
                emo_score = 1.0 if e["emotion"] == emotion else 0.2

            # 3. Recency
            try:
                t = datetime.strptime(e["time"], "%Y-%m-%d %H:%M")
                days = (now - t).days
                recency = max(0.0, 1.0 - days/14)  # 2주 기준
            except:
                recency = 0.5

            # 4. Importance
            importance = e.get("importance", 0.5)

            # 종합
            score = (sem * 0.4 + emo_score * 0.2 +
                    recency * 0.2 + importance * 0.2)
            scored.append((score, e))

        scored.sort(reverse=True)
        results = [e for _, e in scored[:top_k]]

        # 접근 횟수 업데이트 (자주 쓰인 기억 = 중요)
        for e in results:
            e["access_count"] = e.get("access_count",0) + 1
            # 자주 접근되면 중요도 소폭 상승
            if e["access_count"] % 5 == 0:
                e["importance"] = min(1.0, e.get("importance",0.5) + 0.05)
        self._save()

        return results

    def get_context(self, query: str, emotion: str = "", top_k: int = 4) -> str:
        """프롬프트용 기억 컨텍스트"""
        results = self.search(query, emotion=emotion, top_k=top_k)
        if not results: return ""
        lines = []
        for r in results:
            t = r.get("time","")[:10]
            emo = f"[{r['emotion']}]" if r.get("emotion") else ""
            imp = f"★{r.get('importance',0.5):.1f}"
            lines.append(f"[{t}]{emo}{imp} {r['text'][:100]}")
        return "관련 기억:\n" + "\n".join(lines)

    def sync_from_all(self):
        """모든 기억 소스에서 동기화"""
        try:
            from memory import memory
            from emotion_engine import emotion_engine
            cur_emotion = emotion_engine.get_current().get("emotion","")

            # 대화 로그
            for log_entry in memory.data.get("chat_logs",[])[-30:]:
                u = log_entry.get("user","")
                s = log_entry.get("sirian","")
                if u and s:
                    self.add(f"현승: {u} / 시리안: {s}",
                            "chat", cur_emotion, importance=0.6)

            # 에이전트 생각
            for t in memory.data.get("agent_thoughts",[])[-20:]:
                thought = t.get("thought","")
                if thought:
                    imp = 0.8 if "연구" in thought else 0.5
                    self.add(thought, t.get("activity","general"),
                            cur_emotion, importance=imp)

            log.info(f"Enhanced Memory 동기화 완료 ({len(self.entries)}개)")
        except Exception as e:
            log.debug(f"동기화 오류: {e}")

enhanced_memory = EnhancedMemory()
