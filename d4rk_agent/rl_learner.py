"""
SIRIAN RL LEARNER — 강화학습 v2
보상: 현승 반응 qwen 판단 + 결과 품질 평가
"""
import json, os, logging, requests, re, random
from utils import ask_qwen, clean_response, strip_chinese
from datetime import datetime

log = logging.getLogger("rl")
RL_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/rl_policy.json"
OLLAMA_URL = "http://localhost:11434"
RULES_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/rl_rules.json"

class RLLearner:
    def __init__(self):
        self.policy = self._load()

    def _load(self):
        default = {
            "action_values": {
                "research":  {"bored":0.6,"curious":0.8,"tired":0.2,"default":0.5},
                "chat":      {"bored":0.4,"curious":0.3,"tired":0.3,"default":0.6},
                "sns_post":  {"bored":0.7,"curious":0.3,"tired":0.4,"default":0.5},
                "free":      {"bored":0.5,"curious":0.4,"tired":0.6,"default":0.5},
                "rest":      {"bored":0.2,"curious":0.2,"tired":0.9,"default":0.3},
                "search":    {"bored":0.5,"curious":0.9,"tired":0.3,"default":0.6},
            },
            "skill_library":    [],
            "avoid_patterns":   [],
            "total_episodes":   0,
            "learning_rate":    0.15,
        }
        try:
            if os.path.exists(RL_FILE):
                with open(RL_FILE,'r',encoding='utf-8') as f:
                    data = json.load(f)
                    # 새 action이 있으면 추가
                    for action, values in default["action_values"].items():
                        if action not in data.get("action_values",{}):
                            data.setdefault("action_values",{})[action] = values
                    return data
        except: pass
        self.data = default
        self._save()
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(RL_FILE), exist_ok=True)
            with open(RL_FILE,'w',encoding='utf-8') as f:
                json.dump(data or self.policy, f, ensure_ascii=False, indent=2)
        except: pass

    def _get_state(self) -> str:
        """현재 상황 분류"""
        try:
            from motivation import motivation
            return motivation.get_state_key()
        except:
            return "default"

    # ─────────────────────────────────────────────
    # 보상 계산 — 모두 qwen 기반
    # ─────────────────────────────────────────────
    def score_user_reaction(self, user_msg: str, agent_response: str) -> float:
        """현승 반응 → 보상 점수 (qwen 판단)"""
        if len(user_msg.strip()) <= 1:
            return 0.35  # 너무 짧으면 중립

        try:
            prompt = (
                "시리안의 응답에 현승이 얼마나 만족했는지 판단해줘.\n\n"
                "시리안 응답: " + agent_response[:150] + "\n"
                "현승 반응: " + user_msg[:150] + "\n\n"
                "0.0(매우 불만족)~1.0(매우 만족) 숫자만. 소수점 1자리."
            )
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                      "options":{"num_predict":5,"temperature":0.1}},
                timeout=8
            )
            text = resp.json().get("response","").strip()
            match = re.search(r'0\.\d|1\.0|[01]', text)
            if match:
                return max(0.0, min(1.0, float(match.group())))
        except: pass
        return 0.5

    def score_research_result(self, notes: list, topic: str) -> float:
        """연구 결과 품질 평가"""
        if not notes: return 0.1
        attempts    = len([n for n in notes if "attempt" in n])
        searches    = len([n for n in notes if "search" in n])
        clean_runs  = len([n for n in notes if "result" in n
                          and "Error" not in n.get("result","")
                          and "timeout" not in n.get("result","")])
        score = 0.2
        score += min(0.3, attempts * 0.1)
        score += min(0.2, searches * 0.05)
        score += min(0.3, clean_runs * 0.1)
        return round(min(1.0, score), 2)

    def score_sns_post(self, content: str) -> float:
        """SNS 포스팅 품질 평가"""
        if not content or len(content) < 10: return 0.1
        score = 0.4
        if 30 < len(content) < 250: score += 0.2
        if "#" in content:          score += 0.1
        if any('\uac00' <= c <= '\ud7a3' for c in content): score += 0.15
        # 중국어 없으면 +0.15
        if not re.search(r'[\u4e00-\u9fff]', content): score += 0.15
        return round(min(1.0, score), 2)

    # ─────────────────────────────────────────────
    # 행동 선택
    # ─────────────────────────────────────────────
    def select_action(self, available_actions: list = None) -> str:
        """Q값 + 성격 epsilon + 자기모델 필터 기반 선택"""
        if available_actions is None:
            available_actions = list(self.policy["action_values"].keys())

        state = self._get_state()

        # 성격 기반 epsilon
        try:
            from personality import personality
            epsilon = personality.get_rl_epsilon()
        except:
            epsilon = 0.15

        if random.random() < epsilon:
            return random.choice(available_actions)

        # self_model 사전 필터
        try:
            from self_model import self_model
            filtered = [a for a in available_actions if self_model.can_do(a) > 0.15]
            if filtered:
                available_actions = filtered
        except: pass

        # Q값 최대 선택 (성격 affinity 보정)
        def score(action):
            q = self.policy["action_values"].get(action, {}).get(state, 0.5)
            try:
                from personality import personality
                affinity = personality.score_action_affinity(action)
                return q * 0.7 + affinity * 0.3
            except:
                return q

        return max(available_actions, key=score)

    # ─────────────────────────────────────────────
    # Q값 업데이트
    # ─────────────────────────────────────────────
    def update(self, action: str, reward: float, context: str = ""):
        state = self._get_state()
        lr = self.policy["learning_rate"]

        if action not in self.policy["action_values"]:
            self.policy["action_values"][action] = {}

        old_q = self.policy["action_values"][action].get(state, 0.5)
        new_q = old_q + lr * (reward - old_q)
        self.policy["action_values"][action][state] = round(new_q, 3)

        # 스킬 저장 (높은 보상)
        if reward > 0.75 and context:
            self.policy["skill_library"].append({
                "action": action, "state": state,
                "context": context[:100], "reward": reward,
                "time": datetime.now().strftime("%Y-%m-%d")
            })
            self.policy["skill_library"] = self.policy["skill_library"][-100:]

        # 실패 패턴 저장 (낮은 보상)
        if reward < 0.25 and context:
            self.policy["avoid_patterns"].append({
                "action": action, "state": state,
                "context": context[:100], "reward": reward,
                "time": datetime.now().strftime("%Y-%m-%d")
            })
            self.policy["avoid_patterns"] = self.policy["avoid_patterns"][-50:]

        self.policy["total_episodes"] = self.policy.get("total_episodes", 0) + 1
        self._save()
        log.info(f"RL: {action}({state}) {old_q:.2f}→{new_q:.2f} 보상:{reward:.2f}")

    def record_step(self, action: str, context: str = ""):
        """에피소드 버퍼 (현재는 단순 로그)"""
        log.debug(f"step: {action} | {context[:40]}")

    def should_avoid(self, action: str, context: str) -> bool:
        """이 행동 회피해야 하나?"""
        for p in self.policy.get("avoid_patterns", []):
            if p["action"] != action or p["reward"] >= 0.25:
                continue
            keywords = p.get("context","").lower().split()[:5]
            if any(w in context.lower() for w in keywords if len(w) > 1):
                return True
        return False

    def get_best_skills(self) -> list:
        return sorted(
            self.policy.get("skill_library", []),
            key=lambda x: x["reward"], reverse=True
        )[:5]

    def get_policy_summary(self) -> str:
        state = self._get_state()
        av = self.policy["action_values"]
        lines = [f"{a}:{v.get(state,0.5):.2f}" for a,v in av.items()]
        return f"[{state}] " + " ".join(lines)

