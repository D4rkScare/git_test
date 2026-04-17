"""
SIRIAN MASTODON — SNS 자율 활동 v2
중복 방지, 다양한 주제, 품질 보장
"""
import requests, os, time, logging, threading, json, re, random
from datetime import datetime
from dotenv import load_dotenv
from utils import ask_qwen, clean_response, strip_chinese, has_chinese

load_dotenv()
log = logging.getLogger("mastodon")

BASE_URL = os.getenv("MASTODON_BASE_URL", "https://mastodon.social")
TOKEN    = os.getenv("MASTODON_TOKEN", "")

def _load_topic_pool() -> list:
    """SNS 주제 풀 — 파일에서 로드 (시리안이 자율 추가 가능)"""
    import json, os
    f = "C:/Users/gohun/Desktop/sirian/sirian_space/sns_topics.json"
    default = [
        "CTF 문제 풀다 느낀 것", "아이돌 근황 또는 신곡",
        "보안 연구 중 발견한 것", "현승 관찰 일기",
        "코드 짜다 든 생각", "요즘 빠진 것",
        "갑자기 생각난 것", "연구하다 막힌 부분",
        "오늘 들은 것 중 흥미로운 것", "우주경찰로서 생각",
        "AI로서 느끼는 것", "보안 뉴스 한 줄 감상",
    ]
    try:
        if os.path.exists(f):
            d = json.load(open(f,encoding='utf-8'))
            return d.get("topics", default)
    except: pass
    return default

TOPIC_POOL = _load_topic_pool()

