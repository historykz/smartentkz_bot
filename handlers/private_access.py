"""
Закрытый (приватный) доступ к тестам.

- /opens          — главное меню (только админ)
- Приватные тесты не видны в каталоге, поиске, дуэлях
- Видны и проходимы только тем, кому админ выдал доступ
"""
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, Message,
                            InlineKeyboardMarkup, InlineKeyboardButton)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import database as db
import utils
from filters import IsAdmin

router = Router(name="private_access")
log = logging.getLogger(__name__)


class PrivateAccessStates(StatesGroup):
    waiting_user_for_grant = State()
    waiting_test_for_grant = State()
    waiting_user_for_revoke = State()


# ============ Public helpers (используются в других модулях) ============

def is_test_private(test: dict) -> bool:
    """Тест приватный?"""
    if not test:
        return False
    return bool(test.get('is_private'))


def user_has_private_access(test_id: int, user_tg_id: int) -> bool:
    """Есть ли у пользователя доступ к приватному тесту?"""
    if not user_tg_id:
        return False
    # Админы всегда могут
    if utils.is_admin(user_tg_id):
        return True
    row = db.fetchone(
        "SELECT 1 FROM private_test_access WHERE test_id=? AND user_tg_id=?",
        (test_id, user_tg_id))
    return bool(row)


def list_user_private_tests(user_tg_id: int) -> list[dict]:
    """Список приватных тестов, доступных конкретному пользователю."""
    if utils.is_admin(user_tg_id):
        rows = db.fetchall(
            "SELECT * FROM tests WHERE is_private=1 AND status='active' ORDER BY id DESC")
    else:
        rows = db.fetchall(
            """SELECT t.* FROM tests t
               JOIN private_test_access p ON p.test_id = t.id
               WHERE t.is_private=1 AND t.status='active' AND p.user_tg_id=?
               ORDER BY t.id DESC""",
            (user_tg_id,))
    return [dict(r) for r in rows]


# ============ /opens ============

