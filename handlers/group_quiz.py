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

@router.callback_query(F.data.startswith("gqlaunch:"))
async def cb_gq_launch(call: CallbackQuery):
    """
    Запуск группового теста из inline-карточки.
    Сработает только если callback нажал тот же админ, кто её отправил.
    """
    try:
        parts = call.data.split(":")
        test_id = int(parts[1])
        intended_admin_id = int(parts[2])
    except (ValueError, IndexError):
        await call.answer()
        return

    # Только админ бота
    if not utils.is_admin(call.from_user.id):
        await call.answer(
            "⛔ Только администратор бота может запустить тест.",
            show_alert=True)
        return

    # Проверка: тот ли админ, кто отправлял карточку
    if call.from_user.id != intended_admin_id:
        await call.answer(
            "⛔ Эту карточку отправил другой администратор. Отправьте свою.",
            show_alert=True)
        return

    chat = call.message.chat if call.message else None
    if not chat or chat.type not in ("group", "supergroup"):
        await call.answer(
            "⚠️ Эту кнопку нужно нажимать в группе, а не в личке.",
            show_alert=True)
        return

    test = test_runner.get_test(test_id)
    if not test:
        await call.answer("Тест не найден.", show_alert=True)
        return

    # Записываем группу в known_groups для будущей статистики
    db.execute(
        """INSERT OR IGNORE INTO known_groups (chat_id, title, type, added_by, seen_at)
           VALUES (?,?,?,?, CURRENT_TIMESTAMP)""",
        (chat.id, chat.title or "", chat.type, call.from_user.id))

    ok, key, gq_id = await group_quiz_service.start_lobby(
        call.bot, dict(test), chat.id, call.from_user.id, language='ru')

    if not ok:
        if key == "already_running":
            await call.answer(
                "⚠️ В этой группе уже идёт тест. Сначала /stop.",
                show_alert=True)
        else:
            await call.answer(f"❌ Не удалось: {key}", show_alert=True)
        return

    # Удаляем inline-карточку (она больше не нужна — лобби-карточка уже отправлена)
    try:
        await call.message.delete()
    except Exception:
        pass

    await call.answer("✅ Тест запущен!")


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
