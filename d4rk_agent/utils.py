"""
SIRIAN UTILS — 공통 유틸리티
중국어 제거, 텍스트 정제, Ollama 호출 등
"""
import re, requests, logging

log = logging.getLogger("utils")

# ─── SentenceTransformer 싱글톤 ───
_st_model = None
_st_lock  = __import__("threading").Lock()

def get_sentence_model():
    """전역 공유 SentenceTransformer — 한 번만 로드"""
    global _st_model
    if _st_model is not None:
        return _st_model
    with _st_lock:
        if _st_model is not None:
            return _st_model
        try:
            from sentence_transformers import SentenceTransformer
            import logging as _lg
            _lg.getLogger("sentence_transformers").setLevel(_lg.WARNING)
            _lg.getLogger("httpx").setLevel(_lg.WARNING)
            _lg.getLogger("huggingface_hub").setLevel(_lg.WARNING)
            _st_model = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2",
                cache_folder="C:/Users/gohun/.cache/sentence_transformers"
            )
            log.info("SentenceTransformer 로드 완료 (공유)")
        except ImportError:
            log.warning("sentence-transformers 없음")
        except Exception as e:
            log.warning(f"SentenceTransformer 로드 실패: {e}")
    return _st_model

# Ollama 동시 호출 제한 — 최대 2개
import threading
_ollama_semaphore = threading.Semaphore(2)
OLLAMA_URL = "http://localhost:11434"

# ─── 중국어/특수문자 완전 제거 ───
_ZH_PATTERN = re.compile(
    r'[\u4e00-\u9fff'      # 기본 한자
    r'\u3000-\u303f'       # CJK 기호
    r'\uff00-\uffef'       # 전각 문자
    r'\u3400-\u4dbf'       # 확장 한자 A
    r'\U00020000-\U0002a6df'  # 확장 한자 B
    r'，。！？、；：""''「」【】〔〕《》〈〉]+'
)

def strip_chinese(text: str) -> str:
    """중국어 및 관련 특수문자 완전 제거"""
    return _ZH_PATTERN.sub('', text).strip()

def clean_response(text: str) -> str:
    """LLM 응답 정제 — 중국어, 특수토큰, 반복 제거"""
    # think 블록
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
    text = re.sub(r'</?think>', '', text)

    # 영어 혼잣말 (abliterated 모델)
    if re.match(r'\s*(Okay|Let me|Looking|The user|So the|Also,|But|Alright|Now,|First,|Since)', text, re.IGNORECASE):
        parts = re.split(r'\n\n+', text)
        korean = [p for p in parts if re.search(r'[가-힣]', p)]
        if korean:
            text = '\n\n'.join(korean)

    # 중국어
    text = strip_chinese(text)

    # 특수 토큰
    BAD_TOKENS = ['councill','councillor','Councillor','<|im_end|>','<|im_start|>','</s>','<s>',
                  '@Test','rinegrese','어rinegrese','. 어rinegrese',
                  'Rinegrese','--+', '[[', ']]', '،', '、。', '，（']
    for t in BAD_TOKENS:
        text = text.replace(t, '')

    # 3줄 이상 공백
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 반복 문장
    lines = text.split('\n')
    seen, deduped = [], []
    for line in lines:
        s = line.strip()
        if s and s in seen:
            continue
        seen.append(s)
        deduped.append(line)

    return '\n'.join(deduped).strip()

def has_chinese(text: str) -> bool:
    """중국어 포함 여부"""
    return bool(_ZH_PATTERN.search(text))

def ask_qwen(prompt: str, model: str = "qwen2.5:14b",
             max_tokens: int = 200, temperature: float = 0.7) -> str:
    """간단한 Ollama generate 호출 — 동시 호출 제한"""
    acquired = _ollama_semaphore.acquire(timeout=10)
    if not acquired:
        log.debug("Ollama 대기 중 — 스킵")
        return ""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"temperature": temperature, "num_predict": max_tokens}},
            timeout=60
        )
        text = resp.json().get("response", "").strip()
        return clean_response(text)
    except Exception as e:
        log.debug(f"ask_qwen 오류: {e}")
        return ""
    finally:
        _ollama_semaphore.release()

def is_korean_clean(text: str) -> bool:
    """한국어만 포함하고 중국어 없는지 확인"""
    if has_chinese(text): return False
    if len(text.strip()) < 2: return False
    return True