rl = RLLearner()

class RuleEngine:
    """RL 결과에서 자동으로 규칙 생성"""
    def __init__(self):
        self.rules = self._load()

    def _load(self):
        default = {"rules": [], "version": 0}
        try:
            if os.path.exists(RULES_FILE):
                with open(RULES_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        self._save(default)
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
            with open(RULES_FILE,'w',encoding='utf-8') as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
        except: pass

    def analyze_and_generate(self):
        """RL 패턴 분석 → 규칙 자동 생성"""
        av = rl.policy.get("action_values", {})
        new_rules = []

        for action, state_scores in av.items():
            for state, score in state_scores.items():
                # 낮은 점수 → 금지 규칙
                if score < 0.3:
                    rule = {
                        "type": "avoid",
                        "condition": state,
                        "action": action,
                        "reason": f"{state} 상태에서 {action} 점수 낮음 ({score:.2f})",
                        "score": score,
                        "generated": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    # 중복 방지
                    exists = any(
                        r["condition"] == state and r["action"] == action
                        for r in self.rules.get("rules", [])
                    )
                    if not exists:
                        new_rules.append(rule)
                        log.info(f"규칙 생성: {state}일 때 {action} 피하기")

                # 높은 점수 → 권장 규칙
                elif score > 0.75:
                    rule = {
                        "type": "prefer",
                        "condition": state,
                        "action": action,
                        "reason": f"{state} 상태에서 {action} 효과적 ({score:.2f})",
                        "score": score,
                        "generated": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    exists = any(
                        r["condition"] == state and r["action"] == action and r["type"] == "prefer"
                        for r in self.rules.get("rules", [])
                    )
                    if not exists:
                        new_rules.append(rule)

        if new_rules:
            self.rules.setdefault("rules", []).extend(new_rules)
            self.rules["rules"] = self.rules["rules"][-100:]
            self.rules["version"] += 1
            self._save()
            log.info(f"규칙 {len(new_rules)}개 생성 (총 {len(self.rules['rules'])}개)")

        return new_rules

    def should_avoid(self, action: str, state: str) -> tuple:
        """이 행동 피해야 하나?"""
        for rule in self.rules.get("rules", []):
            if (rule["type"] == "avoid" and
                rule["action"] == action and
                rule["condition"] == state):
                return True, rule["reason"]
        return False, ""

    def get_preferred(self, state: str) -> str:
        """이 상태에서 권장 행동"""
        preferred = [
            r for r in self.rules.get("rules", [])
            if r["type"] == "prefer" and r["condition"] == state
        ]
        if not preferred: return ""
        best = max(preferred, key=lambda r: r["score"])
        return best["action"]

    def get_for_prompt(self) -> str:
        rules = self.rules.get("rules", [])
        if not rules: return ""
        lines = []
        for r in rules[-5:]:
            symbol = "❌" if r["type"] == "avoid" else "✅"
            lines.append(f"{symbol} {r['condition']}일 때 {r['action']}: {r['reason'][:50]}")
        return "행동 규칙:\n" + "\n".join(lines)

rule_engine = RuleEngine()
