from utils import get_sentence_model
"""
SIRIAN VECTOR MEMORY — 벡터 기반 기억 검색
sentence-transformers + FAISS로 의미 기반 검색
"""
import json, os, logging, numpy as np
from datetime import datetime
from utils import strip_chinese

log = logging.getLogger("vector")
VECTOR_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/vector_store.json"

class VectorMemory:
    def __init__(self):
        self.model = None
        self.index = None
        self.entries = []
        self._ready = False
        self._init()

    def _init(self):
        """sentence-transformers + FAISS 초기화"""
        try:
            from sentence_transformers import SentenceTransformer
            import faiss
            self.model = get_sentence_model()
            self._load()
            self._ready = True
            log.info(f"Vector Memory 준비 ({len(self.entries)}개)")
        except ImportError:
            log.warning("sentence-transformers 또는 faiss 없음 — 해시 기반으로 대체")
            self._load()
        except Exception as e:
            log.warning(f"Vector Memory 초기화 실패: {e}")
            self._load()

    def _load(self):
        try:
            if os.path.exists(VECTOR_FILE):
                with open(VECTOR_FILE,'r',encoding='utf-8') as f:
                    data = json.load(f)
                    self.entries = data.get("entries", [])
        except: pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(VECTOR_FILE), exist_ok=True)
            with open(VECTOR_FILE,'w',encoding='utf-8') as f:
                json.dump({"entries": self.entries[-500:]}, f,
                          ensure_ascii=False, indent=2)
        except: pass

    def add(self, text: str, category: str = "general", metadata: dict = None):
        """텍스트를 벡터로 저장"""
        text = strip_chinese(text).strip()
        if not text or len(text) < 5: return

        entry = {
            "text": text[:300],
            "category": category,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "metadata": metadata or {}
        }

        if self._ready and self.model:
            try:
                vec = self.model.encode([text])[0].tolist()
                entry["vector"] = vec
            except: pass

        self.entries.append(entry)
        self.entries = self.entries[-500:]
        self._save()

    def search(self, query: str, top_k: int = 3, category: str = None) -> list:
        """의미 기반 검색"""
        if not self.entries: return []

        candidates = self.entries
        if category:
            candidates = [e for e in self.entries if e.get("category") == category]
        if not candidates: return []

        # sentence-transformers 사용 가능하면 벡터 검색
        if self._ready and self.model:
            try:
                q_vec = self.model.encode([query])[0]
                scored = []
                for e in candidates:
                    if "vector" not in e: continue
                    v = np.array(e["vector"])
                    cos = np.dot(q_vec, v) / (np.linalg.norm(q_vec) * np.linalg.norm(v) + 1e-9)
                    scored.append((cos, e))
                scored.sort(reverse=True)
                return [e for _, e in scored[:top_k]]
            except: pass

        # 폴백: 키워드 매칭
        query_words = set(query.lower().split())
        scored = []
        for e in candidates:
            words = set(e["text"].lower().split())
            overlap = len(query_words & words)
            scored.append((overlap, e))
        scored.sort(reverse=True)
        return [e for _, e in scored[:top_k] if _[0] > 0]

    def get_context(self, query: str, top_k: int = 3) -> str:
        """프롬프트용 관련 기억"""
        results = self.search(query, top_k=top_k)
        if not results: return ""
        lines = []
        for r in results:
            t = r.get("time","")[:10]
            lines.append(f"[{t}][{r.get('category','')}] {r['text'][:100]}")
        return "관련 기억:\n" + "\n".join(lines)

    def sync_from_memory(self):
        """memory.json에서 중요 내용 벡터화"""
        try:
            from memory import memory
            logs = memory.data.get("chat_logs",[])[-50:]
            thoughts = memory.data.get("agent_thoughts",[])[-30:]
            for log_entry in logs:
                user = log_entry.get("user","")
                sirian = log_entry.get("sirian","")
                if user and sirian:
                    self.add(f"현승: {user} / 시리안: {sirian}", "chat")
            for t in thoughts:
                thought = t.get("thought","")
                if thought:
                    self.add(thought, t.get("activity","general"))
            log.info(f"memory 동기화 완료 ({len(self.entries)}개)")
        except Exception as e:
            log.debug(f"동기화 실패: {e}")

vector_memory = VectorMemory()