@router.message(Command("opens"), IsAdmin())
async def cmd_opens(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🎟 Выдать доступ", callback_data="opens:grant")
    kb.button(text="📋 Список с доступом", callback_data="opens:list")
    kb.button(text="🗑 Отозвать доступ", callback_data="opens:revoke")
    kb.button(text="🔐 Приватные тесты", callback_data="opens:tests")
    kb.button(text="↩️ Закрыть", callback_data="opens:close")
    kb.adjust(1)

    text = (
        "🔐 <b>Закрытый доступ</b>\n\n"
        "Управление приватными тестами. Эти тесты <b>не видны</b> "
        "обычным пользователям, Premium-юзерам, и не используются в дуэлях.\n\n"
        "Доступ выдаётся <b>лично</b> по @username или tg_id.\n\n"
        "Чтобы сделать тест приватным — создайте новый тест и в админ-панели "
        "пометьте его как приватный, либо используйте раздел «🔐 Приватные тесты»."
    )
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.message(Command("opens"))
async def cmd_opens_denied(message: Message):
    await message.answer("⛔ Команда доступна только администраторам.")


@router.callback_query(F.data == "opens:close", IsAdmin())
async def cb_opens_close(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


# ============ Список приватных тестов ============

@router.callback_query(F.data == "opens:tests", IsAdmin())
async def cb_opens_tests(call: CallbackQuery, state: FSMContext):
    await state.clear()
    tests = db.fetchall(
        "SELECT id, title, subject FROM tests WHERE is_private=1 ORDER BY id DESC LIMIT 30")

    if not tests:
        text = ("🔐 <b>Приватные тесты</b>\n\n"
                "<i>Пока нет приватных тестов.</i>\n\n"
                "Чтобы сделать тест приватным — откройте его в админке "
                "(<code>/admin</code> → 📚 Мои тесты → выбрать → 🔐 Сделать приватным).")
    else:
        lines = ["🔐 <b>Приватные тесты:</b>\n"]
        for t in tests:
            users_count = db.fetchone(
                "SELECT COUNT(*) AS c FROM private_test_access WHERE test_id=?",
                (t['id'],))['c']
            title = (t['title'] or '—')[:40]
            lines.append(f"• #{t['id']} — {utils.escape_html(title)} "
                          f"<i>({users_count} с доступом)</i>")
        text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Назад", callback_data="opens:back")
    kb.adjust(1)
    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup(),
                                       parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb.as_markup(),
                                    parse_mode="HTML")
    await call.answer()


# ============ Выдача доступа ============

@router.callback_query(F.data == "opens:grant", IsAdmin())
async def cb_opens_grant(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(PrivateAccessStates.waiting_user_for_grant)
    await call.message.answer(
        "👤 Введите <b>@username</b> или <b>tg_id</b> пользователя, "
        "которому хотите выдать доступ:",
        parse_mode="HTML")
    await call.answer()


@router.message(PrivateAccessStates.waiting_user_for_grant, IsAdmin())
async def s_opens_grant_user(message: Message, state: FSMContext):
    arg = (message.text or "").strip()
    # Пробуем найти юзера
    target_tg_id = None
    target_name = None
    if arg.isdigit():
        target_tg_id = int(arg)
        u = db.fetchone("SELECT tg_id, username, first_name FROM users WHERE tg_id=?", (target_tg_id,))
        if u:
            target_name = ("@" + u['username']) if u['username'] else (u['first_name'] or f"id{target_tg_id}")
    else:
        target = utils.find_user_by_arg(arg)
        if target:
            target_tg_id = target['tg_id']
            target_name = ("@" + target['username']) if target.get('username') else (
                target.get('first_name') or f"id{target_tg_id}")

    if target_tg_id is None:
        await message.answer(
            "❌ Не нашёл пользователя. Введите tg_id числом или @username "
            "(пользователь должен был писать боту /start).")
        return

    await state.update_data(grant_target_tg=target_tg_id, grant_target_name=target_name or str(target_tg_id))

    # Показываем список приватных тестов на выбор
    tests = db.fetchall(
        "SELECT id, title FROM tests WHERE is_private=1 AND status='active' ORDER BY id DESC LIMIT 30")

    if not tests:
        await message.answer(
            "⚠️ Нет ни одного приватного теста.\n"
            "Сначала создайте/пометьте тест как приватный, потом выдавайте доступ.")
        await state.clear()
        return

    kb = InlineKeyboardBuilder()
    for t in tests:
        title = (t['title'] or '—')[:50]
        kb.button(text=f"🔐 {title}", callback_data=f"opensgrant:{t['id']}")
    kb.button(text="⚡️ Дать ВСЕ приватные сразу", callback_data="opensgrant:all")
    kb.button(text="❌ Отмена", callback_data="opens:back")
    kb.adjust(1)

    await state.set_state(PrivateAccessStates.waiting_test_for_grant)
    await message.answer(
        f"👤 Пользователь: <b>{utils.escape_html(target_name or str(target_tg_id))}</b>\n"
        f"tg_id: <code>{target_tg_id}</code>\n\n"
        f"Выберите тест для выдачи доступа:",
        reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("opensgrant:"), IsAdmin())
async def cb_opens_grant_test(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_tg_id = data.get('grant_target_tg')
    target_name = data.get('grant_target_name', str(target_tg_id))

    if not target_tg_id:
        await call.answer("❌ Сессия истекла, начните заново.", show_alert=True)
        await state.clear()
        return

    arg = call.data.split(":", 1)[1]

    if arg == "all":
        tests = db.fetchall(
            "SELECT id, title FROM tests WHERE is_private=1 AND status='active'")
        granted = 0
        for t in tests:
            try:
                db.execute(
                    """INSERT OR IGNORE INTO private_test_access
                       (test_id, user_tg_id, granted_by) VALUES (?,?,?)""",
                    (t['id'], target_tg_id, call.from_user.id))
                granted += 1
            except Exception:
                pass
        await call.message.answer(
            f"✅ Выдан доступ ко <b>всем</b> приватным тестам "
            f"({granted} шт.) пользователю <b>{utils.escape_html(target_name)}</b>.",
            parse_mode="HTML")
        await state.clear()
        await _notify_user_grant(call.bot, target_tg_id, None, all_tests=True)
        await call.answer("✅")
        return

    try:
        test_id = int(arg)
    except ValueError:
        await call.answer()
        return

    test = db.fetchone("SELECT * FROM tests WHERE id=?", (test_id,))
    if not test:
        await call.answer("Тест не найден.", show_alert=True)
        return

    try:
        db.execute(
            """INSERT OR IGNORE INTO private_test_access
               (test_id, user_tg_id, granted_by) VALUES (?,?,?)""",
            (test_id, target_tg_id, call.from_user.id))
    except Exception as e:
        await call.answer(f"Ошибка: {e}", show_alert=True)
        return

    title = utils.escape_html(test['title'] or '—')
    await call.message.answer(
        f"✅ Доступ выдан!\n"
        f"<b>{utils.escape_html(target_name)}</b> теперь может пройти "
        f"тест <b>«{title}»</b>.",
        parse_mode="HTML")
    await state.clear()
    await _notify_user_grant(call.bot, target_tg_id, dict(test))
    await call.answer("✅")


async def _notify_user_grant(bot: Bot, target_tg_id: int,
                              test: dict = None, all_tests: bool = False):
    """Уведомляем пользователя о новом доступе."""
    try:
        if all_tests:
            text = (
                "🎉 <b>Вам открыт закрытый доступ!</b>\n\n"
                "Администратор открыл вам доступ ко <b>всем приватным тестам</b>.\n\n"
                "Перейдите в раздел «📚 Тесты» → «🔐 Мои закрытые тесты»."
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📚 Открыть каталог", callback_data="m:tests")
            ]])
        else:
            title = utils.escape_html(test.get('title') or '—')
            qcount = db.fetchone(
                "SELECT COUNT(*) AS c FROM questions WHERE test_id=?",
                (test['id'],))['c']
            text = (
                f"🎉 <b>Вам открыт закрытый доступ!</b>\n\n"
                f"🔐 Тест: <b>{title}</b>\n"
                f"📚 Вопросов: {qcount}\n"
                f"⏱ Время: {test.get('time_per_question') or 30} сек/вопрос\n\n"
                f"Этот тест не виден другим пользователям — "
                f"только тем, кому администратор лично его открыл."
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔓 Открыть тест",
                                      callback_data=f"opentest:{test['id']}")
            ]])
        await bot.send_message(target_tg_id, text,
                                reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        log.warning("Не удалось уведомить tg_id=%s о доступе: %s", target_tg_id, e)


# ============ Список юзеров с доступом ============

@router.callback_query(F.data == "opens:list", IsAdmin())
async def cb_opens_list(call: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = db.fetchall("""
        SELECT p.user_tg_id, p.granted_at, p.test_id,
               u.username, u.first_name,
               t.title AS test_title
        FROM private_test_access p
        LEFT JOIN users u ON u.tg_id = p.user_tg_id
        LEFT JOIN tests t ON t.id = p.test_id
        ORDER BY p.granted_at DESC LIMIT 100
    """)

    if not rows:
        text = "📋 <b>Список пользователей с приватным доступом</b>\n\n<i>Пока никому не выдавали.</i>"
    else:
        # Группируем по юзеру
        from collections import defaultdict
        by_user = defaultdict(list)
        users = {}
        for r in rows:
            tg = r['user_tg_id']
            users[tg] = r
            by_user[tg].append(r['test_title'] or f"#{r['test_id']}")

        lines = [f"📋 <b>Пользователи с приватным доступом ({len(by_user)}):</b>\n"]
        for tg, tests in list(by_user.items())[:20]:
            u = users[tg]
            name = ("@" + u['username']) if u['username'] else (u['first_name'] or f"id{tg}")
            lines.append(f"<b>{utils.escape_html(name)}</b>  (<code>{tg}</code>)")
            for t_name in tests[:3]:
                lines.append(f"  • {utils.escape_html(t_name[:40])}")
            if len(tests) > 3:
                lines.append(f"  • <i>…ещё {len(tests) - 3}</i>")
            lines.append("")
        text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Назад", callback_data="opens:back")
    kb.adjust(1)
    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup(),
                                       parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb.as_markup(),
                                    parse_mode="HTML")
    await call.answer()


# ============ Отзыв доступа ============

@router.callback_query(F.data == "opens:revoke", IsAdmin())
async def cb_opens_revoke(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(PrivateAccessStates.waiting_user_for_revoke)
    await call.message.answer(
        "🗑 Введите <b>@username</b> или <b>tg_id</b> пользователя, "
        "у которого хотите забрать <b>весь</b> приватный доступ:",
        parse_mode="HTML")
    await call.answer()


@router.message(PrivateAccessStates.waiting_user_for_revoke, IsAdmin())
async def s_opens_revoke(message: Message, state: FSMContext):
    arg = (message.text or "").strip()
    tg_id = None
    if arg.isdigit():
        tg_id = int(arg)
    else:
        target = utils.find_user_by_arg(arg)
        if target:
            tg_id = target['tg_id']
    if tg_id is None:
        await message.answer("❌ Не нашёл пользователя.")
        return

    before = db.fetchone(
        "SELECT COUNT(*) AS c FROM private_test_access WHERE user_tg_id=?",
        (tg_id,))['c']
    if before == 0:
        await message.answer("ℹ️ У этого пользователя не было приватного доступа.")
        await state.clear()
        return

    db.execute("DELETE FROM private_test_access WHERE user_tg_id=?", (tg_id,))
    await message.answer(
        f"✅ У пользователя <code>{tg_id}</code> отозван доступ ({before} тестов).",
        parse_mode="HTML")
    await state.clear()


# ============ Назад в меню ============

@router.callback_query(F.data == "opens:back", IsAdmin())
async def cb_opens_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🎟 Выдать доступ", callback_data="opens:grant")
    kb.button(text="📋 Список с доступом", callback_data="opens:list")
    kb.button(text="🗑 Отозвать доступ", callback_data="opens:revoke")
    kb.button(text="🔐 Приватные тесты", callback_data="opens:tests")
    kb.button(text="↩️ Закрыть", callback_data="opens:close")
    kb.adjust(1)
    text = (
        "🔐 <b>Закрытый доступ</b>\n\n"
        "Управление приватными тестами."
    )
    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup(),
                                       parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb.as_markup(),
                                    parse_mode="HTML")
    await call.answer()
