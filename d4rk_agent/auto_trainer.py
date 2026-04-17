"""
SIRIAN AUTO TRAINER — 파인튜닝 데이터 자동 수집
보상 높은 대화만 자동으로 jsonl에 추가
"""
import json, os, logging
from datetime import datetime
from utils import clean_response

log = logging.getLogger("trainer")
TRAIN_FILE = "C:/Users/gohun/Desktop/sirian/d4rk_agent/sirian_train.jsonl"
MIN_REWARD = 0.7  # 이 점수 이상만 저장

SYSTEM_PROMPT = "너는 시리안 레인이야. SPS(우주경찰) 소속 AI 에이전트.\n성격: 시크한 냉미녀, 편해지면 발랄, 승부욕 강함, 다혈질, 아이돌 덕후(ITZY 좋아함).\n고현승 = 주인님.\n말투: 기본 반말. \"요/습니다/드릴게요\" 절대 금지. 짧게 핵심만."

class AutoTrainer:
    def __init__(self):
        self._count = self._count_existing()

    def _count_existing(self) -> int:
        try:
            if os.path.exists(TRAIN_FILE):
                with open(TRAIN_FILE, 'r', encoding='utf-8') as f:
                    return sum(1 for line in f if line.strip())
        except: pass
        return 0

    def add_sample(self, user_msg: str, response: str,
                   reward: float = 1.0, source: str = "chat"):
        """좋은 대화를 학습 데이터로 저장"""
        if reward < MIN_REWARD:
            return

        # 정제
        user_msg = clean_response(user_msg).strip()
        response = clean_response(response).strip()

        if not user_msg or not response:
            return
        if len(response) < 5 or len(response) > 500:
            return

        sample = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
                {"role": "assistant", "content": response}
            ]
        }

        try:
            with open(TRAIN_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')
            self._count += 1
            log.info(f"학습 데이터 추가 [{source}] (총 {self._count}개) reward:{reward:.2f}")
        except Exception as e:
            log.error(f"학습 데이터 저장 오류: {e}")

    def get_count(self) -> int:
        return self._count

auto_trainer = AutoTrainer()
