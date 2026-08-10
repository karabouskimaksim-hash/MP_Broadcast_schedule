# -*- coding: utf-8 -*-
"""
Telegram-бот «Календарь эфиров».

Возможности:
  /start, /calendar  — открыть календарь; даты с эфирами помечены 🎬
  клик по дате       — карточка эфира + кнопки-ссылки на YouTube и ВКонтакте
  /add               — добавить эфир (только админы)
  /del ГГГГ-ММ-ДД    — удалить эфир (только админы)
  /list              — список всех эфиров (только админы)

Формат /add:
  /add 2026-08-10 | Название эфира | Описание | https://youtu.be/... | https://vk.com/video...
  (описание можно оставить пустым: /add 2026-08-10 | Название | | ссылка_yt | ссылка_vk)

Данные хранятся в streams.json рядом с этим файлом.
"""

import calendar
import json
import os
from datetime import date

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------------------------------------------------------------------------
# Настройки (задаются через переменные окружения на Bothost)
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# ID админов через запятую, например "123456789,987654321"
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
}

if not BOT_TOKEN:
    raise SystemExit("Задайте переменную окружения BOT_TOKEN")

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "streams.json")

MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


# ---------------------------------------------------------------------------
# Хранилище
# ---------------------------------------------------------------------------
def load_streams() -> dict:
    """Читает streams.json → {'2026-08-10': {...}, ...}"""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_streams(streams: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(streams, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Календарь
# ---------------------------------------------------------------------------
def build_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    streams = load_streams()
    kb = InlineKeyboardMarkup(row_width=7)

    # Заголовок «Август 2026»
    kb.row(InlineKeyboardButton(
        f"{MONTHS_RU[month]} {year}", callback_data="ignore"))

    # Дни недели
    kb.row(*[InlineKeyboardButton(d, callback_data="ignore") for d in WEEKDAYS_RU])

    today = date.today()
    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
                continue
            key = f"{year:04d}-{month:02d}-{day:02d}"
            if key in streams:
                text = f"🎬{day}"
                cb = f"day:{key}"
            else:
                text = f"·{day}·" if (year, month, day) == (today.year, today.month, today.day) else str(day)
                cb = "empty"
            row.append(InlineKeyboardButton(text, callback_data=cb))
        kb.row(*row)

    # Навигация
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    kb.row(
        InlineKeyboardButton("◀️", callback_data=f"nav:{prev_y}-{prev_m}"),
        InlineKeyboardButton("Сегодня", callback_data=f"nav:{today.year}-{today.month}"),
        InlineKeyboardButton("▶️", callback_data=f"nav:{next_y}-{next_m}"),
    )
    return kb


def stream_card(key: str) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и кнопки карточки эфира."""
    s = load_streams().get(key, {})
    y, m, d = key.split("-")
    genitive = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
        7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    }
    pretty_date = f"{int(d)} {genitive[int(m)]} {y}"

    text = f"🎬 <b>{s.get('title', 'Эфир')}</b>\n📅 {pretty_date}"
    if s.get("description"):
        text += f"\n\n{s['description']}"

    kb = InlineKeyboardMarkup(row_width=2)
    buttons = []
    if s.get("youtube"):
        buttons.append(InlineKeyboardButton("▶️ YouTube", url=s["youtube"]))
    if s.get("vk"):
        buttons.append(InlineKeyboardButton("▶️ ВКонтакте", url=s["vk"]))
    if buttons:
        kb.row(*buttons)
    kb.row(InlineKeyboardButton("⬅️ К календарю", callback_data=f"nav:{y}-{int(m)}"))
    return text, kb


# ---------------------------------------------------------------------------
# Команды
# ---------------------------------------------------------------------------
@bot.message_handler(commands=["start", "calendar"])
def cmd_start(message):
    today = date.today()
    bot.send_message(
        message.chat.id,
        "📅 <b>Календарь эфиров</b>\n\nДаты с записями помечены 🎬 — нажмите, чтобы открыть ссылки.",
        reply_markup=build_calendar(today.year, today.month),
    )


@bot.message_handler(commands=["add"])
def cmd_add(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    raw = message.text.partition(" ")[2]
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 4:
        bot.reply_to(
            message,
            "Формат:\n<code>/add 2026-08-10 | Название | Описание | ссылка YouTube | ссылка VK</code>\n"
            "Описание можно оставить пустым (два | подряд).",
        )
        return
    # Если частей 4 — считаем, что описание пропущено
    if len(parts) == 4:
        d, title, yt, vk = parts
        desc = ""
    else:
        d, title, desc, yt, vk = parts[:5]

    try:
        y, m, dd = map(int, d.split("-"))
        date(y, m, dd)  # валидация
    except (ValueError, AttributeError):
        bot.reply_to(message, "Дата должна быть в формате <code>ГГГГ-ММ-ДД</code>, например 2026-08-10")
        return

    streams = load_streams()
    streams[f"{y:04d}-{m:02d}-{dd:02d}"] = {
        "title": title or "Эфир",
        "description": desc,
        "youtube": yt,
        "vk": vk,
    }
    save_streams(streams)
    bot.reply_to(message, f"✅ Эфир «{title}» на {d} сохранён.")


@bot.message_handler(commands=["del"])
def cmd_del(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    key = message.text.partition(" ")[2].strip()
    streams = load_streams()
    if key in streams:
        removed = streams.pop(key)
        save_streams(streams)
        bot.reply_to(message, f"🗑 Удалён эфир «{removed.get('title')}» ({key}).")
    else:
        bot.reply_to(message, "На эту дату эфира нет. Формат: <code>/del 2026-08-10</code>")


@bot.message_handler(commands=["list"])
def cmd_list(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    streams = load_streams()
    if not streams:
        bot.reply_to(message, "Пока нет ни одного эфира.")
        return
    lines = [f"• <code>{k}</code> — {v.get('title')}" for k, v in sorted(streams.items())]
    bot.reply_to(message, "📋 <b>Все эфиры:</b>\n" + "\n".join(lines))


@bot.message_handler(commands=["id"])
def cmd_id(message):
    """Помогает узнать свой Telegram ID, чтобы прописать его в ADMIN_IDS."""
    bot.reply_to(message, f"Ваш ID: <code>{message.from_user.id}</code>")


# ---------------------------------------------------------------------------
# Callback-кнопки
# ---------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    data = call.data

    if data == "ignore":
        bot.answer_callback_query(call.id)

    elif data == "empty":
        bot.answer_callback_query(call.id, "В этот день эфира не было 🙂")

    elif data.startswith("nav:"):
        y, m = map(int, data[4:].split("-"))
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                "📅 <b>Календарь эфиров</b>\n\nДаты с записями помечены 🎬 — нажмите, чтобы открыть ссылки.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=build_calendar(y, m),
            )
        except telebot.apihelper.ApiTelegramException:
            pass  # сообщение не изменилось — игнорируем

    elif data.startswith("day:"):
        key = data[4:]
        bot.answer_callback_query(call.id)
        text, kb = stream_card(key)
        try:
            bot.edit_message_text(
                text, call.message.chat.id, call.message.message_id, reply_markup=kb
            )
        except telebot.apihelper.ApiTelegramException:
            pass


if __name__ == "__main__":
    print("Бот запущен…")
    bot.infinity_polling(skip_pending=True)
