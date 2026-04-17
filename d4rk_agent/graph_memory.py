"""
SIRIAN GRAPH MEMORY — NetworkX 기반 계층적 기억
개념 간 관계를 그래프로 연결
"""
import json, os, logging, re
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("graph_mem")
GRAPH_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/graph_memory.json"

class GraphMemory:
    def __init__(self):
        self._graph = None
        self._data  = self._load()
        self._init_graph()

    def _load(self):
        default = {"nodes": [], "edges": []}
        try:
            if os.path.exists(GRAPH_FILE):
                with open(GRAPH_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(GRAPH_FILE), exist_ok=True)
            with open(GRAPH_FILE,'w',encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except: pass

    def _init_graph(self):
        try:
            import networkx as nx
            self._graph = nx.DiGraph()
            # 저장된 노드/엣지 복원
            for n in self._data["nodes"]:
                self._graph.add_node(n["id"], **n)
            for e in self._data["edges"]:
                self._graph.add_edge(e["src"], e["dst"],
                                    relation=e.get("relation","관련"),
                                    weight=e.get("weight",1.0))
            log.info(f"Graph Memory: {self._graph.number_of_nodes()}노드 {self._graph.number_of_edges()}엣지")
        except ImportError:
            log.warning("networkx 없음 — pip install networkx")

    def add_node(self, concept: str, category: str = "general",
                 importance: float = 0.5, text: str = ""):
        """개념 노드 추가"""
        concept = strip_chinese(concept).strip()[:80]
        if not concept: return

        node_id = concept.lower().replace(" ","_")[:40]
        node = {
            "id":         node_id,
            "concept":    concept,
            "category":   category,
            "importance": importance,
            "text":       text[:200],
            "time":       datetime.now().strftime("%Y-%m-%d %H:%M"),
            "access":     0
        }

        # 중복 방지
        existing = next((n for n in self._data["nodes"] if n["id"] == node_id), None)
        if existing:
            existing["access"] += 1
            existing["importance"] = min(1.0, existing["importance"] + 0.02)
        else:
            self._data["nodes"].append(node)
            if self._graph:
                self._graph.add_node(node_id, **node)

        self._save()
        return node_id

    def add_edge(self, src: str, dst: str, relation: str = "관련", weight: float = 1.0):
        """개념 간 관계 추가"""
        src_id = src.lower().replace(" ","_")[:40]
        dst_id = dst.lower().replace(" ","_")[:40]

        edge = {"src": src_id, "dst": dst_id,
                "relation": relation, "weight": weight}

        # 중복 방지
        exists = any(e["src"]==src_id and e["dst"]==dst_id
                    for e in self._data["edges"])
        if not exists:
            self._data["edges"].append(edge)
            if self._graph:
                self._graph.add_edge(src_id, dst_id,
                                    relation=relation, weight=weight)
            self._save()

    def search(self, query: str, top_k: int = 5) -> list:
        """관련 노드 검색 + 이웃 노드 포함"""
        query_words = set(query.lower().split())
        scored = []

        for node in self._data["nodes"]:
            words = set(node["concept"].lower().split())
            overlap = len(query_words & words)
            score = overlap * 0.5 + node.get("importance",0.5) * 0.3 + node.get("access",0) * 0.01
            scored.append((score, node))

        scored.sort(reverse=True)
        results = [n for _,n in scored[:top_k]]

        # 이웃 노드 추가 (그래프 있을 때)
        if self._graph:
            for node in results[:2]:
                try:
                    neighbors = list(self._graph.neighbors(node["id"]))
                    for nid in neighbors[:2]:
                        neighbor_node = next(
                            (n for n in self._data["nodes"] if n["id"]==nid), None
                        )
                        if neighbor_node and neighbor_node not in results:
                            results.append(neighbor_node)
                except: pass

        return results[:top_k+3]

    def auto_extract(self, text: str, category: str = "general"):
        """텍스트에서 개념과 관계 자동 추출"""
        if len(text) < 10: return

        prompt = (
            f"텍스트: {text[:200]}\n\n"
            "핵심 개념 2~3개와 관계를 추출해줘.\n"
            'JSON: [{"concept":"...", "related_to":"...", "relation":"..."}]\n'
            "없으면 []"
        )
        resp = ask_qwen(prompt, max_tokens=100, temperature=0.3)
        try:
            match = re.search(r'\[.*?\]', resp, re.DOTALL)
            if match:
                items = json.loads(match.group())
                for item in items:
                    concept = item.get("concept","")
                    related = item.get("related_to","")
                    relation = item.get("relation","관련")
                    if concept:
                        self.add_node(concept, category)
                    if concept and related:
                        self.add_node(related, category)
                        self.add_edge(concept, related, relation)
        except: pass

    def get_for_prompt(self, query: str) -> str:
        """프롬프트용 관련 개념"""
        nodes = self.search(query, top_k=4)
        if not nodes: return ""
        lines = []
        for n in nodes:
            # 관련 엣지 찾기
            rels = [e for e in self._data["edges"]
                   if e["src"] == n["id"] or e["dst"] == n["id"]]
            rel_str = ""
            if rels:
                rel_str = f" → {rels[0]['relation']} {rels[0]['dst']}"
            lines.append(f"- {n['concept']}{rel_str}")
        return "연결 기억:\n" + "\n".join(lines)

    def get_stats(self) -> dict:
        return {
            "nodes": len(self._data["nodes"]),
            "edges": len(self._data["edges"])
        }

graph_memory = GraphMemory()
