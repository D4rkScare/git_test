"""
D4RK AGENT — Tool Suite
에이전트가 사용할 수 있는 도구들. 안전한 것만.
"""
import os, re, subprocess, tempfile, sys, json, logging
import requests
from bs4 import BeautifulSoup
from safety import safety

log = logging.getLogger("tools")


def verify_tool(task: str, tool_name: str) -> bool:
    from utils import ask_qwen
    parts = ["태스크: ", task[:80], "\n도구: ", tool_name, "\n이 도구가 적합해? 예/아니오만."]
    prompt = "".join(parts)
    resp = ask_qwen(prompt, max_tokens=5, temperature=0.2)
    return "예" in (resp or "") or "yes" in (resp or "").lower()


class Tools:

    # ══ 웹 검색 ══
    def web_search(self, query: str, max_results: int = 5) -> list:
        """DuckDuckGo 검색 (API 키 불필요)"""
        try:
            url = "https://html.duckduckgo.com/html/"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.post(url, data={"q": query}, headers=headers, timeout=8)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for r in soup.select(".result__body")[:max_results]:
                title_el = r.select_one(".result__title")
                snippet_el = r.select_one(".result__snippet")
                url_el = r.select_one(".result__url")
                if title_el:
                    results.append({
                        "title": title_el.get_text(strip=True),
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                        "url": url_el.get_text(strip=True) if url_el else ""
                    })
            return results
        except Exception as e:
            log.error(f"검색 실패: {e}")
            return [{"title": "검색 실패", "snippet": str(e), "url": ""}]

    def fetch_url(self, url: str, max_chars: int = 3000) -> str:
        """URL 내용 가져오기"""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=8)
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script","style","nav","footer","header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return text[:max_chars]
        except Exception as e:
            return f"페이지 가져오기 실패: {e}"

    # ══ 코드 실행 ══
    def run_python(self, code: str, confirm_callback=None) -> dict:
        """Python 코드 안전 실행"""
        check = safety.check_code(code)
        if check.get("blocked"):
            return {"success": False, "output": check["reason"], "blocked": True}
        if check.get("needs_confirm"):
            if confirm_callback:
                confirmed = confirm_callback(check["reason"])
                if not confirmed:
                    return {"success": False, "output": "사용자가 취소했습니다.", "cancelled": True}
            else:
                return {"success": False, "output": check["reason"], "needs_confirm": True}

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                             delete=False, encoding="utf-8") as f:
                f.write(code)
                tmp = f.name

            result = subprocess.run(
                [sys.executable, tmp],
                capture_output=True, text=True, timeout=30
            )
            os.unlink(tmp)
            output = result.stdout + (("\n[STDERR]\n" + result.stderr) if result.stderr else "")
            return {
                "success": result.returncode == 0,
                "output": output[:2000] or "(출력 없음)",
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "타임아웃 (30초 초과)"}
        except Exception as e:
            return {"success": False, "output": f"실행 오류: {e}"}

    def run_powershell(self, cmd: str, confirm_callback=None) -> dict:
        """PowerShell 명령 안전 실행 (확인 필요)"""
        check = safety.check_code(cmd)
        if check.get("blocked"):
            return {"success": False, "output": check["reason"], "blocked": True}

        if confirm_callback:
            confirmed = confirm_callback(f"PowerShell 실행:\n{cmd}")
            if not confirmed:
                return {"success": False, "output": "취소됨"}

        try:
            result = subprocess.run(
                ["powershell", "-Command", cmd],
                capture_output=True, text=True, timeout=15, encoding="cp949"
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout[:2000] or result.stderr[:500] or "(출력 없음)"
            }
        except Exception as e:
            return {"success": False, "output": str(e)}

    # ══ 파일 작업 (읽기/생성만, 삭제 절대 불가) ══
    def read_file(self, path: str) -> dict:
        """파일 읽기"""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(5000)
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "content": str(e)}

    def write_file(self, path: str, content: str, confirm_callback=None) -> dict:
        """파일 쓰기 (확인 필요)"""
        check = safety.check_action("write_file", path)
        if check.get("blocked"):
            return {"success": False, "message": check["reason"]}
        if confirm_callback:
            confirmed = confirm_callback(f"파일 저장: {path}\n({len(content)}자)")
            if not confirmed:
                return {"success": False, "message": "취소됨"}
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "message": f"{path} 저장됨"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def list_files(self, path: str = ".") -> list:
        """폴더 내용 읽기"""
        try:
            items = []
            for entry in os.scandir(path):
                items.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": entry.stat().st_size if entry.is_file() else 0
                })
            return sorted(items, key=lambda x: (x["type"] == "file", x["name"]))
        except Exception as e:
            return [{"name": str(e), "type": "error", "size": 0}]

    # ══ 클립보드 ══
    def get_clipboard(self) -> str:
        try:
            import pyperclip
            return pyperclip.paste()
        except:
            return ""

    def set_clipboard(self, text: str):
        try:
            import pyperclip
            pyperclip.copy(text)
        except:
            pass

    # ══ 시스템 정보 (읽기만) ══
    def get_system_info(self) -> dict:
        import platform, psutil
        return {
            "os": platform.system(),
            "cpu": psutil.cpu_percent(),
            "memory": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("C:\\" if platform.system()=="Windows" else "/").percent
        }

tools = Tools()
