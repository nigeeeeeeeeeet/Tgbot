"""
Telegram бот на aiogram 3 для поиска свободных 5-буквенных юзернеймов.

Установка:
    pip install aiogram aiohttp

Запуск:
    python username_finder_bot.py
"""

import asyncio
import random
import string
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage

# ⚠️ ЗАМЕНИ НА СВОЙ ТОКЕН (получи новый у @BotFather)
BOT_TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния поиска по chat_id
search_tasks: dict[int, asyncio.Task] = {}

VOWELS = "aeiouy"
CONSONANTS = "bcdfghjklmnpqrstvwxz"
COOL_PATTERNS = ["CVCVC", "VCVCV", "CVVCV", "CVCVV", "CCVVC"]


# ───────────────────────── Генерация ─────────────────────────

def generate_username() -> str:
    pattern = random.choice(COOL_PATTERNS)
    result = ""
    for ch in pattern:
        result += random.choice(VOWELS if ch == "V" else CONSONANTS)
    return result


# ───────────────────────── Проверка ──────────────────────────

async def check_telegram(session: aiohttp.ClientSession, username: str) -> bool:
    """Проверка через Telegram getChat — True если свободен."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat"
    try:
        async with session.post(url, json={"chat_id": f"@{username}"}, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            data = await resp.json()
            if data.get("ok"):
                return False  # Чат существует — занят
            desc = data.get("description", "").lower()
            return "not found" in desc or "invalid" in desc
    except Exception:
        return False


async def check_fragment(session: aiohttp.ClientSession, username: str) -> bool:
    """Проверка через Fragment.com — True если свободен/продаётся."""
    url = f"https://fragment.com/username/{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return False
            text = (await resp.text()).lower()
            if "owner" in text or "telegram:" in text:
                return False
            return "buy username" in text or "for sale" in text or "available" in text
    except Exception:
        return False


async def is_available(session: aiohttp.ClientSession, username: str) -> bool:
    tg_free = await check_telegram(session, username)
    if not tg_free:
        return False
    return await check_fragment(session, username)


# ───────────────────────── Клавиатуры ────────────────────────

def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Найти 5", callback_data="find:5"),
            InlineKeyboardButton(text="🎯 Найти 10", callback_data="find:10"),
        ],
        [InlineKeyboardButton(text="💡 Как это работает?", callback_data="how")],
    ])


def result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Искать ещё", callback_data="again"),
            InlineKeyboardButton(text="🏠 Главная", callback_data="menu"),
        ]
    ])


def stop_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛔ Остановить поиск", callback_data="stop")]
    ])


# ───────────────────────── Поиск ─────────────────────────────

async def run_search(chat_id: int, message_id: int, count: int):
    found: list[str] = []
    checked = 0
    max_checks = 600

    async with aiohttp.ClientSession() as session:
        while len(found) < count and checked < max_checks:
            username = generate_username()
            checked += 1

            try:
                ok = await is_available(session, username)
            except asyncio.CancelledError:
                break
            except Exception:
                ok = False

            if ok:
                found.append(username)

            # Обновляем статус каждые 5 проверок
            if checked % 5 == 0:
                try:
                    await bot.edit_message_text(
                        f"🔍 Ищу свободные юзернеймы...\n"
                        f"Проверено: {checked} | Найдено: {len(found)}/{count}",
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=stop_kb(),
                    )
                except Exception:
                    pass

            await asyncio.sleep(0.25)

    # Итог
    if found:
        lines = "\n".join(
            f"`{i}.` [@{u}](https://t.me/{u}) — [Fragment](https://fragment.com/username/{u})"
            for i, u in enumerate(found, 1)
        )
        text = (
            f"✅ Готово\\! Проверено: {checked}\n\n"
            f"🎯 *Свободные юзернеймы:*\n\n{lines}\n\n"
            f"💡 Жми Fragment — и быстрее регистрируй\\!"
        )
    else:
        text = (
            f"😔 Проверено {checked} вариантов — ничего не нашёл\\.\n"
            f"Попробуй ещё раз — каждый раз новые комбинации\\!"
        )

    try:
        await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="MarkdownV2",
            reply_markup=result_kb(),
            disable_web_page_preview=True,
        )
    except Exception:
        pass

    search_tasks.pop(chat_id, None)


# ───────────────────────── Хендлеры ──────────────────────────

@dp.message(CommandStart())
@dp.message(Command("menu"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 *Привет\\! Ищу свободные 5\\-буквенные юзернеймы в Telegram\\.* \n\n"
        "🔤 Генерирую читаемые комбинации букв\n"
        "✅ Проверяю через Telegram API \\+ Fragment\n"
        "🔗 Даю прямые ссылки для регистрации\n\n"
        "Выбери сколько юзернеймов искать:",
        parse_mode="MarkdownV2",
        reply_markup=main_kb(),
    )


@dp.callback_query(F.data.startswith("find:"))
async def cb_find(call: CallbackQuery):
    chat_id = call.message.chat.id
    count = int(call.data.split(":")[1])

    if chat_id in search_tasks:
        await call.answer("⏳ Поиск уже идёт!", show_alert=True)
        return

    msg = await call.message.edit_text(
        f"🔍 Запускаю поиск {count} юзернеймов...\nПроверено: 0 | Найдено: 0/{count}",
        reply_markup=stop_kb(),
    )

    task = asyncio.create_task(run_search(chat_id, msg.message_id, count))
    search_tasks[chat_id] = task
    await call.answer("🚀 Поиск начат!")


@dp.callback_query(F.data == "stop")
async def cb_stop(call: CallbackQuery):
    chat_id = call.message.chat.id
    task = search_tasks.pop(chat_id, None)
    if task:
        task.cancel()
        await call.message.edit_text(
            "⛔ Поиск остановлен.",
            reply_markup=result_kb(),
        )
        await call.answer("Остановлено.")
    else:
        await call.answer("Поиск уже завершён.")


@dp.callback_query(F.data == "again")
async def cb_again(call: CallbackQuery):
    await call.message.edit_text(
        "Сколько юзернеймов искать?",
        reply_markup=main_kb(),
    )
    await call.answer()


@dp.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery):
    await call.message.edit_text(
        "👋 *Главное меню*\n\nВыбери сколько юзернеймов искать:",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )
    await call.answer()


@dp.callback_query(F.data == "how")
async def cb_how(call: CallbackQuery):
    text = (
        "⚙️ *Как работает бот:*\n\n"
        "1️⃣ Генерирует читаемые 5-буквенные слова\n"
        "   (чередование гласных и согласных)\n\n"
        "2️⃣ Проверяет через *Telegram API*\n"
        "   — существует ли уже такой чат/канал\n\n"
        "3️⃣ Проверяет через *Fragment.com*\n"
        "   — доступен ли для регистрации\n\n"
        "4️⃣ Показывает только прошедшие обе проверки\n\n"
        "⚠️ Действуй быстро — юзернейм могут занять!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu")]
    ])
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.message()
async def fallback(message: Message):
    await message.answer("Используй кнопки 👇", reply_markup=main_kb())


# ───────────────────────── Запуск ────────────────────────────

async def main():
    print("🤖 Бот запущен на aiogram 3! Ctrl+C для остановки.")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
