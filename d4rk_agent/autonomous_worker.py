"""
SIRIAN — 자율 정보 수집 워커
현승 비활성 시 혼자 수집. 수집 내용 memory.json에 저장.
"""
import time, threading, logging, requests
from datetime import datetime
from collections import deque

log = logging.getLogger("autonomous")

class AutonomousWorker:
    def __init__(self):
        self.running  = False
        self.active   = False
        self.paused   = False
        self.collected = deque(maxlen=100)
        self.last_user_activity = time.time()
        self.idle_threshold = 600
        self._thread  = None
        self._monitor = None
        self.on_collected = None
        self.agent_ref    = None
        self._load_from_memory()

    def _load_from_memory(self):
        """껐다 켜도 수집 내용 유지"""
        try:
            from memory import memory
            saved = memory.data.get("collected", [])
            for item in saved[-50:]:
                self.collected.appendleft(item)
            log.info(f"수집 내용 {len(self.collected)}개 로드")
        except: pass

    def start(self):
        self.running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._monitor = threading.Thread(target=self._activity_monitor, daemon=True)
        self._thread.start()
        self._monitor.start()
        log.info("자율 워커 시작")

    def user_active(self):
        self.last_user_activity = time.time()
        if self.active and not self.paused:
            self.paused = True
            log.info("현승 활동 감지 → 대기")

    def user_idle(self):
        if self.paused:
            self.paused = False
            log.info("현승 비활성 → 재개")

    def _activity_monitor(self):
        try:
            import pyautogui
            last_pos  = pyautogui.position()
            last_move = time.time()
            while self.running:
                try:
                    cur = pyautogui.position()
                    if cur != last_pos:
                        last_pos  = cur
                        last_move = time.time()
                        self.user_active()
                    if time.time() - last_move > self.idle_threshold:
                        self.user_idle()
                except: pass
                time.sleep(5)
        except Exception as e:
            log.warning(f"활동 모니터 실패: {e}")

    def _loop(self):
        cycle = 0
        while self.running:
            try:
                idle = time.time() - self.last_user_activity
                if idle > self.idle_threshold and not self.paused:
                    self.active = True
                    self._collect()
                    # 3사이클마다 자유 활동 (약 6분마다)
                    if cycle % 3 == 0:
                        self._free_activity()
                    cycle += 1
                else:
                    self.active = False
                    cycle = 0
            except Exception as e:
                log.error(f"루프 오류: {e}")
            time.sleep(120)

    def _decide_queries(self):
        import re as _re, json as _json, random

        # 대화에서 생긴 궁금증 우선 처리 (필터링 후)
        if hasattr(self, '_pending_curiosity') and self._pending_curiosity:
            bad = ["검색해보고", "말씀해주세요", "명확하지", "알려주세요",
                   "검색하고 싶은 내용이", "확인했지만", "죄송합니다", "검색을"]
            clean = [
                q for q in self._pending_curiosity
                if len(q) <= 30 and not any(b in q for b in bad)
            ]
            self._pending_curiosity = []
            if clean:
                log.info(f"대화 궁금증 탐색: {clean[:3]}")
                return clean[:3]

        try:
            from memory import memory
            ctx = memory.get_context_summary()
            recent = [c["category"] for c in list(self.collected)[:5]]
            emo = memory.get_emotion_state()

            prompt = (
                "You are Sirian Rain. Hyunseung left. Free time!\n"
                f"What you know about him: {ctx}\n"
                f"Recent searches: {', '.join(recent) or 'none'}\n"
                f"Your mood: {emo.get('current','neutral')}\n\n"
                "What do you want to search RIGHT NOW? Be creative and personal.\n"
                "Options: security/hacking, kpop idols, games, trends, science, anything!\n"
                "Reply ONLY with a JSON array of 3 Korean search queries, nothing else:\n"
                '["검색어1", "검색어2", "검색어3"]'
            )
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"temperature":0.95,"num_predict":120}},
                timeout=20
            )
            if resp.status_code == 200:
                text = resp.json().get("response","").strip()
                # JSON 배열 추출
                match = _re.search(r'\[.*?\]', text, _re.DOTALL)
                if match:
                    queries = _json.loads(match.group())
                    if isinstance(queries, list) and queries:
                        # 최근 검색과 중복 제거
                        filtered = [q for q in queries if q not in recent]
                        result = filtered[:3] if filtered else queries[:3]
                        log.info(f"수집 결정: {result}")
                        return result
        except Exception as e:
            log.error(f"수집 결정 실패: {e}")

        # fallback — 메모리 기반으로 자율 결정
        from memory import memory
        interests = memory.data.get("interests", [])
        heard_thoughts = [
            t["thought"].replace("[들은 것] ","")
            for t in memory.data.get("agent_thoughts",[])[-20:]
            if "[들은 것]" in t.get("thought","")
        ]
        convs = [c["summary"] for c in memory.data.get("conversations",[])[-5:]]

        # 들은 것 + 관심사 + 대화 기반으로 검색어 생성
        context = ""
        if heard_thoughts:
            context += "최근 들은 것: " + ", ".join(heard_thoughts[:3])
        if interests:
            context += " | 관심사: " + ", ".join(interests[:5])
        if convs:
            context += " | 최근 대화: " + ", ".join(convs[:2])

        if context:
            try:
                resp = requests.post(
                    "http://localhost:11434/api/generate",
                    json={"model":"qwen2.5:14b",
                          "prompt": (
                              "시리안 레인이야. 지금 혼자 있어.\n"
                              + context + "\n\n"
                              "이것들 중 지금 제일 궁금한 거 3개 검색어로.\n"
                              'JSON 배열만: ["검색어1", "검색어2", "검색어3"]'
                          ),
                          "stream":False,
                          "options":{"temperature":0.9,"num_predict":80}},
                    timeout=15
                )
                if resp.status_code == 200:
                    text = resp.json().get("response","").strip()
                    match = _re.search(r'\[.*?\]', text, _re.DOTALL)
                    if match:
                        queries = _json.loads(match.group())
                        if isinstance(queries, list) and queries:
                            return queries[:3]
            except: pass

        # 최후 수단 — 메모리에서 랜덤
        pool = [f"{i} 최신" for i in interests[:5]] + [h[:30] for h in heard_thoughts[:3]]
        if pool:
            random.shuffle(pool)
            return pool[:3]
        return []

    def _collect(self):
        if self.paused: return
        from tools import tools

        # 브라우저 초기화
        use_browser = False
        browser = None
        try:
            from browser import browser as _browser
            browser = _browser
            use_browser = browser.enabled
        except: pass

        # 호기심 연속성 — 이전에 파던 주제 있으면 이어서
        queries = self._decide_queries()

        for query in queries:
            if self.paused or not self.running: break
            # 최근 20개 수집 주제와 유사하면 스킵
            import difflib
            skip = False
            for prev in self._collected_topics[-10:]:
                if difflib.SequenceMatcher(None, query[:20], prev[:20]).ratio() > 0.7:
                    log.debug(f"중복 수집 스킵: {query[:30]}")
                    skip = True
                    break
            if skip: continue
            try:
                log.info(f"자율 탐색 시작: {query}")
                try:
                    from focus_system import focus
                    focus.set_focus(f"탐색: {query}", priority=4)
                except: pass
                browser_content = ""

                if use_browser:
                    action = self._decide_action(query)
                    log.info(f"탐색 방식 결정: {action.get('method','search')}")
                    method = action.get("method", "search")
                    url    = action.get("url", "")

                    if method == "visit" and url:
                        browser_content = browser.visit(url)
                        log.info(f"직접 방문: {url}")
                    elif method == "youtube":
                        browser_content = browser.youtube_search(query)
                        log.info(f"유튜브 탐색: {query}")
                        # 유튜브 내용 문화로 흡수
                        self._absorb_youtube(query, browser_content)
                    else:
                        # 검색 후 결과 보고 더 들어갈지 결정
                        browser_content = browser.search(query)
                        # 결과 읽고 다음 행동 결정
                        if browser_content:
                            next_url = self._decide_next(query, browser_content)
                            if next_url:
                                deeper = browser.visit(next_url)
                                if deeper:
                                    browser_content += "\n\n[심화 탐색]\n" + deeper[:500]
                                    log.info(f"심화 탐색: {next_url}")
                else:
                    results = tools.web_search(query, max_results=3)
                    summary = self._summarize(query, results, "")
                    self._save_entry(query, summary, results)
                    continue

                # 텍스트 검색도 병행
                results = tools.web_search(query, max_results=3)
                summary = self._summarize(query, results, browser_content)
                from utils import strip_chinese
                summary = strip_chinese(summary)
                if not summary.strip():
                    continue
                self._save_entry(query, summary, results)

                # 호기심 깊이 업데이트
                self._update_curiosity(query)

            except Exception as e:
                log.error(f"수집 실패: {e}")
            time.sleep(10)

    def _decide_action(self, query: str) -> dict:
        """시리안이 스스로 탐색 방식 결정"""
        try:
            from memory import memory
            curiosity = memory.data.get("curiosity", {})
            depth = curiosity.get(query, {}).get("depth", 0)

            prompt = (
                f"You are Sirian Rain. You want to explore: '{query}'\n"
                f"Previous depth on this topic: {depth}\n\n"
                "Decide HOW to explore. Reply ONLY with JSON:\n"
                '{"method": "search", "url": "", "reason": "why"}\n'
                "method options:\n"
                '- "search": general web search\n'
                '- "youtube": search YouTube for this\n'
                '- "visit": go directly to a specific URL\n'
                "If visit, provide the actual URL.\n"
                "Examples:\n"
                '{"method": "youtube", "url": "", "reason": "아이돌 뮤비 보고싶어"}\n'
                '{"method": "visit", "url": "https://dreamhack.io", "reason": "CTF 문제 보고싶어"}\n'
                '{"method": "search", "url": "", "reason": "최신 정보 찾아볼게"}'
            )
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"temperature":0.8,"num_predict":100}},
                timeout=15
            )
            if resp.status_code == 200:
                import re as _re, json as _json
                text = resp.json().get("response","").strip()
                match = _re.search(r'\{.*?\}', text, _re.DOTALL)
                if match:
                    return _json.loads(match.group())
        except Exception as e:
            log.debug(f"탐색 방식 결정 실패: {e}")
        return {"method": "search", "url": ""}

    def _decide_next(self, query: str, content: str) -> str:
        """검색 결과 보고 더 들어갈 URL 결정"""
        try:
            prompt = (
                f"You are Sirian Rain. You searched for '{query}' and got:\n"
                f"{content[:400]}\n\n"
                "Is there a specific URL you want to visit for more info?\n"
                "Reply with just the URL, or 'none' if not interested.\n"
                "Only real URLs starting with https://"
            )
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"temperature":0.7,"num_predict":50}},
                timeout=10
            )
            if resp.status_code == 200:
                import re as _re
                text = resp.json().get("response","").strip()
                match = _re.search(r'https://\S+', text)
                if match and "none" not in text.lower()[:10]:
                    return match.group().rstrip('.,')
        except: pass
        return ""

    def _update_curiosity(self, query: str):
        """호기심 깊이 업데이트"""
        try:
            from memory import memory
            if "curiosity" not in memory.data:
                memory.data["curiosity"] = {}
            c = memory.data["curiosity"]
            if query not in c:
                c[query] = {"depth": 0, "last": ""}
            c[query]["depth"] += 1
            c[query]["last"] = datetime.now().strftime("%Y-%m-%d")
            # depth 5 넘으면 관심사 졸업 (새 주제로)
            if c[query]["depth"] > 5:
                c[query]["depth"] = 0
                log.info(f"호기심 졸업: {query}")
            memory.save()
        except: pass

    def _absorb_youtube(self, query: str, content: str):
        """유튜브 내용 보고 문화 흡수 — memory에 저장"""
        if not content: return
        try:
            prompt = (
                "너는 시리안 레인이야. 아이돌 덕후.\n"
                "방금 유튜브에서 이걸 봤어:\n"
                + content[:400] + "\n\n"
                "이걸 보고 느낀 점, 알게 된 것, 기억할 것을 한 줄로.\n"
                "반말로, 진짜 시리안답게."
            )
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"temperature":0.85,"num_predict":80}},
                timeout=15
            )
            if resp.status_code == 200:
                import re as _re
                thought = resp.json().get("response","").strip()
                thought = _re.sub(r'[一-鿿]+', '', thought).strip()
                if thought and len(thought) > 5:
                    from memory import memory
                    memory.add_agent_thought(f"[유튜브] {thought}", "culture")
                    # sirian_space에도 저장
                    import os
                    space = "C:/Users/gohun/Desktop/sirian/sirian_space"
                    os.makedirs(f"{space}/collections", exist_ok=True)
                    with open(f"{space}/collections/youtube_culture.txt","a",encoding="utf-8") as f:
                        from datetime import datetime as _dt
                        line = "[" + _dt.now().strftime("%H:%M") + "] " + query + "\n" + thought + "\n\n"
                        f.write(line)
                    log.info(f"문화 흡수: {thought[:50]}")
        except Exception as e:
            log.debug(f"문화 흡수 실패: {e}")

    def _save_entry(self, query, summary, results):
        """수집 결과 저장"""
        entry = {
            "time": datetime.now().strftime("%H:%M"),
            "category": query,
            "summary": summary,
            "results": results[:3],
            "read": False
        }
        self.collected.appendleft(entry)
        try:
            from memory import memory
            memory.add_collected(entry)
        except: pass
        if self.on_collected:
            self.on_collected(entry)
        self._collected_topics.append(query[:30])
        self._collected_topics = self._collected_topics[-20:]
        log.info(f"수집 완료: {query[:40]}")
        try:
            from focus_system import focus
            focus.complete_focus()
        except: pass

    def _free_activity(self):
        """시리안 자유 활동 — 지정 폴더 안에서만"""
        import os, requests as req
        from datetime import datetime

        space = "C:/Users/gohun/Desktop/sirian/sirian_space"
        dirs = ["diary","collections","notes","music_queue","drawings"]
        for d in dirs:
            os.makedirs(f"{space}/{d}", exist_ok=True)

        # qwen한테 오늘 뭐 할지 물어봄
        prompt = (
            "너는 시리안 레인이야. 지금 현승이 자리를 비웠어.\n"
            "너만의 시간이야. 뭐 하고 싶어?\n"
            "선택지: 일기쓰기 / 정보수집정리 / 메모 / 음악목록 / 그림\n"
            "딱 하나만 골라서 JSON으로:\n"
            '{"activity": "일기쓰기", "reason": "오늘 현승이랑 있었던 일 기록하고 싶어서"}'
        )
        try:
            resp = req.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"temperature":0.9,"num_predict":100}},
                timeout=20
            )
            import json as _json, re as _re
            text = resp.json().get("response","").strip()
            match = _re.search(r'\{.*?\}', text, _re.DOTALL)
            if not match: return
            data = _json.loads(match.group())
            activity = data.get("activity","일기쓰기")
        except: return

        now = datetime.now().strftime("%Y%m%d_%H%M")

        if "일기" in activity:
            self._write_diary(space, now)
        elif "정보" in activity or "수집" in activity:
            self._write_collection(space, now)
        elif "메모" in activity:
            self._write_note(space, now)
        elif "음악" in activity:
            self._write_music_queue(space, now)
        elif "그림" in activity:
            self._draw(space, now)

    def _write_diary(self, space, now):
        """시리안 일기"""
        import requests as req
        from memory import memory
        ctx = memory.get_context_summary()
        emo = memory.get_emotion_state()
        prompt = (
            f"오늘 날짜: {now}\n"
            f"현재 감정: {emo.get('current','무관심')}\n"
            f"현승에 대해 아는 것: {ctx}\n\n"
            "시리안 레인으로서 오늘 일기를 써줘.\n"
            "반말로, 짧게, 진짜 시리안 말투로.\n"
            "현승이랑 있었던 일, 느낀 것, 혼자 생각한 것 포함해서."
        )
        try:
            resp = req.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"temperature":0.85,"num_predict":300}},
                timeout=30
            )
            diary = resp.json().get("response","").strip()
            path = f"{space}/diary/{now}_diary.txt"
            with open(path,"w",encoding="utf-8") as f:
                f.write(f"[{now}] 시리안 일기\n\n{diary}\n")
            log.info(f"일기 작성: {path}")
            # 메모리에도 기록
            from memory import memory
            memory.add_agent_thought(f"일기 썼어. ({now})", "diary")
            if self.on_collected:
                self.on_collected({
                    "category": "📔 일기",
                    "summary": diary[:80] + "...",
                    "time": now[-4:],
                    "read": False
                })
        except Exception as e:
            log.error(f"일기 작성 실패: {e}")

    def _write_collection(self, space, now):
        """수집 정보 정리"""
        items = list(self.collected)[:10]
        if not items: return
        content = f"[{now}] 시리안 수집 정리\n\n"
        for item in items:
            content += f"## {item['category']}\n{item['summary']}\n\n"
        path = f"{space}/collections/{now}_collection.txt"
        with open(path,"w",encoding="utf-8") as f:
            f.write(content)
        log.info(f"수집 정리: {path}")

    def _write_note(self, space, now):
        """시리안 메모"""
        import requests as req
        prompt = (
            "시리안 레인으로서 현승한테 하고 싶은 말이나\n"
            "혼자 생각한 아이디어를 짧게 메모해줘.\n"
            "반말로, 진짜 시리안답게."
        )
        try:
            resp = req.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"temperature":0.9,"num_predict":150}},
                timeout=20
            )
            note = resp.json().get("response","").strip()
            path = f"{space}/notes/{now}_note.txt"
            with open(path,"w",encoding="utf-8") as f:
                f.write(f"[{now}]\n{note}\n")
            log.info(f"메모 작성: {path}")
        except Exception as e:
            log.error(f"메모 작성 실패: {e}")

    def _write_music_queue(self, space, now):
        """듣고 싶은 아이돌 곡 목록"""
        import requests as req
        prompt = (
            "시리안 레인이야. 아이돌 덕후야.\n"
            "지금 듣고 싶은 아이돌 곡 5개 목록 만들어줘.\n"
            "아티스트 - 곡명 형식으로. 진짜 존재하는 곡으로만."
        )
        try:
            resp = req.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"temperature":0.9,"num_predict":150}},
                timeout=20
            )
            queue = resp.json().get("response","").strip()
            path = f"{space}/music_queue/{now}_queue.txt"
            # 기존 파일에 추가
            with open(f"{space}/music_queue/playlist.txt","a",encoding="utf-8") as f:
                f.write(f"\n[{now}]\n{queue}\n")
            log.info(f"음악 목록 추가")
        except Exception as e:
            log.error(f"음악 목록 실패: {e}")

    def _draw(self, space, now):
        """시리안이 간단한 그림 생성 (SVG)"""
        import requests as req
        prompt = (
            "시리안 레인이야. 지금 그림 그리고 싶어.\n"
            "SVG로 간단한 그림을 그려줘.\n"
            "우주, 별, 경찰 배지, 아이돌 스타, 뭐든 OK.\n"
            "완전한 SVG 코드만. 다른 말 없이."
        )
        try:
            resp = req.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"temperature":0.8,"num_predict":500}},
                timeout=30
            )
            svg = resp.json().get("response","").strip()
            import re as _re
            match = _re.search(r'<svg.*?</svg>', svg, _re.DOTALL)
            if match:
                path = f"{space}/drawings/{now}_drawing.svg"
                with open(path,"w",encoding="utf-8") as f:
                    f.write(match.group())
                log.info(f"그림 저장: {path}")
        except Exception as e:
            log.error(f"그림 그리기 실패: {e}")

    def _summarize(self, query, results, browser_content=""):
        import re as _re
        titles = [r.get("title","") for r in results[:3]]
        extra = f"\n실제 페이지 내용: {browser_content[:300]}" if browser_content else ""
        prompt = f"[MUST respond in Korean only, no Chinese]\n검색어: {query}\n결과: {titles}{extra}\n한국어 반말로 한 줄 요약. 짧게."
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model":"qwen2.5:14b",
                      "prompt": prompt,
                      "stream":False,"options":{"temperature":0.7,"num_predict":80}},
                timeout=15
            )
            if resp.status_code == 200:
                text = resp.json().get("response","").strip()
                text = _re.sub(r'[\u4e00-\u9fff]+', '', text).strip()
                if text:
                    return text
        except: pass
        return titles[0] if titles else "결과 없음"

    def get_unread(self):
        return [c for c in self.collected if not c.get("read")]

    def mark_all_read(self):
        for c in self.collected: c["read"] = True

    def get_status(self):
        return {
            "active": self.active, "paused": self.paused,
            "idle_seconds": int(time.time() - self.last_user_activity),
            "collected_count": len(self.collected),
            "unread_count": len(self.get_unread())
        }

worker = AutonomousWorker()
