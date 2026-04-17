"""
SIRIAN LORA PIPELINE — 자동 파인튜닝 준비
데이터 품질 검사 + 200개 달성 시 알림 + 학습 스크립트 자동 생성
실제 학습은 현승이 수동 실행 (GPU 과부하 방지)
"""
import json, os, logging, re
from datetime import datetime
from utils import ask_qwen, strip_chinese

log = logging.getLogger("lora")
TRAIN_FILE  = "C:/Users/gohun/Desktop/sirian/d4rk_agent/sirian_train.jsonl"
REPORT_FILE = "C:/Users/gohun/Desktop/sirian/sirian_space/lora_report.json"
SCRIPT_FILE = "C:/Users/gohun/Desktop/sirian/d4rk_agent/run_finetune.sh"

class LoraPipeline:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        default = {
            "total":       0,
            "quality":     0.0,
            "last_check":  "",
            "notified_200": False,
            "filtered":    0,
        }
        try:
            if os.path.exists(REPORT_FILE):
                with open(REPORT_FILE,'r',encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        return default

    def _save(self):
        try:
            os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
            with open(REPORT_FILE,'w',encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except: pass

    def check_and_filter(self) -> dict:
        """데이터 품질 검사 + 저품질 제거"""
        if not os.path.exists(TRAIN_FILE):
            return {"total": 0, "quality": 0.0}

        with open(TRAIN_FILE,'r',encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

        good, bad = [], []
        for line in lines:
            try:
                sample = json.loads(line)
                msgs   = sample.get("messages", [])
                resp   = next((m["content"] for m in msgs
                              if m["role"]=="assistant"), "")

                # 품질 기준
                if (len(resp) < 5 or                    # 너무 짧음
                    len(resp) > 500 or                   # 너무 김
                    "습니다" in resp or "드릴게요" in resp or  # 존댓말
                    bool(re.search(r'[\u4e00-\u9fff]', resp))):  # 중국어
                    bad.append(line)
                else:
                    good.append(line)
            except:
                bad.append(line)

        # 저품질 제거 후 저장
        if bad:
            with open(TRAIN_FILE,'w',encoding='utf-8') as f:
                f.write("\n".join(good) + "\n")
            log.info(f"저품질 {len(bad)}개 제거, {len(good)}개 유지")

        quality = len(good) / max(len(lines), 1)
        self.data.update({
            "total":      len(good),
            "quality":    round(quality, 2),
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "filtered":   len(bad),
        })
        self._save()

        # 200개 달성 알림
        if len(good) >= 200 and not self.data.get("notified_200"):
            self.data["notified_200"] = True
            self._save()
            self._notify_ready(len(good))
            self._generate_script(len(good))

        return {"total": len(good), "quality": quality, "filtered": len(bad)}

    def _notify_ready(self, count: int):
        msg = f"파인튜닝 데이터 {count}개 준비됐어. run_finetune.sh 실행하면 학습 시작돼."
        log.info(msg)
        try:
            from tts_engine import tts
            tts.speak(msg, priority=True)
        except: pass
        try:
            from memory import memory
            memory.add_agent_thought(f"[파인튜닝] {msg}", "lora")
        except: pass

    def _generate_script(self, count: int):
        """Unsloth LoRA 학습 스크립트 자동 생성"""
        script = f"""#!/bin/bash
# 시리안 레인 파인튜닝 스크립트
# 데이터: {count}개 | 생성: {datetime.now().strftime("%Y-%m-%d %H:%M")}
# 실행: bash run_finetune.sh

pip install unsloth -q

python3 - << 'EOF'
from unsloth import FastLanguageModel
import torch

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/Qwen2.5-14B-Instruct-bnb-4bit",
    max_seq_length = 2048,
    load_in_4bit = True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16, target_modules=["q_proj","k_proj","v_proj","o_proj"],
    lora_alpha=16, lora_dropout=0,
    bias="none", use_gradient_checkpointing="unsloth",
)

from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset

dataset = load_dataset("json", data_files="{TRAIN_FILE}", split="train")

trainer = SFTTrainer(
    model=model, tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="messages",
    max_seq_length=2048,
    args=TrainingArguments(
        output_dir="./sirian_lora",
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        save_steps=50,
    ),
)
trainer.train()
model.save_pretrained("./sirian_lora_final")
print("파인튜닝 완료! sirian_lora_final 폴더 확인해.")
EOF
"""
        try:
            with open(SCRIPT_FILE,'w',encoding='utf-8') as f:
                f.write(script)
            log.info(f"파인튜닝 스크립트 생성: {SCRIPT_FILE}")
        except Exception as e:
            log.error(f"스크립트 생성 실패: {e}")

    def get_status(self) -> dict:
        self.check_and_filter()
        return self.data

lora_pipeline = LoraPipeline()
