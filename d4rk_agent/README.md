# D4RK AGENT v1.0

## 실행 방법

### 1. START.bat 실행 (더블클릭)
자동으로 패키지 설치 후 브라우저 열림

### 2. 수동 실행
```
pip install -r requirements.txt
python main.py
```
브라우저에서 http://localhost:7865

---

## 설정

### ElevenLabs API 키
1. https://elevenlabs.io 가입
2. Profile → API Key 복사
3. `.env` 파일에 붙여넣기 OR UI 오른쪽 패널에서 입력

### 목소리 선택
- UI 오른쪽 → "목소리 목록" 클릭
- 원하는 목소리 클릭하면 Voice ID 자동 입력

---

## 기능

### 👁 화면 관찰 (20초마다 자동)
- 열린 윈도우 제목 분석
- 현재 활동 분류 (리버싱/CTF/코딩 등)
- 패턴 학습 → memory.json 저장

### 💬 대화
- 자연스러운 반말 대화
- 코드 작성/실행 요청 가능
- 웹 검색 요청 가능

### 🤖 자율 행동 (3분마다)
- 스스로 상황 파악
- 관련 추천 팝업으로 알림
- TTS로 말하기

### 🛡 Safety Layer (절대 보장)
- 파일/폴더 삭제 → 영구 차단
- 시스템 종료 → 영구 차단
- 레지스트리 수정 → 영구 차단
- 파일 쓰기 → 확인 필요
- 코드 실행 → 확인 필요

---

## 도구 (AI가 자동으로 사용)
- `search` — DuckDuckGo 검색
- `fetch_url` — 웹 페이지 읽기
- `run_code` — Python 코드 실행
- `read_file` — 파일 읽기
- `write_file` — 파일 저장 (확인 필요)
- `system_info` — 시스템 상태

## 필요한 것
- Python 3.10+
- Ollama (ollama.com) + qwen2.5:14b 모델
- ElevenLabs API 키 (유료, 월 $5~)
- RTX GPU 권장 (4070 Super 이상)
