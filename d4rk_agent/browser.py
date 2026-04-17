"""
SIRIAN BROWSER — 시리안 전용 Chrome 제어
자율 활동 시 혼자 웹 탐색
"""
import logging, time, re
log = logging.getLogger("browser")

class SirianBrowser:
    def __init__(self):
        self.driver = None
        self.enabled = False
        self._init()

    def _init(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            opts = Options()
            # 헤드리스 OFF — 창 보임
            # opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--window-size=900,650")
            opts.add_argument("--window-position=1920,0")  # 두 번째 모니터 or 우측 상단
            opts.add_argument("--lang=ko-KR")
            opts.add_argument("--disable-notifications")
            opts.add_argument("--disable-popup-blocking")
            opts.add_experimental_option("excludeSwitches", ["enable-logging"])
            opts.add_experimental_option("detach", True)  # 스크립트 종료 후에도 창 유지
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=opts)
            # 창 타이틀 설정
            self.driver.execute_script("document.title = '🔍 시리안 브라우저'")
            self.enabled = True
            log.info("브라우저 초기화 완료 (시리안 창)")
        except Exception as e:
            log.warning(f"브라우저 초기화 실패: {e}")
            self.enabled = False

    def search(self, query: str) -> str:
        """검색하고 결과 텍스트 반환"""
        if not self.enabled: return ""
        try:
            from selenium.webdriver.common.by import By
            url = f"https://search.naver.com/search.naver?query={query}"
            self.driver.get(url)
            time.sleep(2)
            # 검색 결과 텍스트 추출
            texts = []
            for sel in [".news_wrap", ".total_wrap", ".view_wrap", "article"]:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els[:3]:
                        t = el.text.strip()[:200]
                        if t: texts.append(t)
                except: pass
            result = "\n".join(texts[:5])
            log.info(f"검색 완료: {query[:30]}")
            return result or self._get_page_text()
        except Exception as e:
            log.error(f"검색 실패: {e}")
            return ""

    def visit(self, url: str) -> str:
        """URL 방문하고 내용 반환"""
        if not self.enabled: return ""
        try:
            self.driver.get(url)
            time.sleep(2)
            return self._get_page_text()
        except Exception as e:
            log.error(f"방문 실패: {e}")
            return ""

    def youtube_search(self, query: str) -> str:
        """유튜브 검색"""
        if not self.enabled: return ""
        try:
            from selenium.webdriver.common.by import By
            self.driver.get(f"https://www.youtube.com/results?search_query={query}")
            time.sleep(2)
            titles = []
            els = self.driver.find_elements(By.CSS_SELECTOR, "#video-title")
            for el in els[:5]:
                t = el.get_attribute("title") or el.text
                if t: titles.append(t.strip())
            return "\n".join(titles) if titles else ""
        except Exception as e:
            log.error(f"유튜브 검색 실패: {e}")
            return ""

    def _get_page_text(self) -> str:
        """현재 페이지 텍스트 추출"""
        try:
            from selenium.webdriver.common.by import By
            body = self.driver.find_element(By.TAG_NAME, "body")
            text = body.text[:2000]
            # 불필요한 내용 정리
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text.strip()
        except:
            return ""

    def close(self):
        if self.driver:
            try: self.driver.quit()
            except: pass

browser = SirianBrowser()
