"""
Онбординг — обучение нового юзера при первом /start.
4 экрана с кнопками «Дальше / Назад / Пропустить».
Поддержка RU и KZ.
"""
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
import utils

router = Router(name="onboarding")
log = logging.getLogger(__name__)


# ========== ТЕКСТЫ ==========

TEXTS = {
    "ru": {
        "screen_1": (
            "👋 <b>Салют, {name}!</b>\n\n"
            "Я твой помощник по ЕНТ. Со мной ты:\n\n"
            "📚 Будешь решать тесты по предметам — с настоящим таймером, как на экзамене\n\n"
            "⚔️ Сможешь рубиться 1-на-1 в дуэлях с другими учениками\n\n"
            "🏆 Подниматься в рейтинге и видеть кто реально шарит\n\n"
            "👥 Звать друзей в группу и устраивать квиз-баттлы прямо там\n\n"
            "Покажу тебе всё за 30 секунд — клянусь не утомлю. "
            "Потом сам ЕНТ покажется проще 😎"
        ),
        "screen_2": (
            "📚 <b>ТЕСТЫ — самое главное здесь</b>\n\n"
            "Тыкаешь «📚 Тесты» в меню → выбираешь предмет "
            "(Биология, История, География...) → выбираешь конкретный тест → "
            "жмёшь «▶️ Пройти тест».\n\n"
            "Дальше бот начнёт кидать тебе вопросы по одному, как настоящие "
            "квизы в Telegram.\n\n"
            "⏱ На каждый — таймер. Не ответил — вопрос пропускается "
            "(как на ЕНТ — не успел, потерял балл).\n\n"
            "В конце увидишь: сколько правильно, сколько неправильно, где затупил. "
            "Можешь пройти тест ещё раз — но в рейтинг засчитается только первая попытка."
        ),
        "screen_3": (
            "⚔️ <b>ДУЭЛЬ — это огонь 🔥</b>\n\n"
            "Жмёшь «⚔️ Дуэль» → «🎯 Найти соперника» → "
            "бот находит тебе случайного игрока такого же уровня.\n\n"
            "Дальше вы вдвоём отвечаете на 10 общих вопросов. Кто быстрее и точнее — "
            "тот победил. Победителю — очки в рейтинг.\n\n"
            "🏆 <b>РЕЙТИНГ — кто тут самый умный</b>\n\n"
            "В «🏆 Рейтинг» — топ-100 игроков. Можно посмотреть за неделю или за "
            "всё время. Цель — пробиться в топ.\n\n"
            "📊 <b>«Мои результаты»</b> — твоя личная история: какие тесты ты прошёл, "
            "со сколькими процентами, где слабые места. Полезно смотреть перед ЕНТ."
        ),
        "screen_4": (
            "🔐 <b>ЗАКРЫТЫЕ ТЕСТЫ — фишка для своих</b>\n\n"
            "Если админ откроет тебе доступ к закрытому тесту (например, сливам или "
            "эксклюзивному пробнику) — придёт уведомление с 🎉.\n\n"
            "Эти тесты ищи в каталоге под кнопкой «🔐 Мои закрытые тесты» — "
            "она появляется автоматически, когда у тебя есть доступ.\n\n"
            "📢 <b>ПОДПИШИСЬ НА КАНАЛ</b> @ent_biologydariga — там сливы, "
            "разборы заданий, советы. Без него бот вообще требует подписку, "
            "так что лучше сразу.\n\n"
            "💬 <b>ЕСЛИ ЧТО-ТО НЕ ТАК</b> — жми «🛠 Техподдержка». Напишешь — ответим.\n\n"
            "Всё, теперь ты во всеоружии. Удачи на ЕНТ 🚀"
        ),
        "btn_start": "▶️ Поехали!",
        "btn_skip": "⏭️ Я и так разберусь",
        "btn_back": "⬅️ Назад",
        "btn_next": "➡️ Дальше",
        "btn_to_tests": "📚 Сразу к тестам",
        "btn_to_menu": "🏠 В главное меню",
    },
    "kz": {
        "screen_1": (
            "👋 <b>Сәлем, {name}!</b>\n\n"
            "Мен сенің ҰБТ-ға дайындалуға көмекшің. Менімен бірге сен:\n\n"
            "📚 Пәндер бойынша тесттерді шешесің — нағыз емтихандағыдай таймермен\n\n"
            "⚔️ Басқа оқушылармен 1-ге-1 дуэльге шыға аласың\n\n"
            "🏆 Рейтингте жоғары көтеріле аласың — кім шынымен мықты екенін көресің\n\n"
            "👥 Достарыңды топқа шақырып, бірге квиз-сайыстар өткізе аласың\n\n"
            "Барлығын 30 секундта көрсетемін — жалықтырмаймын деп уәде беремін 😎\n"
            "Содан кейін ҰБТ оп-оңай көрінеді."
        ),
        "screen_2": (
            "📚 <b>ТЕСТТЕР — мұндағы ең басты нәрсе</b>\n\n"
            "Мәзірден «📚 Тесттер» басасың → пәнді таңдайсың "
            "(Биология, Тарих, География...) → нақты тестті таңдайсың → "
            "«▶️ Тестті өту» басасың.\n\n"
            "Содан бот саған сұрақтарды бір-бірлеп жібереді — "
            "Telegram-дағы кәдімгі викториналар сияқты.\n\n"
            "⏱ Әр сұраққа таймер бар. Жауап бермесең — сұрақ өткізіледі "
            "(ҰБТ-дағы сияқты — үлгермедің, балл жоғалттың).\n\n"
            "Соңында көресің: қаншасына дұрыс, қаншасына қате жауап бердің, "
            "қай жерде қателестің. Тестті қайта өте аласың — бірақ рейтингке "
            "тек бірінші әрекет есептеледі."
        ),
        "screen_3": (
            "⚔️ <b>ДУЭЛЬ — бұл от 🔥</b>\n\n"
            "«⚔️ Дуэль» басасың → «🎯 Қарсылас тап» → "
            "бот саған өзіңмен бір деңгейдегі кездейсоқ ойыншыны табады.\n\n"
            "Содан екеуің 10 ортақ сұраққа жауап бересіңдер. Кім тез әрі дұрыс — "
            "сол жеңеді. Жеңімпазға — рейтинг ұпайлары.\n\n"
            "🏆 <b>РЕЙТИНГ — кім ең ақылды</b>\n\n"
            "«🏆 Рейтинг» бөлімінде — топ-100 ойыншы. Аптаға немесе барлық уақытқа "
            "қарай көре аласың. Мақсат — топқа кіру.\n\n"
            "📊 <b>«Менің нәтижелерім»</b> — сенің жеке тарихың: қандай тесттер өттің, "
            "неше процентпен, әлсіз жерлерің қайда. ҰБТ алдында қарап шығу пайдалы."
        ),
        "screen_4": (
            "🔐 <b>ЖАБЫҚ ТЕСТТЕР — өз үшіндегілерге</b>\n\n"
            "Егер админ саған жабық тестке (мысалы, сливтерге немесе эксклюзивті "
            "сынақ тестке) рұқсат берсе — 🎉 хабарламасы келеді.\n\n"
            "Бұл тесттерді каталогтан «🔐 Менің жабық тесттерім» түймесінен табасың — "
            "ол рұқсат болғанда автоматты түрде пайда болады.\n\n"
            "📢 <b>КАНАЛҒА ЖАЗЫЛ</b> @ent_biologydariga — сонда сливтер, "
            "тапсырмаларды талдау, кеңестер. Жазылмасаң, бот сені бәрібір талап етеді, "
            "сондықтан бірден жазылған дұрыс.\n\n"
            "💬 <b>БІР НӘРСЕ ДҰРЫС БОЛМАСА</b> — «🛠 Техқолдау» бас. Жазсаң — жауап береміз.\n\n"
            "Болды, енді сен бәріне дайынсың. ҰБТ-да сәттілік 🚀"
        ),
        "btn_start": "▶️ Бастаймыз!",
        "btn_skip": "⏭️ Өзім түсінемін",
        "btn_back": "⬅️ Артқа",
        "btn_next": "➡️ Әрі қарай",
        "btn_to_tests": "📚 Бірден тесттерге",
        "btn_to_menu": "🏠 Басты мәзірге",
    }
}