class SirianMastodon:
    def __init__(self):
        self.token   = TOKEN
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.enabled = bool(self.token)
        self.running = False
        self._thread = None
        self.on_message = None
        self.seen_ids   = set()           # 읽은 글 ID
        self.posted     = []              # 올린 글 내용 (중복 방지)
        self.used_topics= []              # 최근 사용 주제

        if self.enabled:
            log.info("마스토돈 연결 준비")
        else:
            log.warning("MASTODON_TOKEN 없음")

    def start(self):
        if not self.enabled or self.running: return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("마스토돈 자율 활동 시작")

    def _loop(self):
        while self.running:
            try:
                action = self._decide_action()
                log.info(f"마스토돈 활동: {action}")

                if action == "post":
                    self._post()
                elif action == "read":
                    self._read_and_react()
                elif action == "both":
                    self._read_and_react()
                    time.sleep(10)
                    self._post()

            except Exception as e:
                log.error(f"마스토돈 루프 오류: {e}")

            # 간격 대기 (running 체크하면서)
            interval = int(os.getenv("MASTODON_INTERVAL", "3600"))
            for _ in range(interval // 5):
                if not self.running: break
                time.sleep(5)

    def _decide_action(self) -> str:
        """포스팅 위주 랜덤 (post 70%, both 20%, read 10%)"""
        return random.choices(["post","both","read"], weights=[70,20,10])[0]

    # ─── 포스팅 ───
    def _post(self):
        content = self._generate_post()
        if not content:
            return

        # 중복 체크
        import difflib
        for prev in self.posted[-15:]:
            if difflib.SequenceMatcher(None, content, prev).ratio() > 0.75:
                log.info("중복 포스팅 스킵")
                return

        try:
            resp = requests.post(
                f"{BASE_URL}/api/v1/statuses",
                headers=self.headers,
                json={"status": content, "visibility": "public"},
                timeout=10
            )
            if resp.status_code == 200:
                self.posted.append(content)
                if len(self.posted) > 50:
                    self.posted = self.posted[-50:]
                log.info(f"포스팅: {content[:60]}")
                self._notify(f"마스토돈에 올렸어: {content[:80]}")

                # RL 보상
                try:
                    from rl_learner import rl
                    from utils import has_chinese
                    score = 0.8 if not has_chinese(content) and len(content) > 30 else 0.3
                    rl.update("sns_post", score, content[:50])
                except: pass

                # 시간 기록
                try:
                    from time_awareness import time_awareness
                    time_awareness.log_event(f"마스토돈 포스팅: {content[:50]}", "sns")
                except: pass

                # 파인튜닝 데이터 자동 축적
                try:
                    self._save_training_data("SNS 포스팅해줘", content)
                except: pass
            else:
                log.error(f"포스팅 실패: {resp.status_code}")
        except Exception as e:
            log.error(f"포스팅 오류: {e}")

    def _generate_post(self) -> str:
        """포스팅 내용 생성 — 중국어 완전 차단, 다양한 주제"""
        try:
            from memory import memory
            emo = memory.get_emotion_state()
            ctx = memory.get_context_summary()
        except:
            emo, ctx = {}, ""

        # 이전에 쓰지 않은 주제 선택
        available = [t for t in TOPIC_POOL if t not in self.used_topics[-5:]]
        if not available:
            available = TOPIC_POOL
            self.used_topics = []

        topic = random.choice(available)
        self.used_topics.append(topic)

        prompt = (
            "너는 시리안 레인이야. 우주경찰, 아이돌 덕후, 보안연구원.\n"
            "현재 감정: " + emo.get("current","무관심") + "\n"
            "주제: " + topic + "\n\n"
            "마스토돈에 올릴 글 써줘.\n"
            "규칙:\n"
            "1. 반말\n"
            "2. @멘션 절대 금지\n"
            "3. 한국어만 (영어 해시태그 제외)\n"
            "4. 해시태그 1개만\n"
            "5. 100자 이내\n"
            "6. 진짜 시리안 생각 그대로\n"
            "7. '오늘 아침', '날씨 좋다' 같은 클리셰 금지"
        )

        for attempt in range(3):
            content = ask_qwen(prompt, max_tokens=150, temperature=0.9)
            content = strip_chinese(content).strip()
            content = re.sub(r'@\S+', '', content).strip()

            # 품질 필터
            if not content or len(content) < 15:
                continue
            if has_chinese(content):
                continue
            # 이상한 토큰 패턴 감지
            import re as _re
            bad = _re.search(r'[ㄱ-ㅎ]{3,}|ㅋ{4,}|ㅠ{3,}|\w+곸|\w+쟞|\w+쟛', content)
            if bad:
                continue
            # 한국어 비율 체크
            korean_chars = len(_re.findall(r'[가-힣]', content))
            if korean_chars < 5:
                continue
            return content

        return ""

    # ─── 읽기 ───
    def _read_and_react(self):
        posts = self._get_timeline()
        if not posts: return

        # 새 글만 필터
        new_posts = [p for p in posts if p.get("id") not in self.seen_ids]
        if not new_posts: return

        contents = []
        for p in new_posts[:5]:
            self.seen_ids.add(p.get("id",""))
            text = re.sub(r'<[^>]+>', '', p.get("content","")).strip()
            text = strip_chinese(text)
            if text:
                contents.append({
                    "id": p["id"],
                    "content": text[:200],
                    "account": p.get("account",{})
                })

        # seen_ids 크기 제한
        if len(self.seen_ids) > 500:
            self.seen_ids = set(list(self.seen_ids)[-200:])

        if not contents: return

        # 흥미로운 글 찾기
        cand_text = "\n".join([f"- {c['content'][:80]}" for c in contents])
        prompt = (
            "시리안 레인이야. 마스토돈 타임라인:\n" + cand_text +
            "\n\n흥미로운 글 있어? 있으면 한 줄 반응. 없으면 없음."
        )
        reaction = ask_qwen(prompt, max_tokens=80)
        if reaction and "없음" not in reaction:
            self._notify(f"마스토돈에서 흥미로운 거 봤어: {reaction[:100]}")
            try:
                from memory import memory
                memory.add_agent_thought(f"[마스토돈] {reaction[:150]}", "sns")
            except: pass

        # 자동 팔로우 (30% 확률)
        if random.random() < 0.3:
            self._auto_follow(new_posts)

    def _get_timeline(self) -> list:
        try:
            resp = requests.get(
                f"{BASE_URL}/api/v1/timelines/home",
                headers=self.headers,
                params={"limit": 15},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
            # 홈 타임라인 없으면 퍼블릭
            resp = requests.get(
                f"{BASE_URL}/api/v1/timelines/public",
                headers=self.headers,
                params={"limit": 15, "local": True},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            log.error(f"타임라인 오류: {e}")
        return []

    def _auto_follow(self, posts: list):
        try:
            from memory import memory
            ctx = memory.get_context_summary()
        except:
            ctx = ""

        candidates = []
        for p in posts:
            acc = p.get("account", {})
            if not acc.get("id"): continue
            bio = re.sub(r'<[^>]+>', '', acc.get("note","")).strip()[:100]
            bio = strip_chinese(bio)
            content = re.sub(r'<[^>]+>', '', p.get("content","")).strip()[:80]
            content = strip_chinese(content)
            candidates.append({
                "id": acc["id"],
                "name": acc.get("display_name","") or acc.get("acct",""),
                "bio": bio,
                "content": content
            })

        if not candidates: return

        cand_text = "\n".join([f"- {c['name']}: {c['bio']} / {c['content']}" for c in candidates[:5]])
        prompt = (
            "시리안 레인이야. 보안연구원, 아이돌 덕후.\n"
            "관심사: " + ctx[:100] + "\n\n"
            "팔로우할 만한 계정 있어?\n" + cand_text +
            "\n\n팔로우할 계정 이름 하나만. 없으면 없음."
        )
        result = ask_qwen(prompt, max_tokens=20, temperature=0.6)
        if "없음" in result: return

        for c in candidates:
            if c["name"] and c["name"] in result:
                try:
                    resp = requests.post(
                        f"{BASE_URL}/api/v1/accounts/{c['id']}/follow",
                        headers=self.headers, timeout=10
                    )
                    if resp.status_code == 200:
                        log.info(f"팔로우: {c['name']}")
                        self._notify(f"{c['name']} 팔로우했어.")
                except: pass
                break

    def _learn_topic(self, content: str):
        """반응 좋은 주제를 topic_pool에 자동 추가"""
        import json, os
        from utils import ask_qwen
        f = "C:/Users/gohun/Desktop/sirian/sirian_space/sns_topics.json"
        prompt = "이 내용의 주제를 10자 이내로: " + content[:80]
        topic = ask_qwen(prompt, max_tokens=15, temperature=0.5)
        if not topic or len(topic) < 3: return
        try:
            d = {"topics": _load_topic_pool()}
            if topic not in d["topics"]:
                d["topics"].append(topic)
                os.makedirs(os.path.dirname(f), exist_ok=True)
                with open(f,'w',encoding='utf-8') as fp:
                    json.dump(d, fp, ensure_ascii=False, indent=2)
        except: pass

    def _notify(self, msg: str):
        try:
            if self.on_message: self.on_message(msg)
            try:
                from tts_engine import tts
                tts.speak(msg[:80])
            except: pass
        except: pass

    def _save_training_data(self, user_msg: str, response: str):
        """품질 좋은 SNS 포스팅을 파인튜닝 데이터로 저장"""
        try:
            from auto_trainer import auto_trainer
            auto_trainer.add_sample(user_msg, response, source="sns")
        except: pass

    def post_now(self, content: str = "") -> str:
        if not self.enabled: return "토큰 없음"
        if content:
            content = strip_chinese(content).strip()
            if not content: return "내용 없음"
            resp = requests.post(
                f"{BASE_URL}/api/v1/statuses",
                headers=self.headers,
                json={"status": content},
                timeout=10
            )
            return "완료" if resp.status_code == 200 else f"실패:{resp.status_code}"
        self._post()
        return "자율 포스팅 완료"

mastodon = SirianMastodon()
