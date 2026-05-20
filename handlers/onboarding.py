"""
Онбординг для новых юзеров. 4 экрана с навигацией.
RU + KZ.
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
            "Бот сұрақтарды бір-бірлеп жібереді — викторина сияқты.\n\n"
            "⏱ Әр сұраққа таймер. Үлгермесең — өткізіледі.\n\n"
            "Соңында нәтижеңді көресің."
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
            "Админ рұқсат берсе — 🎉 хабарлама келеді. "
            "Каталогтан «🔐 Менің жабық тесттерім» бөлімінен тап.\n\n"
            "📢 <b>КАНАЛҒА ЖАЗЫЛ</b> @ent_biologydariga — сливтер мен талдаулар.\n\n"
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


async def start_onboarding(message: Message, user: dict):
    lang = user.get('language') or 'ru'
    name = user.get('first_name') or ("друг" if lang == "ru" else "досым")
    text = _txt(lang, "screen_1").format(name=utils.escape_html(name))
    try:
        await message.answer(text, reply_markup=_build_keyboard(lang, 1),
                              parse_mode="HTML")
    except Exception as e:
        log.exception("start_onboarding failed: %s", e)


async def _show_screen(call: CallbackQuery, user: dict, screen: int):
    lang = user.get('language') or 'ru'
    name = user.get('first_name') or ("друг" if lang == "ru" else "досым")
    text = _txt(lang, f"screen_{screen}")
    if screen == 1:
        text = text.format(name=utils.escape_html(name))
    kb = _build_keyboard(lang, screen)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            log.warning("show_screen error: %s", e)


@router.callback_query(F.data.startswith("onb:"))
async def cb_onboarding(call: CallbackQuery, user: dict = None, state: FSMContext = None):
    """Обработка кнопок онбординга. Crash-proof."""
    log.info("onb callback: %s", call.data)
    try:
        if state:
            await state.clear()
    except Exception:
        pass

    if user is None:
        user = {}

    try:
        arg = call.data.split(":")[1]
    except (ValueError, IndexError):
        try:
            await call.answer()
        except Exception:
            pass
        return

    lang = user.get('language') or 'ru'

    if arg.isdigit():
        screen = int(arg)
        if 1 <= screen <= 4:
            await _show_screen(call, user, screen)
            try:
                await call.answer()
            except Exception:
                pass
            return

    if arg == "done":
        try:
            db.execute(
                "UPDATE users SET onboarded_at=? WHERE tg_id=?",
                (utils.now_iso(), call.from_user.id))
        except Exception as e:
            log.warning("mark onboarded: %s", e)

        from keyboards import main_menu_kb
        from locales import t as _t
        is_a = False
        try:
            is_a = utils.is_admin(call.from_user.id)
        except Exception:
            pass
        text = _t("main_menu", lang)
        kb = main_menu_kb(lang, is_a)
        try:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            try:
                await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
            except Exception as e:
                log.warning("done send error: %s", e)
        try:
            await call.answer()
        except Exception:
            pass
        return

    try:
        await call.answer()
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