def _txt(lang: str, key: str) -> str:
    """Получить текст по ключу для языка (с фоллбэком на RU)."""
    return TEXTS.get(lang, TEXTS["ru"]).get(key) or TEXTS["ru"].get(key, key)


# ========== ОТПРАВКА ЭКРАНОВ ==========

def _build_keyboard(lang: str, screen: int) -> InlineKeyboardMarkup:
    """Кнопки для каждого экрана."""
    kb = InlineKeyboardBuilder()
    if screen == 1:
        kb.button(text=_txt(lang, "btn_start"), callback_data="onb:2")
        kb.button(text=_txt(lang, "btn_skip"), callback_data="onb:skip")
    elif screen == 2:
        kb.button(text=_txt(lang, "btn_back"), callback_data="onb:1")
        kb.button(text=_txt(lang, "btn_next"), callback_data="onb:3")
    elif screen == 3:
        kb.button(text=_txt(lang, "btn_back"), callback_data="onb:2")
        kb.button(text=_txt(lang, "btn_next"), callback_data="onb:4")
    elif screen == 4:
        kb.button(text=_txt(lang, "btn_to_tests"), callback_data="onb:done_tests")
        kb.button(text=_txt(lang, "btn_to_menu"), callback_data="onb:done_menu")
    if screen in (1,):
        kb.adjust(1)
    elif screen in (2, 3):
        kb.adjust(2)
    else:
        kb.adjust(1)
    return kb.as_markup()


