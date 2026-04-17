"""
D4RK AGENT — Telegram Bot
폰에서 시리안이랑 대화 가능
실행: py -3.11 telegram_bot.py
"""
import asyncio, logging, os
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("telegram")

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
except ImportError:
    import subprocess, sys
    print("[*] python-telegram-bot 설치 중...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-telegram-bot==20.7", "-q"])
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED = os.getenv("TELEGRAM_ALLOWED_ID", "")  # 현승 텔레그램 ID (보안용)

# ── 에이전트 연결 ──
def get_agent():
    try:
        from agent import agent
        return agent
    except Exception as e:
        log.error(f"에이전트 연결 실패: {e}")
        return None

agent = get_agent()

# ── 권한 체크 ──
def is_allowed(update: Update) -> bool:
    if not ALLOWED:
        return True  # 설정 안 했으면 전체 허용
    return str(update.effective_user.id) == ALLOWED

# ── 핸들러 ──
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("권한 없음.")
        return
    await update.message.reply_text(
        "시리안이야. 뭐야.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("권한 없음.")
        return

    user_text = update.message.text
    if not user_text:
        return

    # 타이핑 표시
    await ctx.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # 에이전트한테 전달
    if agent:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: agent.chat(user_text, "")
            )
            # 코드 블록 처리
            await update.message.reply_text(
                response[:4000],  # 텔레그램 최대 4096자
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"오류: {e}")
    else:
        await update.message.reply_text("에이전트 연결 안 됨. main.py 먼저 실행해.")

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    if agent:
        import requests
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=3)
            ollama_ok = r.status_code == 200
        except:
            ollama_ok = False
        await update.message.reply_text(
            f"Ollama: {'✓' if ollama_ok else '✗'}\n"
            f"모델: {agent.model}\n"
            f"메모리: {len(agent.chat_history)//2}턴 대화"
        )
    else:
        await update.message.reply_text("에이전트 미연결")

async def clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    if agent:
        agent.chat_history = []
        await update.message.reply_text("대화 초기화했어.")

async def capture(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """현재 화면 캡처해서 전송"""
    if not is_allowed(update):
        return
    try:
        from observer import observer
        if observer.last_screenshot_b64:
            import base64
            img_data = base64.b64decode(observer.last_screenshot_b64)
            await ctx.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=img_data,
                caption=f"현재 화면\n활동: {observer.last_activity}\n{observer.last_analysis[:100]}"
            )
        else:
            await update.message.reply_text("화면 캡처 없음. observer 실행 중인지 확인해.")
    except Exception as e:
        await update.message.reply_text(f"캡처 실패: {e}")

# ── 메인 ──
def main():
    if not TOKEN:
        print("[!] TELEGRAM_BOT_TOKEN이 .env에 없어.")
        print("[!] .env 파일에 TELEGRAM_BOT_TOKEN=토큰값 추가해.")
        return

    print(f"[*] 시리안 텔레그램 봇 시작...")
    print(f"[*] t.me/sirian_rain_bot")
    print(f"[*] 종료: Ctrl+C\n")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("capture", capture))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
