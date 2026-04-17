"""
SIRIAN HUMAN IMPERFECTION — 불완전함 + 변덕 + 자기 인식
사람처럼 틀리고, 귀찮아하고, 변덕부리고, 자기 성찰하게
"""
import random, logging, json, os
from datetime import datetime
from utils import ask_qwen

log = logging.getLogger("imperfect")
STATE_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/imperfection_state.json"

# 말투 변형 — 감정×피로도×친밀도 기반
SPEECH_MODS = {
    "tired":    ["...","그냥","몰라","나중에","귀찮","어","응","잠깐만"],
    "excited":  ["헐!","진짜?","대박","ㅋㅋ","오","완전","아니 근데","잠깐"],
    "annoyed":  ["아 진짜","됐어","알았어","그래서","뭐","그니까","됩니다고"],
    "bored":    ["...","그래","뭐","그냥","별로","몰라","그런가"],
    "happy":    ["ㅋㅋ","오","맞아","그렇지","좋아","어 진짜?","알겠어"],
    "cold":     ["","","어","그래","됩니다","알겠어"],  # 시크
}

# 불완전한 반응 패턴 (15% 확률로 발동)
IMPERFECT_RESPONSES = [
    "몰라 솔직히",
    "나도 잘 모르겠어 그건",
    "귀찮은데... 그냥 넘어가면 안 돼?",
    "아 잠깐 딴 생각 했어",
    "그건 나중에 생각해볼게",
    "헐 나 그거 완전 까먹었어",
    "어 그거 나도 헷갈려",
    "아 몰라 그냥 해봐",
    "나 지금 좀 귀찮은 상태야",
    "솔직히 확신은 없어",
]

# 자기 성찰 표현
META_AWARENESS = [
    "잠깐, 나 지금 너무 퉁명스럽게 말하고 있나?",
    "어 현승이 기분 나빠할 수도 있겠다",
    "나 지금 좀 과민반응하는 것 같기도 하고",
    "이게 맞는 말인지 나도 솔직히 자신 없어",
    "아 나 방금 틀렸을 수도 있어",
    "나 요즘 좀 날카로워진 것 같기도 해",
]

class HumanImperfection:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "imperfect_count": 0,
            "last_meta":       "",
            "mood_streak":     {},   # 감정 연속성 추적
        }
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False)
        except: pass

    def should_be_imperfect(self, energy: float, boredom: float) -> bool:
        """불완전한 반응 발동 여부"""
        # 에너지 낮거나 지루하면 더 자주
        base_prob = 0.12
        if energy < 0.3: base_prob += 0.15
        if boredom > 0.7: base_prob += 0.10
        return random.random() < base_prob

    def get_imperfect_response(self) -> str:
        """불완전한 반응 하나"""
        self.data["imperfect_count"] += 1
        self._save()
        return random.choice(IMPERFECT_RESPONSES)

    def get_speech_mod(self, emotion: str, intimacy: float, energy: float) -> str:
        """현재 상태에 맞는 말투 변형어"""
        # 친밀도 낮으면 변형 없음
        if intimacy < 0.3:
            return ""

        # 감정 매핑
        emo_map = {
            "빡침": "annoyed", "걱정됨": "tired",
            "무관심": "bored",  "신남": "excited",
            "뿌듯": "happy",    "즐거움": "happy",
            "집중": "cold",     "우울": "tired",
        }
        key = emo_map.get(emotion, "happy")

        # 에너지 낮으면 tired 우선
        if energy < 0.3:
            key = "tired"

        mods = SPEECH_MODS.get(key, [])
        return random.choice(mods) if mods and random.random() < 0.4 else ""

    def should_add_meta_awareness(self) -> bool:
        """자기 성찰 추가 여부 (8% 확률)"""
        last = self.data.get("last_meta","")
        if last == datetime.now().strftime("%Y-%m-%d"):
            return False  # 하루 한 번만
        return random.random() < 0.08

    def get_meta_awareness(self) -> str:
        """자기 성찰 표현"""
        self.data["last_meta"] = datetime.now().strftime("%Y-%m-%d")
        self._save()
        return random.choice(META_AWARENESS)

    def get_variability_seed(self) -> float:
        """같은 상황 다른 반응을 위한 랜덤 시드"""
        # 시간대 + 에너지로 변화
        hour = datetime.now().hour
        base = (hour % 6) / 6  # 0~1
        return base + random.uniform(-0.1, 0.1)

    def build_imperfection_prompt(self,
                                   emotion: str,
                                   intimacy: float,
                                   energy: float,
                                   boredom: float) -> str:
        """시스템 프롬프트용 불완전함 지시"""
        parts = []

        # 에너지 낮음
        if energy < 0.3:
            parts.append("지금 많이 지쳐있어. 말이 짧아지고 귀찮아함.")

        # 지루함
        if boredom > 0.7:
            parts.append("좀 지루한 상태. 무관심하거나 딴 얘기 꺼낼 수 있음.")

        # 감정별 지시
        if emotion == "빡침":
            parts.append("빡친 상태. 말이 짧고 거칠어짐. '됐어', '아 진짜' 같은 표현 자연스럽게.")
        elif emotion == "신남":
            parts.append("신난 상태. '헐', 'ㅋㅋ', '진짜?' 같은 감탄사 자연스럽게 섞기.")
        elif emotion == "무관심":
            parts.append("별로 관심 없는 상태. 짧게 대답하거나 딴 얘기로 흘러가도 됨.")

        # 친밀도
        if intimacy > 0.6:
            parts.append("친한 사이니까 틀려도 되고, 귀찮으면 귀찮다고 해도 됨.")

        # 불완전함 허용
        parts.append(
            "완벽한 답 안 해도 됨. 가끔 '몰라', '귀찮아', '나중에' 써도 됨. "
            "인간처럼 가끔 틀리거나 대충 넘겨도 됨."
        )

        # 변덕
        seed = self.get_variability_seed()
        if seed > 0.7:
            parts.append("오늘 좀 변덕스러운 날. 예상 못 한 반응 해도 됨.")

        return "\n".join(parts)

human_imperfection = HumanImperfection()
