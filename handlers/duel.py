"""Хендлеры дуэлей 1 на 1."""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

import utils
from locales import t
from keyboards import duel_menu_kb, duel_cancel_kb, back_kb, main_menu_kb
from states import DuelStates
import database as db
from services import duel_service

router = Router(name="duel")
log = logging.getLogger(__name__)


@router.callback_query(F.data == "m:duel")
async def cb_duel_menu(call: CallbackQuery, user: dict):
    lang = user.get('language') or 'ru'
    if call.message.chat.type != "private":
        await call.answer(t("personal_chat_only", lang), show_alert=True)
        return
    try:
        await call.message.edit_text(t("duel_menu", lang),
                                       reply_markup=duel_menu_kb(lang),
                                       parse_mode="HTML")
    except Exception:
        await call.message.answer(t("duel_menu", lang),
                                    reply_markup=duel_menu_kb(lang),
                                    parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "duel:invite")
async def cb_duel_invite(call: CallbackQuery, user: dict):
    lang = user.get('language') or 'ru'
    if call.message.chat.type != "private":
        await call.answer(t("personal_chat_only", lang), show_alert=True)
        return
    await call.answer()
    # Сначала выбор раздела
    cats = duel_service.get_duel_categories(lang)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for c in cats:
        emoji = c.get('emoji') or '📚'
        kb.button(text=f"{emoji} {c['name']}",
                  callback_data=f"duelcat:{c['id']}")
    # Все разделы вместе
    kb.button(text="🎲 Все разделы (вперемешку)", callback_data="duelcat:all")
    kb.button(text="↩️ Назад", callback_data="duel:menu")
    kb.adjust(1)
    if not cats:
        await call.message.answer(
            "⚠️ Пока нет бесплатных тестов для дуэли. Попроси админа добавить."
            if lang == "ru" else
            "⚠️ Дуэль үшін тегін тесттер жоқ. Әкімшіден сұра.")
        return
    await call.message.answer(
        "⚔️ <b>Дуэль</b>\n\nПо какому разделу сыграем?\n"
        "<i>Вопросы будут только из выбранного раздела.</i>"
        if lang == "ru" else
        "⚔️ <b>Дуэль</b>\n\nҚай бөлім бойынша ойнаймыз?",
        reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("duelcat:"))
async def cb_duel_category_chosen(call: CallbackQuery, user: dict):
    """Раздел выбран — создаём ссылку-приглашение."""
    lang = user.get('language') or 'ru'
    arg = call.data.split(":")[1]
    category_id = None if arg == "all" else int(arg)
    await call.answer()

    code = await duel_service.create_invite(
        call.from_user.id, call.message.chat.id, lang, category_id=category_id)
    import config
    bot_un = getattr(config, 'BOT_USERNAME', '') or ''
    if not bot_un:
        try:
            bot_un = (await call.bot.get_me()).username
        except Exception:
            bot_un = ''
    link = f"https://t.me/{bot_un}?start=duel_{code}"

    # Название раздела
    cat_name = "все разделы"
    if category_id:
        c = db.fetchone("SELECT name FROM test_categories WHERE id=?", (category_id,))
        cat_name = c['name'] if c else "раздел"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    invite_text = (
        f"⚔️ Я приглашаю тебя на дуэль!\n"
        f"📚 Раздел: {cat_name}\n"
        "Заходи, если не струсил 😏"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Принять участие", url=link)
    ]])
    await call.message.answer(
        "🔗 <b>Готово! Перешли это сообщение другу или в чат:</b>",
        parse_mode="HTML")
    await call.message.answer(invite_text, reply_markup=kb)
    await call.message.answer(
        "⚠️ Дуэль на 2 человек. Первый кто нажмёт «Принять участие» — "
        "сыграет с тобой. Жди соперника! ⏳" if lang == "ru"
        else "⚠️ Дуэль 2 адамға. «Қатысу» басқан бірінші адам сенімен ойнайды. "
             "Қарсыласты күт! ⏳")



async def cb_duel_fast(call: CallbackQuery, state: FSMContext, user: dict):
    lang = user.get('language') or 'ru'
    # Проверим, не в активной ли он уже дуэли
    active = await duel_service.get_active_duel_for(user['id'])
    if active:
        await call.answer(t("duel_already_in", lang), show_alert=True)
        return

    duel_id = await duel_service.join_queue(call.bot, user['id'],
                                             call.message.chat.id, lang)
    if duel_id:
        # Сразу нашли пару
        try:
            await call.message.delete()
        except Exception:
            pass
        await state.set_state(DuelStates.in_duel)
    else:
        try:
            await call.message.edit_text(t("duel_searching", lang),
                                         reply_markup=duel_cancel_kb(lang))
        except Exception:
            await call.message.answer(t("duel_searching", lang),
                                      reply_markup=duel_cancel_kb(lang))
        await state.set_state(DuelStates.searching)
    await call.answer()


@router.callback_query(F.data == "duel:subject")
async def cb_duel_subject(call: CallbackQuery, state: FSMContext, user: dict):
    """Дуэль по предмету — в этой реализации соответствует обычному поиску."""
    await cb_duel_fast(call, state, user)


@router.callback_query(F.data == "duel:cancel")
async def cb_duel_cancel(call: CallbackQuery, state: FSMContext, user: dict):
    lang = user.get('language') or 'ru'
    removed = await duel_service.leave_queue(user['id'])
    if not removed:
        # Может, активная дуэль
        active = await duel_service.get_active_duel_for(user['id'])
        if active:
            await duel_service.abort_duel_by_user(call.bot, user['id'])
    await state.clear()
    try:
        await call.message.edit_text(t("duel_cancelled", lang),
                                     reply_markup=main_menu_kb(lang, utils.is_admin(call.from_user.id)))
    except Exception:
        await call.message.answer(t("duel_cancelled", lang),
                                  reply_markup=main_menu_kb(lang, utils.is_admin(call.from_user.id)))
    await call.answer()


@router.callback_query(F.data == "duel:history")
async def cb_duel_history(call: CallbackQuery, user: dict):
    lang = user.get('language') or 'ru'
    stats = duel_service.get_duels_stats(user['id'])
    text = t("duel_history", lang,
             wins=stats['wins'], losses=stats['losses'], total=stats['total'])
    try:
        await call.message.edit_text(text, reply_markup=back_kb(lang, "m:duel"))
    except Exception:
        await call.message.answer(text, reply_markup=back_kb(lang, "m:duel"))
    await call.answer()


@router.callback_query(F.data.startswith("duelans:"))
async def cb_duel_answer(call: CallbackQuery, user: dict):
    lang = user.get('language') or 'ru'
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer()
        return
    try:
        duel_id = int(parts[1])
        question_id = int(parts[2])
        option_id = int(parts[3])
    except ValueError:
        await call.answer()
        return

    result = await duel_service.process_duel_answer(
        call.bot, duel_id, user['id'], question_id, option_id)

    if result == 'ok':
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer(t("answer_recorded", lang))
    elif result == 'already':
        await call.answer(t("already_answered", lang), show_alert=True)
    elif result == 'old':
        await call.answer(t("old_button", lang), show_alert=True)
    else:
        await call.answer(t("error_generic", lang), show_alert=True)