async def start_onboarding(message: Message, user: dict):
    """Запустить онбординг с экрана 1."""
    lang = user.get('language') or 'ru'
    name = user.get('first_name') or "друг"
    text = _txt(lang, "screen_1").format(name=utils.escape_html(name))
    kb = _build_keyboard(lang, 1)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def show_screen(call: CallbackQuery, user: dict, screen: int):
    """Показать конкретный экран онбординга."""
    lang = user.get('language') or 'ru'
    name = user.get('first_name') or "друг"
    key = f"screen_{screen}"
    text = _txt(lang, key)
    if screen == 1:
        text = text.format(name=utils.escape_html(name))
    kb = _build_keyboard(lang, screen)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


# ========== ХЕНДЛЕРЫ ==========

@router.callback_query(F.data.startswith("onb:"))
async def cb_onboarding(call: CallbackQuery, user: dict, state: FSMContext):
    arg = call.data.split(":")[1]
    lang = user.get('language') or 'ru'

    if arg.isdigit():
        screen = int(arg)
        if 1 <= screen <= 4:
            await show_screen(call, user, screen)
            return

    if arg in ("skip", "done_menu", "done_tests"):
        # Помечаем что юзер прошёл онбординг
        try:
            db.execute(
                "UPDATE users SET onboarded_at=? WHERE tg_id=?",
                (utils.now_iso(), call.from_user.id))
        except Exception:
            pass

        # Удаляем сообщение онбординга
        try:
            await call.message.delete()
        except Exception:
            pass

        # Открываем главное меню или каталог
        from keyboards import main_menu_kb
        from locales import t

        if arg == "done_tests":
            # Сразу открываем каталог тестов
            # симулируем нажатие "m:tests" — но проще отправить новое меню
            call.data = "m:tests"
            from handlers import user as _user_handler
            await _user_handler.cb_tests_menu(call, user)
        else:
            # Главное меню
            try:
                await call.message.answer(
                    t("main_menu", lang),
                    reply_markup=main_menu_kb(lang, utils.is_admin(call.from_user.id)))
            except Exception:
                pass
        await call.answer()
        return

    await call.answer()


# ========== HELPERS ==========

def is_onboarded(tg_id: int) -> bool:
    """Проверка прошёл ли юзер онбординг."""
    row = db.fetchone("SELECT onboarded_at FROM users WHERE tg_id=?", (tg_id,))
    if not row:
        return False
    return bool(row.get('onboarded_at'))
