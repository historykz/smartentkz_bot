"""
Онбординг — 4 экрана с навигацией. RU + KZ.
Запускается через cb_onb_start_X из выбора языка.
"""
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
import utils

router = Router(name="onboarding")
log = logging.getLogger(__name__)


TEXTS = {
    "ru": {
        "screen_1": (
            "👋 <b>Салют, {name}!</b>\n\n"
            "Я твой помощник по ЕНТ. Со мной ты:\n\n"
            "📚 Будешь решать тесты — с настоящим таймером, как на экзамене\n\n"
            "⚔️ Сможешь рубиться 1-на-1 в дуэлях\n\n"
            "🏆 Подниматься в рейтинге\n\n"
            "👥 Звать друзей и устраивать квиз-баттлы\n\n"
            "Покажу всё за 30 секунд 😎"
        ),
        "screen_2": (
            "📚 <b>ТЕСТЫ — самое главное</b>\n\n"
            "Тапаешь «📚 Тесты» → выбираешь предмет → конкретный тест → "
            "жмёшь «▶️ Пройти тест».\n\n"
            "Бот кидает вопросы по одному — как квиз в Telegram.\n\n"
            "⏱ На каждый вопрос — таймер. Не успел — пропускается.\n\n"
            "В конце увидишь сколько правильно ответил."
        ),
        "screen_3": (
            "⚔️ <b>ДУЭЛЬ — 1 на 1</b>\n\n"
            "«⚔️ Дуэль» → «🎯 Найти соперника» → бот находит игрока.\n\n"
            "10 общих вопросов. Кто быстрее и точнее — побеждает.\n\n"
            "🏆 <b>РЕЙТИНГ</b> — топ-100 игроков. Цель — попасть в топ.\n\n"
            "📊 <b>«Мои результаты»</b> — твоя личная история."
        ),
        "screen_4": (
            "🔐 <b>ЗАКРЫТЫЕ ТЕСТЫ</b>\n\n"
            "Если админ откроет доступ — придёт уведомление 🎉. "
            "Ищи их в каталоге под «🔐 Мои закрытые тесты».\n\n"
            "📢 <b>ПОДПИШИСЬ НА КАНАЛ</b> @ent_biologydariga — сливы и разборы.\n\n"
            "💬 Вопросы → «🛠 Техподдержка».\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>СМЕНА ЯЗЫКА</b>\n"
            "«👤 Профиль» → «🌐 Сменить язык»\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Удачи на ЕНТ! 🚀"
        ),
        "btn_start": "▶️ Поехали!",
        "btn_skip": "⏭️ Я и так разберусь",
        "btn_back": "⬅️ Назад",
        "btn_next": "➡️ Дальше",
        "btn_done": "🏠 В главное меню",
    },
    "kz": {
        "screen_1": (
            "👋 <b>Сәлем, {name}!</b>\n\n"
            "Мен сенің ҰБТ-ға дайындалуға көмекшің. Менімен бірге:\n\n"
            "📚 Тесттерді шешесің — нағыз емтихандағыдай таймермен\n\n"
            "⚔️ Басқа оқушылармен 1-ге-1 дуэльге шығасың\n\n"
            "🏆 Рейтингте жоғары көтерілесің\n\n"
            "👥 Достарыңмен квиз-сайыстар өткізесің\n\n"
            "Барлығын 30 секундта көрсетемін 😎"
        ),
        "screen_2": (
            "📚 <b>ТЕСТТЕР — ең басты</b>\n\n"
            "«📚 Тесттер» → пәнді таңда → нақты тестті таңда → "
            "«▶️ Тестті өту» бас.\n\n"
            "Бот сұрақтарды бір-бірлеп жібереді.\n\n"
            "⏱ Әр сұраққа таймер. Үлгермесең — өткізіледі."
        ),
        "screen_3": (
            "⚔️ <b>ДУЭЛЬ — 1-ге-1</b>\n\n"
            "«⚔️ Дуэль» → «🎯 Қарсылас тап» → бот ойыншы табады.\n\n"
            "10 сұраққа жауап бересіңдер. Кім тез әрі дұрыс — сол жеңеді.\n\n"
            "🏆 <b>РЕЙТИНГ</b> — топ-100 ойыншы.\n\n"
            "📊 <b>«Менің нәтижелерім»</b> — жеке тарихың."
        ),
        "screen_4": (
            "🔐 <b>ЖАБЫҚ ТЕСТТЕР</b>\n\n"
            "Админ рұқсат берсе — 🎉 хабарлама келеді.\n\n"
            "📢 <b>КАНАЛҒА ЖАЗЫЛ</b> @ent_biologydariga\n\n"
            "💬 Сұрақтар → «🛠 Техқолдау».\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>ТІЛДІ АУЫСТЫРУ</b>\n"
            "«👤 Профиль» → «🌐 Тілді ауыстыру»\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "ҰБТ-да сәттілік! 🚀"
        ),
        "btn_start": "▶️ Бастаймыз!",
        "btn_skip": "⏭️ Өзім түсінемін",
        "btn_back": "⬅️ Артқа",
        "btn_next": "➡️ Әрі қарай",
        "btn_done": "🏠 Басты мәзірге",
    }
}


def _txt(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS["ru"]).get(key) or TEXTS["ru"].get(key, key)


def _get_user_lang(tg_id: int) -> str:
    """Достаём язык юзера из БД."""
    try:
        row = db.fetchone("SELECT language, first_name FROM users WHERE tg_id=?", (tg_id,))
        if row and row.get('language'):
            return row['language']
    except Exception:
        pass
    return 'ru'


