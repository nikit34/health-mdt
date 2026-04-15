"""Telegram bot — runs as a separate container from the API.

Commands:
  /start        — pair the chat with the web account via PIN
  /brief        — get today's brief
  /checkin text — store a free-form check-in
  /ask ...      — ask the GP a question
  /report       — get the latest weekly MDT summary
  /tasks        — list open tasks (with Apple Reminders links)
  /done <id>    — close a task

Quiet operation: posts the morning brief automatically at 07:00 local time.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..agents.context import build_context
from ..agents.orchestrator import generate_daily_brief
from ..agents.registry import GP_AGENT
from ..config import get_settings
from ..db import Brief, Checkin, MdtReport, Task, User
from ..db.session import engine, init_db

log = logging.getLogger(__name__)


# --- Helpers ---

def _require_user(chat_id: int) -> User | None:
    """Only respond to the paired chat."""
    with Session(engine) as s:
        user = s.exec(select(User)).first()
        if not user:
            return None
        if user.telegram_chat_id != chat_id:
            return None
        return user


def _pair_chat(chat_id: int) -> bool:
    """Pair the bot with the user account if not yet paired."""
    with Session(engine) as s:
        user = s.exec(select(User)).first()
        if not user:
            user = User(telegram_chat_id=chat_id)
            s.add(user)
            s.commit()
            return True
        if user.telegram_chat_id and user.telegram_chat_id != chat_id:
            return False
        user.telegram_chat_id = chat_id
        s.add(user)
        s.commit()
        return True


# --- Handlers ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    args = context.args
    settings = get_settings()

    # If PIN configured, require it
    if settings.access_pin:
        if not args or args[0].strip() != settings.access_pin.strip():
            await update.message.reply_text(
                "Добро пожаловать в health-mdt.\n\n"
                "Чтобы связать этот чат с твоим аккаунтом, отправь:\n"
                "`/start <PIN>`\n\n"
                "PIN ты получил при деплое инстанса.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    if _pair_chat(chat_id):
        await update.message.reply_text(
            "✓ Чат привязан.\n\n"
            "Что я умею:\n"
            "/brief — утренний бриф\n"
            "/checkin как дела сегодня — зафиксировать чек-ин\n"
            "/ask ... — спросить GP-агента\n"
            "/report — последний недельный MDT-отчёт\n"
            "/tasks — открытые задачи\n"
            "/done <id> — закрыть задачу\n\n"
            "Каждое утро в 07:00 я буду присылать бриф автоматически."
        )
    else:
        await update.message.reply_text(
            "Аккаунт уже привязан к другому чату. "
            "Отвяжи его в веб-интерфейсе и попробуй ещё раз."
        )


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _require_user(update.effective_chat.id)
    if not user:
        await update.message.reply_text("Сначала привяжи чат: /start <PIN>")
        return
    settings = get_settings()
    if not settings.has_llm:
        await update.message.reply_text("LLM не настроен — нужен ANTHROPIC_API_KEY в .env.")
        return
    await update.message.reply_text("Готовлю бриф…")
    with Session(engine) as s:
        fresh_user = s.get(User, user.id)
        brief = generate_daily_brief(s, fresh_user)
    text = _format_brief(brief)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _require_user(update.effective_chat.id)
    if not user:
        await update.message.reply_text("Сначала привяжи чат: /start <PIN>")
        return
    text = " ".join(context.args).strip()
    if not text:
        # If user sent /checkin alone, wait for next message via user_data
        context.user_data["awaiting_checkin"] = True
        await update.message.reply_text("Напиши одним сообщением как ты. Всё в одну строку.")
        return
    with Session(engine) as s:
        c = Checkin(user_id=user.id, text=text)
        s.add(c)
        s.commit()
    await update.message.reply_text("✓ Записано. Учту при следующем брифе.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _require_user(update.effective_chat.id)
    if not user:
        return
    # If awaiting_checkin, treat as check-in
    if context.user_data.pop("awaiting_checkin", False):
        with Session(engine) as s:
            s.add(Checkin(user_id=user.id, text=update.message.text or ""))
            s.commit()
        await update.message.reply_text("✓ Записано.")
        return
    # Else: default behavior — short GP-style answer to free text
    settings = get_settings()
    if not settings.has_llm:
        return
    await _answer_question(update, user, update.message.text or "")


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _require_user(update.effective_chat.id)
    if not user:
        return
    question = " ".join(context.args).strip()
    if not question:
        await update.message.reply_text("Использование: /ask твой вопрос")
        return
    await _answer_question(update, user, question)


async def _answer_question(update: Update, user: User, question: str) -> None:
    await update.message.chat.send_action("typing")
    with Session(engine) as s:
        ctx = build_context(s, user, window_days=14)
        payload = {
            **ctx.to_dict(),
            "instruction": (
                f"Пациент задал вопрос: «{question}». Ответь коротко, как семейный врач, "
                "2-4 абзаца, на основе имеющихся данных. Верни JSON: "
                "{\"answer\": \"...\", \"confidence\": 0.0-1.0, \"needs_human_review\": bool}"
            ),
        }
        resp = GP_AGENT.run(payload)
    answer = resp.narrative or resp.soap.get("assessment", "Не удалось получить ответ.")
    if resp.safety_flags:
        answer += "\n\n⚠️ Флаги: " + ", ".join(resp.safety_flags)
    await update.message.reply_text(answer)


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _require_user(update.effective_chat.id)
    if not user:
        return
    with Session(engine) as s:
        r = s.exec(
            select(MdtReport).where(MdtReport.user_id == user.id).order_by(MdtReport.created_at.desc())
        ).first()
    if not r:
        await update.message.reply_text("Отчётов ещё нет. MDT собирается по воскресеньям. Запусти вручную в вебе.")
        return
    text = _format_mdt(r)
    await update.message.reply_text(text[:4000], parse_mode=ParseMode.MARKDOWN)


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _require_user(update.effective_chat.id)
    if not user:
        return
    with Session(engine) as s:
        rows = s.exec(
            select(Task).where(Task.user_id == user.id, Task.status == "open").order_by(Task.priority, Task.created_at)
        ).all()
    if not rows:
        await update.message.reply_text("Открытых задач нет.")
        return
    lines = ["*Открытые задачи:*"]
    for t in rows[:15]:
        age = (datetime.utcnow() - t.created_at).days
        tag = {"urgent": "🔴", "normal": "🟡", "low": "⚪"}.get(t.priority, "🟡")
        lines.append(f"{tag} *#{t.id}* {t.title}  _(от {t.created_by}, {age}д)_")
        if t.detail:
            lines.append(f"    {t.detail[:120]}")
    lines.append("\n_Закрыть:_ `/done <id>`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _require_user(update.effective_chat.id)
    if not user:
        return
    if not context.args:
        await update.message.reply_text("Использование: /done <id>")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ожидал число.")
        return
    with Session(engine) as s:
        t = s.get(Task, tid)
        if not t or t.user_id != user.id:
            await update.message.reply_text("Задача не найдена.")
            return
        t.status = "done"
        t.closed_at = datetime.utcnow()
        s.add(t)
        s.commit()
    await update.message.reply_text(f"✓ Задача #{tid} закрыта.")


# --- Formatters ---

def _format_brief(b: Brief) -> str:
    lines = [f"*Бриф на {b.for_date.isoformat()}*", "", b.text]
    if b.highlights:
        lines.append("")
        lines.append("_Фокусы дня:_")
        for h in b.highlights:
            lines.append(f"• {h}")
    return "\n".join(lines)


def _format_mdt(r: MdtReport) -> str:
    lines = [f"*MDT-отчёт* ({r.kind}, {r.created_at.date().isoformat()})", "", r.gp_synthesis]
    if r.problem_list:
        lines.append("\n*Список проблем:*")
        for p in r.problem_list[:6]:
            status = p.get("status", "")
            lines.append(f"• {p.get('problem', '')} — _{status}_")
    if r.safety_net:
        lines.append("\n*Safety net:*")
        for tr in r.safety_net[:5]:
            lines.append(f"⚠️ {tr}")
    return "\n".join(lines)


# --- Main ---

async def post_init(app: Application) -> None:
    # Schedule morning brief — uses app's job queue
    async def morning_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        with Session(engine) as s:
            user = s.exec(select(User)).first()
            if not user or not user.telegram_chat_id:
                return
            if not get_settings().has_llm:
                return
            fresh_user = s.get(User, user.id)
            brief = generate_daily_brief(s, fresh_user)
        text = _format_brief(brief)
        await app.bot.send_message(chat_id=user.telegram_chat_id, text=text, parse_mode=ParseMode.MARKDOWN)

    from datetime import time
    app.job_queue.run_daily(morning_job, time=time(hour=7, minute=0), name="morning_brief")


def build_app() -> Application | None:
    settings = get_settings()
    if not settings.has_telegram:
        log.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return None
    init_db()
    app = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = build_app()
    if not app:
        log.info("Bot disabled — idling")
        import time
        while True:
            time.sleep(3600)
    app.run_polling()


if __name__ == "__main__":
    main()
