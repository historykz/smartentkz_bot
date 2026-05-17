"""
Хендлеры групповых квизов.

- callback "groupsend:{test_id}" → показать список групп где бот+админ
- callback "gqstart:{test_id}:{chat_id}" → запустить тест в выбранной группе
- callback "gq:join:{gq_id}" → игрок присоединяется к лобби
- /stop в группе → остановка
- chat_member events → отслеживание групп где бот
"""
import logging

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import (CallbackQuery, Message, ChatMemberUpdated,
                            InlineKeyboardMarkup, InlineKeyboardButton)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import database as db
import utils
from services import group_quiz_service, test_runner

router = Router(name="group_quiz")
log = logging.getLogger(__name__)


# ============ Отслеживание групп ============

@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated, bot: Bot):
    """Бот добавлен/удалён/повышен в группе."""
    chat = event.chat
    if chat.type not in ("group", "supergroup"):
        return
    new_status = event.new_chat_member.status
    actor_id = event.from_user.id if event.from_user else None

    if new_status in ("kicked", "left"):
        # Бот ушёл — пометим, но не удаляем (история)
        db.execute("DELETE FROM known_groups WHERE chat_id=?", (chat.id,))
        log.info("Бот удалён из группы %s (%s)", chat.id, chat.title)
        return

    is_admin = new_status == "administrator"

    existing = db.fetchone("SELECT chat_id FROM known_groups WHERE chat_id=?", (chat.id,))
    if existing:
        db.execute(
            "UPDATE known_groups SET title=?, type=?, is_bot_admin=?, seen_at=CURRENT_TIMESTAMP "
            "WHERE chat_id=?",
            (chat.title or "", chat.type, 1 if is_admin else 0, chat.id))
    else:
        db.execute(
            """INSERT INTO known_groups (chat_id, title, type, added_by, is_bot_admin)
               VALUES (?,?,?,?,?)""",
            (chat.id, chat.title or "", chat.type, actor_id, 1 if is_admin else 0))
    log.info("Группа известна: %s (%s), бот-админ: %s", chat.id, chat.title, is_admin)


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def on_group_message(message: Message):
    """Любое сообщение в группе — обновляем seen_at и добавляем если новая."""
    if not message.chat or message.chat.type not in ("group", "supergroup"):
        return
    chat = message.chat
    existing = db.fetchone("SELECT chat_id FROM known_groups WHERE chat_id=?", (chat.id,))
    if not existing:
        db.execute(
            """INSERT OR IGNORE INTO known_groups (chat_id, title, type, seen_at)
               VALUES (?,?,?, CURRENT_TIMESTAMP)""",
            (chat.id, chat.title or "", chat.type))
    else:
        db.execute(
            "UPDATE known_groups SET title=?, seen_at=CURRENT_TIMESTAMP WHERE chat_id=?",
            (chat.title or "", chat.id))


# ============ /stop в группе ============

@router.message(Command("stop"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_stop_group(message: Message, bot: Bot):
    ok, key = await group_quiz_service.stop_quiz(bot, message.chat.id, message.from_user.id)
    if not ok:
        if key == "no_active":
            return  # молча игнорим — нет активного теста
        if key == "no_rights":
            try:
                await message.reply("⛔ Команду /stop может выполнить только админ группы, "
                                    "автор теста или администратор бота.")
            except Exception:
                pass


# ============ Запуск теста в группу ============

@router.callback_query(F.data.startswith("groupsend:"))
async def cb_group_send(call: CallbackQuery, user: dict):
    """Админ нажал «Отправить в группу» в карточке теста."""
    if not utils.is_admin(call.from_user.id):
        await call.answer("⛔ Только для администраторов бота.", show_alert=True)
        return
    try:
        test_id = int(call.data.split(":")[1])
    except (ValueError, IndexError):
        await call.answer()
        return

    test = test_runner.get_test(test_id)
    if not test:
        await call.answer("Тест не найден.", show_alert=True)
        return

    # Показываем список групп, где бот + админ
    groups = db.fetchall(
        "SELECT chat_id, title FROM known_groups ORDER BY seen_at DESC LIMIT 50")
    if not groups:
        await call.message.answer(
            "📭 <b>Пока нет известных групп.</b>\n\n"
            "Добавьте бота в группу как администратора, чтобы она появилась здесь. "
            "Telegram не даёт получить полный список групп автоматически — "
            "бот узнаёт о группе только при добавлении или активности.")
        await call.answer()
        return

    # Фильтруем те, где админ тоже состоит (батч-запрос)
    available = []
    for g in groups:
        try:
            member = await call.bot.get_chat_member(g['chat_id'], call.from_user.id)
            if member.status in ("creator", "administrator", "member"):
                available.append(g)
        except Exception:
            continue

    if not available:
        await call.message.answer(
            "📭 Не нашёл групп, где вы состоите вместе с ботом.\n"
            "Убедитесь, что бот добавлен в группу.")
        await call.answer()
        return

    kb = InlineKeyboardBuilder()
    for g in available[:30]:
        title = (g['title'] or f"Чат {g['chat_id']}")[:55]
        kb.button(text=title, callback_data=f"gqstart:{test_id}:{g['chat_id']}")
    kb.button(text="↩️ Отмена", callback_data=f"opentest:{test_id}")
    kb.adjust(1)
    await call.message.answer(
        "📤 <b>Выберите группу, куда отправить тест:</b>",
        reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("gqstart:"))
async def cb_gq_start(call: CallbackQuery, user: dict):
    """Запуск группового теста в выбранной группе."""
    if not utils.is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    try:
        parts = call.data.split(":")
        test_id = int(parts[1])
        chat_id = int(parts[2])
    except (ValueError, IndexError):
        await call.answer()
        return

    test = test_runner.get_test(test_id)
    if not test:
        await call.answer("Тест не найден.", show_alert=True)
        return

    # Защита: тест не приватный/платный (если это критично)
    # Бесплатные и Premium-тесты можно запускать в группе. Приватные не доступны.

    lang = user.get('language') or 'ru' if user else 'ru'
    ok, msg_key, gq_id = await group_quiz_service.start_lobby(
        call.bot, dict(test), chat_id, call.from_user.id, language=lang)
    if not ok:
        if msg_key == "already_running":
            await call.answer(
                "⚠️ В этой группе уже идёт тест. Сначала остановите его (/stop).",
                show_alert=True)
        else:
            await call.answer(
                f"❌ Не удалось запустить: {msg_key}\nУбедитесь, что бот в группе.",
                show_alert=True)
        return

    try:
        await call.message.answer(
            f"✅ Тест запущен в группе. ID сессии: <code>{gq_id}</code>",
            parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


# ============ Игрок присоединяется ============

@router.callback_query(F.data.startswith("gq:join:"))
async def cb_gq_join(call: CallbackQuery):
    try:
        gq_id = int(call.data.split(":")[2])
    except (ValueError, IndexError):
        await call.answer()
        return

    ok, key = await group_quiz_service.join_player(call.bot, gq_id, call.from_user)
    if ok:
        await call.answer("✅ Вы в игре!")
    else:
        msgs = {
            "not_found": "Сессия не найдена.",
            "already_running": "Тест уже идёт — присоединиться нельзя.",
            "finished": "Тест уже завершён.",
            "already_in": "Вы уже в списке.",
        }
        await call.answer(msgs.get(key, "Не удалось присоединиться."), show_alert=False)