def _get_user_name(tg_id: int, lang: str = 'ru') -> str:
    try:
        row = db.fetchone("SELECT first_name FROM users WHERE tg_id=?", (tg_id,))
        if row and row.get('first_name'):
            return row['first_name']
    except Exception:
        pass
    return "друг" if lang == "ru" else "досым"


def _build_keyboard(lang: str, screen: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if screen == 1:
        kb.button(text=_txt(lang, "btn_start"), callback_data="onb:2")
        kb.button(text=_txt(lang, "btn_skip"), callback_data="onb:done")
        kb.adjust(1)
    elif screen == 2:
        kb.button(text=_txt(lang, "btn_back"), callback_data="onb:1")
        kb.button(text=_txt(lang, "btn_next"), callback_data="onb:3")
        kb.adjust(2)
    elif screen == 3:
        kb.button(text=_txt(lang, "btn_back"), callback_data="onb:2")
        kb.button(text=_txt(lang, "btn_next"), callback_data="onb:4")
        kb.adjust(2)
    elif screen == 4:
        kb.button(text=_txt(lang, "btn_done"), callback_data="onb:done")
        kb.adjust(1)
    return kb.as_markup()


async def start_onboarding(message: Message, user: dict = None):
    """Запуск онбординга с экрана 1."""
    tg_id = message.from_user.id
    lang = (user or {}).get('language') or _get_user_lang(tg_id)
    name = (user or {}).get('first_name') or _get_user_name(tg_id, lang)
    text = _txt(lang, "screen_1").format(name=utils.escape_html(name))
    try:
        await message.answer(text, reply_markup=_build_keyboard(lang, 1),
                              parse_mode="HTML")
    except Exception as e:
        log.exception("start_onboarding: %s", e)


@router.callback_query(F.data.startswith("onb:"))
async def cb_onboarding(call: CallbackQuery, **kwargs):
    """ВСЕ кнопки онбординга. Не зависит от middleware параметров."""
    # Сначала ОТВЕТЬ на callback — Telegram перестанет показывать «загрузка»
    try:
        await call.answer()
    except Exception as e:
        log.warning("call.answer failed: %s", e)

    # Логируем что callback пришёл
    log.info("=== ONB CALLBACK ===  data=%s  tg_id=%s",
              call.data,
              call.from_user.id if call.from_user else 'None')

    # Защита от всех ошибок
    try:
        # Сброс FSM-состояния
        state = kwargs.get('state')
        if state:
            try:
                await state.set_state(None)
            except Exception:
                pass

        # Парсинг callback
        try:
            arg = call.data.split(":")[1]
        except (ValueError, IndexError):
            log.warning("Bad callback data: %s", call.data)
            return

        tg_id = call.from_user.id if call.from_user else 0
        lang = _get_user_lang(tg_id)
        name = _get_user_name(tg_id, lang)

        # Экран по номеру
        if arg.isdigit():
            screen = int(arg)
            if 1 <= screen <= 4:
                text = _txt(lang, f"screen_{screen}")
                if screen == 1:
                    text = text.format(name=utils.escape_html(name))
                kb = _build_keyboard(lang, screen)

                # Пытаемся отредактировать или отправить
                sent = False
                try:
                    await call.message.edit_text(text, reply_markup=kb,
                                                   parse_mode="HTML")
                    sent = True
                except Exception as e:
                    log.warning("edit_text failed: %s", e)

                if not sent:
                    try:
                        await call.message.answer(text, reply_markup=kb,
                                                    parse_mode="HTML")
                    except Exception as e:
                        log.warning("answer failed: %s", e)
                        # Последняя надежда — через bot
                        try:
                            await call.bot.send_message(
                                call.from_user.id, text, reply_markup=kb,
                                parse_mode="HTML")
                        except Exception as e2:
                            log.exception("All sends failed: %s", e2)
                return

        # Завершение
        if arg == "done":
            try:
                db.execute(
                    "UPDATE users SET onboarded_at=? WHERE tg_id=?",
                    (utils.now_iso(), tg_id))
            except Exception as e:
                log.warning("mark onboarded failed: %s", e)

            # Открываем главное меню
            try:
                from keyboards import main_menu_kb
                from locales import t as _t
                is_a = False
                try:
                    is_a = utils.is_admin(tg_id)
                except Exception:
                    pass
                text = _t("main_menu", lang)
                kb = main_menu_kb(lang, is_a)
                try:
                    await call.message.edit_text(text, reply_markup=kb)
                except Exception:
                    try:
                        await call.message.answer(text, reply_markup=kb)
                    except Exception:
                        await call.bot.send_message(tg_id, text, reply_markup=kb)
            except Exception as e:
                log.exception("done finalize failed: %s", e)
            return

    except Exception as e:
        log.exception("=== ONB CALLBACK FATAL ===: %s", e)
        try:
            await call.message.answer(f"⚠️ Ошибка онбординга: {e}")
        except Exception:
            pass


def is_onboarded(tg_id: int) -> bool:
    try:
        row = db.fetchone("SELECT onboarded_at FROM users WHERE tg_id=?", (tg_id,))
        if not row:
            return False
        return bool(row.get('onboarded_at'))
    except Exception:
        return False


def reset_onboarding(tg_id: int):
    """Сбросить флаг — для команды /restart_onboarding или принудительного показа."""
    try:
        db.execute("UPDATE users SET onboarded_at=NULL WHERE tg_id=?", (tg_id,))
    except Exception:
        pass
