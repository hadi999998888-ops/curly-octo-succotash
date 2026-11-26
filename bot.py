import asyncio
import ast
import base64
import html
import io
import json
import logging
import operator
import os
import random
import re
import time
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urlparse

import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    BusinessConnection,
    BusinessMessagesDeleted,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# =====================================================================
# КОНФИГУРАЦИЯ БОТА
# =====================================================================
# Загружаем секреты из локального .env (файл не добавлять в публичный GitHub).
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN. Заполните .env или переменные окружения хостинга.")
DATA_DIR = Path(os.getenv("DATA_DIR", "."))
STORAGE_FILE = Path(os.getenv("STORAGE_FILE", str(DATA_DIR / "hestle_storage.json")))

# =====================================================================
# ЛОГИРОВАНИЕ
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Hestle.Exe")

# =====================================================================
# КОНСТАНТЫ И ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ
# =====================================================================
DEFAULT_AUTOREPLY_TEXT = (
    "Вижу ваше сообщение, но я сейчас не в сети. Подождите, пожалуйста."
)
DEFAULT_MUTE_NOTICE_TEXT = "🔇 Режим тишины активен. Сообщения временно удаляются."
DEFAULT_TROLL_PHRASES = [
    "Ты серьёзно сейчас это написал? Перечитай ещё раз.",
    "Мощный аргумент, жаль, что мимо сути.",
    "Попробуй сформулировать мысль чуть убедительнее.",
    "Звучит так, будто ты сам в это не до конца веришь.",
    "Интересная теория, продолжай наблюдение.",
]
DEFAULT_SPAM_INTERVAL = 1.2
MIN_SPAM_INTERVAL = 0.5
MAX_SPAM_INTERVAL = 10.0
MAX_SPAM_COUNT = 10

MORSE_MAP = {
    "А": ".-", "Б": "-...", "В": ".--", "Г": "--.", "Д": "-..", "Е": ".", "Ё": ".",
    "Ж": "...-", "З": "--..", "И": "..", "Й": ".---", "К": "-.-", "Л": ".-..",
    "М": "--", "Н": "-.", "О": "---", "П": ".--.", "Р": ".-.", "С": "...", "Т": "-",
    "У": "..-", "Ф": "..-.", "Х": "....", "Ц": "-.-.", "Ч": "---.", "Ш": "----",
    "Щ": "--.-", "Ъ": "--.--", "Ы": "-.--", "Ь": "-..-", "Э": "..-..", "Ю": "..--",
    "Я": ".-.-",
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "!": "-.-.--", "-": "-....-",
}
REVERSE_MORSE_MAP = {v: k for k, v in MORSE_MAP.items()}

EN_LAYOUT = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~"
RU_LAYOUT = "йцукенгшщзхъфывапролджэячсмитьбюёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁ"

LEET_MAP = str.maketrans({
    "а": "4", "А": "4", "a": "4", "A": "4",
    "е": "3", "Е": "3", "e": "3", "E": "3",
    "и": "1", "И": "1", "i": "1", "I": "1",
    "о": "0", "О": "0", "o": "0", "O": "0",
    "с": "5", "С": "5", "s": "5", "S": "5",
    "т": "7", "Т": "7", "t": "7", "T": "7",
    "в": "8", "В": "8", "b": "8", "B": "8",
    "з": "3", "З": "3",
})

KAWAII_FACES = [
    "(◕‿◕✿)", "(｡♥‿♥｡)", "(づ｡◕‿‿◕｡)づ", "(≧◡≦)", "(★^O^★)", "(*^▽^*)", "(⁄ ⁄•⁄ω⁄•⁄ ⁄)"
]

EIGHT_BALL_ANSWERS = [
    "Бесспорно.",
    "Предрешено.",
    "Никаких сомнений.",
    "Определённо да.",
    "Можешь быть уверен в этом.",
    "Мне кажется — «да».",
    "Вероятнее всего.",
    "Хорошие перспективы.",
    "Знаки говорят — «да».",
    "Пока не ясно, попробуй снова.",
    "Спроси позже.",
    "Лучше не рассказывать.",
    "Сейчас нельзя предсказать.",
    "Сконцентрируйся и спроси опять.",
    "Даже не думай.",
    "Мой ответ — «нет».",
    "По моим данным — «нет».",
    "Перспективы не очень хорошие.",
    "Весьма сомнительно.",
]

TRUTH_LIST = [
    "Какой самый неловкий поступок ты совершал в переписке?",
    "Кому из списка контактов ты бы позвонил в 3 часа ночи?",
    "О чём ты чаще всего молчишь в диалогах?",
    "Какая твоя самая странная привычка?",
    "Что бы ты изменил в сегодняшнем дне, если бы мог?",
]

DARE_LIST = [
    "Отправь голосовое сообщение с комплиментом собеседнику.",
    "Поставь на 10 минут забавный статус в профиль.",
    "Напиши следующее сообщение только заглавными буквами.",
    "Отправь случайный стикер из первого набора.",
    "Опиши собеседника тремя словами без использования прилагательных.",
]

BUILTIN_RP_ACTIONS: Dict[str, Tuple[str, str]] = {
    ".обнять": ("🤗", "крепко обнял(-а)"),
    ".поцеловать": ("💋", "нежно поцеловал(-а)"),
    ".ударить": ("👊", "нанес(-ла) удар"),
    ".укусить": ("🦷", "укусил(-а)"),
    ".погладить": ("🫳", "ласково погладил(-а)"),
    ".лизнуть": ("👅", "лизнул(-а)"),
    ".пнуть": ("🦶", "пнул(-а)"),
    ".шлепнуть": ("👋", "шлёпнул(-а)"),
    ".пожать": ("🤝", "крепко пожал(-а) руку"),
    ".удушить": ("🫂", "разыграл(-а) захват"),
    ".подкормить": ("🍕", "подкормил(-а)"),
    ".напоить": ("🥤", "напоил(-а)"),
    ".укрыть": ("🛏", "заботливо укрыл(-а)"),
    ".поздравить": ("🎉", "торжественно поздравил(-а)"),
    ".успокоить": ("🌿", "успокоил(-а)"),
    ".расцеловать": ("💞", "расцеловал(-а)"),
    ".задушить": ("🎭", "драматично придушил(-а)"),
    ".поприветствовать": ("👋", "тепло поприветствовал(-а)"),
    ".попрощаться": ("🫡", "попрощался(-ась) с"),
    ".испугать": ("👻", "внезапно испугал(-а)"),
}


# =====================================================================
# БЕЗОПАСНЫЙ КАЛЬКУЛЯТОР (AST)
# =====================================================================
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval_math(expression: str) -> float:
    cleaned = (
        expression.replace(",", ".")
        .replace("^", "**")
        .replace("×", "*")
        .replace("÷", "/")
    )
    if len(cleaned) > 100:
        raise ValueError("Слишком длинное выражение")
    if not re.fullmatch(r"[0-9+\-*/().%\s]+", cleaned):
        raise ValueError("Недопустимые символы в выражении")

    node = ast.parse(cleaned, mode="eval").body

    def _eval(n: ast.AST) -> float:
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in SAFE_OPERATORS:
            left = _eval(n.left)
            right = _eval(n.right)
            if isinstance(n.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Слишком большая степень")
            if isinstance(n.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
                raise ZeroDivisionError("Деление на ноль")
            return SAFE_OPERATORS[type(n.op)](left, right)
        if isinstance(n, ast.UnaryOp) and type(n.op) in SAFE_OPERATORS:
            return SAFE_OPERATORS[type(n.op)](_eval(n.operand))
        raise ValueError("Некорректная математическая операция")

    return _eval(node)


# =====================================================================
# ХРАНИЛИЩЕ ДАННЫХ (ИЗОЛИРОВАННОЕ ПО ПОЛЬЗОВАТЕЛЯМ И ПОДКЛЮЧЕНИЯМ)
# =====================================================================
class StorageManager:
    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self._lock = asyncio.Lock()
        self.data: Dict[str, Any] = {
            "connections": {},       # business_connection_id -> metadata
            "user_connections": {},  # str(owner_user_id) -> business_connection_id
            "settings": {},          # business_connection_id -> user settings
            "chat_states": {},       # f"{business_connection_id}:{chat_id}" -> chat flags & stats
        }
        self._load_sync()

    def _load_sync(self) -> None:
        if not self.filepath.exists():
            self._save_sync()
            return
        try:
            raw = self.filepath.read_text(encoding="utf-8")
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                for key in self.data:
                    if isinstance(loaded.get(key), dict):
                        self.data[key] = loaded[key]
            logger.info("Хранилище успешно загружено из %s", self.filepath)
        except Exception as exc:
            logger.error("Ошибка загрузки хранилища: %s. Создаётся чистая база.", exc)
            self._save_sync()

    def _save_sync(self) -> None:
        tmp_path = self.filepath.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, self.filepath)

    async def save(self) -> None:
        async with self._lock:
            self._save_sync()

    def default_settings(self) -> Dict[str, Any]:
        return {
            "autoreply_text": DEFAULT_AUTOREPLY_TEXT,
            "mute_notice_text": DEFAULT_MUTE_NOTICE_TEXT,
            "spam_interval": DEFAULT_SPAM_INTERVAL,
            "autoreply_one_shot": True,
            "afk_active": False,
            "afk_reason": "",
            "afk_since": 0,
            "bold_mode": False,
            "kawaii_mode": False,
            "antimute_mode": False,
            "troll_phrases": list(DEFAULT_TROLL_PHRASES),
            "troll_delay": 0.5,
            "replaces": {},
            "custom_rp": {},
            "feature_mute": True,
            "feature_autoreply": True,
            "feature_spam": True,
            "feature_snos": True,
            "feature_tools": True,
        }

    def get_settings(self, connection_id: str) -> Dict[str, Any]:
        base = self.default_settings()
        saved = self.data["settings"].get(connection_id, {})
        base.update(saved)
        self.data["settings"][connection_id] = base
        return base

    def get_chat_state(self, connection_id: str, chat_id: int) -> Dict[str, Any]:
        key = f"{connection_id}:{chat_id}"
        if key not in self.data["chat_states"]:
            self.data["chat_states"][key] = {
                "muted": False,
                "autoreply": False,
                "troll": False,
                "wsag": False,
                "burn_chat_sec": 0,
                "streak_count": 0,
                "streak_last_day": "",
                "warns": {},
                "msg_ids": [],
                "stats": {
                    "owner_msgs": 0,
                    "peer_msgs": 0,
                    "hours": {},
                    "words": {},
                },
            }
        state = self.data["chat_states"][key]
        state.setdefault("troll", False)
        state.setdefault("wsag", False)
        state.setdefault("burn_chat_sec", 0)
        state.setdefault("streak_count", 0)
        state.setdefault("streak_last_day", "")
        state.setdefault("warns", {})
        state.setdefault("msg_ids", [])
        state.setdefault("stats", {"owner_msgs": 0, "peer_msgs": 0, "hours": {}, "words": {}})
        return state

    async def register_connection(self, bc: BusinessConnection) -> None:
        async with self._lock:
            owner_id = bc.user.id
            owner_key = str(owner_id)
            old_conn_id = self.data["user_connections"].get(owner_key)

            if old_conn_id and old_conn_id != bc.id:
                if old_conn_id in self.data["settings"] and bc.id not in self.data["settings"]:
                    self.data["settings"][bc.id] = dict(self.data["settings"][old_conn_id])
                if old_conn_id in self.data["connections"]:
                    self.data["connections"][old_conn_id]["is_enabled"] = False

            rights_dict = {}
            if bc.rights:
                rights_dict = {
                    "can_reply": bool(getattr(bc.rights, "can_reply", False)),
                    "can_delete_outgoing_messages": bool(
                        getattr(
                            bc.rights,
                            "can_delete_outgoing_messages",
                            getattr(bc.rights, "can_delete_sent_messages", False),
                        )
                    ),
                    "can_delete_all_messages": bool(
                        getattr(bc.rights, "can_delete_all_messages", False)
                    ),
                    "can_read_messages": bool(getattr(bc.rights, "can_read_messages", False)),
                }

            self.data["connections"][bc.id] = {
                "connection_id": bc.id,
                "owner_id": owner_id,
                "owner_name": bc.user.full_name,
                "owner_username": bc.user.username or "",
                "user_chat_id": bc.user_chat_id,
                "is_enabled": bool(bc.is_enabled),
                "rights": rights_dict,
                "updated_at": int(time.time()),
            }

            if bc.is_enabled:
                self.data["user_connections"][owner_key] = bc.id
            elif self.data["user_connections"].get(owner_key) == bc.id:
                del self.data["user_connections"][owner_key]

            self.get_settings(bc.id)
            self._save_sync()

    def get_connection(self, connection_id: str) -> Optional[Dict[str, Any]]:
        return self.data["connections"].get(connection_id)

    def get_user_active_connection(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn_id = self.data["user_connections"].get(str(user_id))
        if not conn_id:
            return None
        conn = self.data["connections"].get(conn_id)
        if not conn or not conn.get("is_enabled"):
            return None
        return conn


storage = StorageManager(STORAGE_FILE)

# =====================================================================
# ЗАЩИТА ОТ ДУБЛИРОВАНИЯ UPDATES И АКТИВНЫЕ ЗАДАЧИ
# =====================================================================
PROCESSED_UPDATES: Set[int] = set()
PROCESSED_ORDER: deque[int] = deque(maxlen=5000)

ACTIVE_SPAM_TASKS: Dict[Tuple[str, int], asyncio.Task] = {}
SENT_OWNER_MESSAGES: Dict[Tuple[str, int, int], str] = {}
MINESWEEPER_GAMES: Dict[str, Dict[str, Any]] = {}
TTT_GAMES: Dict[str, Dict[str, Any]] = {}


def is_duplicate_update(update_id: int) -> bool:
    if update_id in PROCESSED_UPDATES:
        return True
    if len(PROCESSED_ORDER) == PROCESSED_ORDER.maxlen:
        oldest = PROCESSED_ORDER.popleft()
        PROCESSED_UPDATES.discard(oldest)
    PROCESSED_ORDER.append(update_id)
    PROCESSED_UPDATES.add(update_id)
    return False


# =====================================================================
# FSM СОСТОЯНИЯ ДЛЯ МЕНЮ НАСТРОЕК
# =====================================================================
class SettingsFSM(StatesGroup):
    waiting_autoreply_text = State()
    waiting_mute_text = State()
    waiting_spam_interval = State()
    waiting_troll_phrase = State()


# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ТЕКСТА И ИНТЕРФЕЙСА
# =====================================================================
def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def format_duration(seconds: int) -> str:
    mins, secs = divmod(max(0, int(seconds)), 60)
    hours, mins = divmod(mins, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ч.")
    if mins:
        parts.append(f"{mins} мин.")
    if secs or not parts:
        parts.append(f"{secs} сек.")
    return " ".join(parts)


def parse_time_arg(raw: str) -> Optional[int]:
    """Парсит 30s, 5m, 1h или просто секунды."""
    raw = raw.strip().lower()
    m = re.fullmatch(r"(\d+)\s*([smhсчм]?)", raw)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2)
    if unit in ("m", "м"):
        return val * 60
    if unit in ("h", "ч"):
        return val * 3600
    return val


def parse_schedule_time(raw: str) -> Optional[int]:
    """Парсит 30m/45s/2h или время формата HH:MM (МСК UTC+3)."""
    sec = parse_time_arg(raw)
    if sec is not None and sec > 0:
        return sec
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", raw.strip())
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            tz_msk = timezone(timedelta(hours=3))
            now = datetime.now(tz_msk)
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return int((target - now).total_seconds())
    return None


def estimate_reg_date(user_id: int) -> str:
    """Примерная оценка даты регистрации по диапазону Telegram ID."""
    anchors = [
        (100_000_000, "2013–2015"),
        (300_000_000, "2016"),
        (500_000_000, "2017"),
        (750_000_000, "2018"),
        (1_050_000_000, "2019"),
        (1_450_000_000, "2020"),
        (2_100_000_000, "2021"),
        (5_300_000_000, "2022"),
        (6_200_000_000, "2023"),
        (7_100_000_000, "2024"),
        (8_000_000_000, "2025"),
    ]
    for limit, year_str in anchors:
        if user_id < limit:
            return year_str
    return "2026"


def switch_keyboard_layout(text: str) -> str:
    has_cyr = bool(re.search(r"[а-яА-ЯёЁ]", text))
    src = RU_LAYOUT if has_cyr else EN_LAYOUT
    dst = EN_LAYOUT if has_cyr else RU_LAYOUT
    table = str.maketrans(src, dst)
    return text.translate(table)


def to_olbanian(text: str) -> str:
    rules = [
        (r"привет", "превед"),
        (r"дела", "дила"),
        (r"красавчик", "красавчег"),
        (r"животное", "жывотное"),
        (r"автор", "аффтар"),
        (r"огонь", "агонь"),
        (r"ться\b", "цца"),
        (r"тся\b", "цца"),
        (r"ого\b", "ова"),
        (r"его\b", "ева"),
        (r"жи", "жы"),
        (r"ши", "шы"),
        (r"ча", "чя"),
        (r"ща", "щя"),
    ]
    res = text
    for pat, rep in rules:
        res = re.sub(pat, rep, res, flags=re.IGNORECASE)
    return res


def text_to_morse(text: str) -> str:
    words = []
    for word in text.upper().split():
        letters = [MORSE_MAP[ch] for ch in word if ch in MORSE_MAP]
        if letters:
            words.append(" ".join(letters))
    return " / ".join(words)


def morse_to_text(morse: str) -> str:
    words = []
    for word in morse.strip().split("/"):
        chars = [REVERSE_MORSE_MAP.get(code, "?") for code in word.strip().split()]
        if chars:
            words.append("".join(chars))
    return " ".join(words)


def build_settings_text(conn: Dict[str, Any], settings: Dict[str, Any]) -> str:
    mode_label = (
        "Один ответ и автоотключение"
        if settings["autoreply_one_shot"]
        else "Постоянный (на каждое входящее)"
    )
    return (
        "⚙️ <b>Hestle.Exe — Панель настроек</b>\n\n"
        f"👤 <b>Аккаунт:</b> {escape_html(conn['owner_name'])}\n"
        f"🔗 <b>Подключение:</b> <code>{escape_html(conn['connection_id'][:14])}…</code>\n\n"
        "<b>Параметры модулей:</b>\n"
        f"• 🔒 Мут: {'<b>Вкл</b>' if settings['feature_mute'] else 'Выкл'}\n"
        f"• 📨 Автоответчик: {'<b>Вкл</b>' if settings['feature_autoreply'] else 'Выкл'}\n"
        f"• 📤 Рассылка (.spam): {'<b>Вкл</b>' if settings['feature_spam'] else 'Выкл'}\n"
        f"• 📋 Отчётные модули: {'<b>Вкл</b>' if settings['feature_snos'] else 'Выкл'}\n"
        f"• 🛠 Утилиты и ИИ: {'<b>Вкл</b>' if settings['feature_tools'] else 'Выкл'}\n\n"
        f"⏱ <b>Интервал .spam:</b> <code>{settings['spam_interval']} сек.</code>\n"
        f"🔄 <b>Режим автоответчика:</b> {mode_label}\n"
        f"🛡 <b>Анти-мут (.nomute):</b> {'<b>Активен</b>' if settings['antimute_mode'] else 'Выкл'}\n"
        f"🅱️ <b>Жирный шрифт (.bold):</b> {'<b>Активен</b>' if settings['bold_mode'] else 'Выкл'}\n"
        f"🌸 <b>Каваи-режим (.kawaii):</b> {'<b>Активен</b>' if settings['kawaii_mode'] else 'Выкл'}\n\n"
        f"💬 <b>Текст автоответчика:</b>\n<i>«{escape_html(settings['autoreply_text'])}»</i>\n\n"
        f"🔇 <b>Уведомление при .mute:</b>\n<i>«{escape_html(settings['mute_notice_text'])}»</i>"
    )


def build_settings_keyboard(settings: Dict[str, Any]) -> InlineKeyboardMarkup:
    def flag(val: bool) -> str:
        return "🟢" if val else "⚪️"

    one_shot_label = "1 ответ" if settings["autoreply_one_shot"] else "Постоянно"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Текст автоответчика",
                    callback_data="cfg:edit_autoreply",
                ),
                InlineKeyboardButton(
                    text="✏️ Текст мута",
                    callback_data="cfg:edit_mute",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"⏱ Интервал: {settings['spam_interval']}с",
                    callback_data="cfg:edit_interval",
                ),
                InlineKeyboardButton(
                    text=f"🔄 Режим: {one_shot_label}",
                    callback_data="cfg:toggle_oneshot",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💬 Фраза для .troll",
                    callback_data="cfg:edit_troll",
                ),
                InlineKeyboardButton(
                    text=f"{flag(settings['antimute_mode'])} Анти-мут",
                    callback_data="cfg:toggle:antimute_mode",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{flag(settings['feature_mute'])} Мут",
                    callback_data="cfg:toggle:feature_mute",
                ),
                InlineKeyboardButton(
                    text=f"{flag(settings['feature_autoreply'])} Автоответчик",
                    callback_data="cfg:toggle:feature_autoreply",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{flag(settings['feature_spam'])} Рассылка",
                    callback_data="cfg:toggle:feature_spam",
                ),
                InlineKeyboardButton(
                    text=f"{flag(settings['feature_snos'])} Отчёты",
                    callback_data="cfg:toggle:feature_snos",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{flag(settings['feature_tools'])} Утилиты и ИИ",
                    callback_data="cfg:toggle:feature_tools",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="♻️ Сбросить по умолчанию",
                    callback_data="cfg:reset",
                ),
            ],
        ]
    )


def format_help_text() -> str:
    return (
        "⚡ <b>Hestle.Exe — Справочник команд</b>\n\n"
        "<b>🔒 Модерация и защита чата</b>\n"
        "• <code>.mute</code> / <code>.unmute</code> — удаление входящих в чате\n"
        "• <code>.nomute</code> — авто-восстановление ваших удалённых сообщений\n"
        "• <code>.wsag</code> / <code>.unwsag</code> — автоудаление стикеров и GIF\n"
        "• <code>.burn [30s] [текст]</code> — самоуничтожающееся сообщение\n"
        "• <code>.bchat [2m]</code> / <code>.unbchat</code> — автоудаление новых сообщений\n"
        "• <code>.panic [N]</code> / <code>.del [N]</code> — очистка последних сообщений\n"
        "• <code>.pin</code> / <code>.unpin</code> — закрепить / открепить сообщение\n"
        "• <code>.warn</code> — выдать предупреждение собеседнику\n\n"
        "<b>📨 Автоответчик и статусы</b>\n"
        "• <code>.Avtootvet</code> / <code>.noavtootvet</code> — автоответчик в чате\n"
        "• <code>.auto [текст]</code> / <code>.unauto</code> — автоответ с заданным текстом\n"
        "• <code>.afk [причина]</code> — режим отсутствия (снимается при вашем сообщении)\n"
        "• <code>.streak</code> / <code>.unstreak</code> — серия дней общения\n\n"
        "<b>📋 Диагностика и аналитика</b>\n"
        "• <code>.snos</code> / <code>.dox</code> / <code>.logger</code> / <code>.osint</code> / <code>.krek</code> / <code>.getlink</code> / <code>.getweb</code> — пошаговые отчёты и генерация ссылок\n"
        "• <code>.info</code> / <code>.get</code> / <code>.id</code> — профиль и ID собеседника\n"
        "• <code>.stat</code> — статистика активности диалога\n"
        "• <code>.ping</code> — замер отклика API\n\n"
        "<b>🧠 Аналитика текста и перевод</b>\n"
        "• <code>.ai [вопрос]</code> / <code>.dialog</code> / <code>.pms</code> — разбор и ответы\n"
        "• <code>.translate</code> / <code>.tl</code> — переводчик сообщений\n"
        "• <code>.sw</code> — смена раскладки клавиатуры\n"
        "• <code>.morse</code> / <code>.leet</code> / <code>.dumb</code> / <code>.pqt</code>\n\n"
        "<b>📤 Рассылка, троллинг и анимации</b>\n"
        "• <code>.spam [1-10] [текст]</code> / <code>.nospam</code> (<code>.stopspam</code>)\n"
        "• <code>.troll</code> / <code>.untroll</code> / <code>.tset [текст]</code>\n"
        "• <code>.anim [1-3] [текст]</code>, <code>.print</code>, <code>.magic</code>, <code>.matrix</code>, <code>.heart</code>, <code>.love</code>, <code>.fire</code>, <code>.boom</code>, <code>.load</code>, <code>.police</code>, <code>.clown</code>, <code>.stair</code>, <code>.haha</code>\n"
        "• <code>.bold</code> / <code>.kawaii</code> — автоформатирование ваших сообщений\n\n"
        "<b>🛠 Утилиты, финансы и медиа</b>\n"
        "• <code>.calc [выражение]</code> — калькулятор\n"
        "• <code>.timer [сек] [заметка]</code>, <code>.remind [30m] [текст]</code>, <code>.remindf [18:30] [текст]</code>\n"
        "• <code>.weather [город]</code>, <code>.rates</code>, <code>.iss</code>, <code>.geo [адрес]</code>\n"
        "• <code>.qr [текст]</code>, <code>.short [url]</code>, <code>.unshort [url]</code>, <code>.link [текст]</code>\n"
        "• <code>.fakec [сумма]</code>, <code>.fakel [сумма]</code> — карточки чеков\n\n"
        "<b>🎮 Мини-игры и RP-действия</b>\n"
        "• <code>.saper</code>, <code>.ttt</code>, <code>.rps</code>, <code>.rec</code>, <code>.ball</code> (<code>.8ball</code>), <code>.coin</code>, <code>.roll [a] [b]</code>, <code>.tod</code>, <code>.mog</code>\n"
        "• <code>.addrp .команда действие</code>, <code>.myrp</code>, <code>.delrp .команда</code>\n"
        "• <code>.обнять</code>, <code>.поцеловать</code>, <code>.пожать</code>, <code>.укусить</code>, <code>.погладить</code> и ещё 15 RP-команд"
    )


async def safe_delete_business_message(
    bot: Bot,
    connection_id: str,
    chat_id: int,
    message_id: int,
) -> bool:
    try:
        await bot.delete_business_messages(
            business_connection_id=connection_id,
            message_ids=[message_id],
        )
        return True
    except TelegramAPIError as exc:
        logger.debug(
            "Не удалось удалить Business-сообщение (conn=%s, chat=%s, msg=%s): %s",
            connection_id,
            chat_id,
            message_id,
            exc,
        )
        return False


async def safe_edit_business_message(
    bot: Bot,
    connection_id: str,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    try:
        await bot.edit_message_text(
            business_connection_id=connection_id,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return True
        logger.debug("Ошибка редактирования Business-сообщения: %s", exc)
        return False
    except TelegramAPIError as exc:
        logger.debug("Telegram API ошибка при редактировании: %s", exc)
        return False


async def send_biz(
    bot: Bot,
    connection_id: str,
    chat_id: int,
    text: str,
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> Optional[Message]:
    try:
        msg = await bot.send_message(
            business_connection_id=connection_id,
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
        )
        state = storage.get_chat_state(connection_id, chat_id)
        state["msg_ids"].append(msg.message_id)
        if len(state["msg_ids"]) > 200:
            state["msg_ids"] = state["msg_ids"][-200:]
        return msg
    except TelegramAPIError as exc:
        logger.warning("Ошибка отправки Business-сообщения (chat=%s): %s", chat_id, exc)
        return None


# =====================================================================
# АНИМИРОВАННЫЕ ОТЧЁТЫ И ИНТЕРАКТИВНЫЕ ВОРКЕРЫ
# =====================================================================
async def run_animated_report(
    bot: Bot,
    connection_id: str,
    chat_id: int,
    title: str,
    steps: List[str],
    final_body: str,
    reply_to_msg: Optional[Message] = None,
    target_override: Optional[str] = None,
) -> None:
    target_block = ""
    reply_id = None
    if target_override:
        target_block = f"\n🎯 <b>Цель:</b> <code>{escape_html(target_override)}</code>\n"
    elif reply_to_msg:
        reply_id = reply_to_msg.message_id
        author = reply_to_msg.from_user.full_name if reply_to_msg.from_user else "Собеседник"
        uid = reply_to_msg.from_user.id if reply_to_msg.from_user else "—"
        snippet = (reply_to_msg.text or reply_to_msg.caption or "[Медиа-фложение]").strip()
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        target_block = (
            f"\n👤 <b>Объект:</b> {escape_html(author)} (<code>{uid}</code>)\n"
            f"💬 <b>Контекст:</b> <i>«{escape_html(snippet)}»</i>\n"
        )

    bars = [
        "<code>[▓░░░░░░░░░] 15%</code>",
        "<code>[▓▓▓▓░░░░░░] 45%</code>",
        "<code>[▓▓▓▓▓▓▓░░░] 80%</code>",
    ]

    first_text = (
        f"📋 <b>Hestle.Exe — {escape_html(title)}</b>\n"
        f"{bars[0]}\n\n"
        f"• {escape_html(steps[0])}"
        f"{target_block}"
    )
    sent = await send_biz(bot, connection_id, chat_id, first_text, reply_to_message_id=reply_id)
    if not sent:
        return

    for idx in range(1, min(len(steps), len(bars))):
        await asyncio.sleep(0.85)
        frame = (
            f"📋 <b>Hestle.Exe — {escape_html(title)}</b>\n"
            f"{bars[idx]}\n\n"
            f"• {escape_html(steps[idx])}"
            f"{target_block}"
        )
        ok = await safe_edit_business_message(bot, connection_id, chat_id, sent.message_id, frame)
        if not ok:
            return

    await asyncio.sleep(0.85)
    final_text = (
        f"📋 <b>Hestle.Exe — {escape_html(title)}</b>\n"
        "<code>[▓▓▓▓▓▓▓▓▓▓] 100%</code>\n"
        f"{target_block}\n"
        f"{final_body}"
    )
    await safe_edit_business_message(bot, connection_id, chat_id, sent.message_id, final_text)


async def run_text_frames_animation(
    bot: Bot,
    connection_id: str,
    chat_id: int,
    frames: List[str],
    delay: float = 0.65,
) -> None:
    if not frames:
        return
    sent = await send_biz(bot, connection_id, chat_id, frames[0])
    if not sent:
        return
    for frame in frames[1:]:
        await asyncio.sleep(delay)
        ok = await safe_edit_business_message(bot, connection_id, chat_id, sent.message_id, frame)
        if not ok:
            break


async def run_spam_worker(
    bot: Bot,
    connection_id: str,
    chat_id: int,
    count: int,
    text: str,
    interval: float,
) -> None:
    key = (connection_id, chat_id)
    try:
        for idx in range(count):
            await send_biz(bot, connection_id, chat_id, text)
            if idx < count - 1:
                await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Рассылка .spam остановлена (conn=%s, chat=%s)", connection_id, chat_id)
        raise
    finally:
        if ACTIVE_SPAM_TASKS.get(key) is asyncio.current_task():
            ACTIVE_SPAM_TASKS.pop(key, None)


async def run_delayed_delete(
    bot: Bot,
    connection_id: str,
    chat_id: int,
    message_id: int,
    delay_sec: int,
) -> None:
    await asyncio.sleep(delay_sec)
    await safe_delete_business_message(bot, connection_id, chat_id, message_id)


async def run_timer_worker(
    bot: Bot,
    connection_id: str,
    chat_id: int,
    seconds: int,
    label: str,
    to_owner_pm: bool = False,
    owner_chat_id: Optional[int] = None,
) -> None:
    await asyncio.sleep(seconds)
    note = f"\n📝 Заметка: <i>{escape_html(label)}</i>" if label else ""
    body = (
        "⏰ <b>Hestle.Exe — Напоминание</b>\n\n"
        f"Прошло: <b>{format_duration(seconds)}</b>{note}"
    )
    if to_owner_pm and owner_chat_id:
        try:
            await bot.send_message(chat_id=owner_chat_id, text=body)
        except TelegramAPIError as exc:
            logger.warning("Не удалось отправить личное напоминание: %s", exc)
    else:
        await send_biz(bot, connection_id, chat_id, body)


# =====================================================================
# ВНЕШНИЕ ОТКРЫТЫЕ API БЕЗ КЛЮЧЕЙ И ТОКЕНОВ
# =====================================================================
async def fetch_json(url: str, timeout: int = 8) -> Optional[Any]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
    except Exception as exc:
        logger.debug("Ошибка HTTP запроса (%s): %s", url, exc)
    return None


async def fetch_bytes(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as exc:
        logger.debug("Ошибка загрузки байтов (%s): %s", url, exc)
    return None


async def resolve_redirect_chain(url: str) -> List[str]:
    chain = [url]
    current = url
    try:
        async with aiohttp.ClientSession() as session:
            for _ in range(8):
                async with session.get(
                    current,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=6),
                ) as resp:
                    loc = resp.headers.get("Location")
                    if resp.status in (301, 302, 303, 307, 308) and loc:
                        if loc.startswith("/"):
                            parsed = urlparse(current)
                            loc = f"{parsed.scheme}://{parsed.netloc}{loc}"
                        chain.append(loc)
                        current = loc
                    else:
                        break
    except Exception:
        pass
    return chain


# =====================================================================
# МИНИ-ИГРЫ (САПЁР И КРЕСТИКИ-НОЛИКИ)
# =====================================================================
def create_minesweeper_board(size: int = 5, mines: int = 5) -> Dict[str, Any]:
    game_id = f"{random.randint(10000, 99999)}"
    mine_positions = set(random.sample(range(size * size), mines))
    return {
        "id": game_id,
        "size": size,
        "mines": mine_positions,
        "revealed": set(),
        "flags": set(),
        "flag_mode": False,
        "over": False,
        "won": False,
    }


def render_minesweeper_kb(game: Dict[str, Any]) -> InlineKeyboardMarkup:
    size = game["size"]
    rows = []
    for r in range(size):
        row_btns = []
        for c in range(size):
            idx = r * size + c
            if idx in game["revealed"]:
                if idx in game["mines"]:
                    label = "💥"
                else:
                    cnt = 0
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            nr, nc = r + dr, c + dc
                            if 0 <= nr < size and 0 <= nc < size:
                                if (nr * size + nc) in game["mines"]:
                                    cnt += 1
                    label = str(cnt) if cnt > 0 else "·"
            elif idx in game["flags"]:
                label = "🚩"
            elif game["over"] and idx in game["mines"]:
                label = "💣"
            else:
                label = "⬜️"
            row_btns.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"ms:{game['id']}:{idx}",
                )
            )
        rows.append(row_btns)

    mode_text = "Режим: 🚩 Флаг" if game["flag_mode"] else "Режим: ⛏ Копать"
    rows.append([
        InlineKeyboardButton(text=mode_text, callback_data=f"ms:{game['id']}:mode")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_ttt_kb(game: Dict[str, Any]) -> InlineKeyboardMarkup:
    board = game["board"]
    rows = []
    for r in range(3):
        btns = []
        for c in range(3):
            idx = r * 3 + c
            cell = board[idx] or "·"
            btns.append(
                InlineKeyboardButton(text=cell, callback_data=f"ttt:{game['id']}:{idx}")
            )
        rows.append(btns)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def check_ttt_winner(board: List[str]) -> Optional[str]:
    wins = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    ]
    for a, b, c in wins:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "DRAW"
    return None


# =====================================================================
# РОУТЕРЫ И ОБРАБОТЧИКИ
# =====================================================================
router = Router(name="hestle_main")


# --- 1. ОБРАБОТКА ПОДКЛЮЧЕНИЙ TELEGRAM BUSINESS ---
@router.business_connection()
async def on_business_connection(bc: BusinessConnection, bot: Bot) -> None:
    logger.info(
        "Обновление BusinessConnection: id=%s | user_id=%s (%s) | enabled=%s",
        bc.id,
        bc.user.id,
        bc.user.full_name,
        bc.is_enabled,
    )
    await storage.register_connection(bc)

    if bc.is_enabled:
        rights = bc.rights
        can_reply = bool(getattr(rights, "can_reply", False)) if rights else False
        can_del_all = bool(getattr(rights, "can_delete_all_messages", False)) if rights else False
        can_del_out = (
            bool(
                getattr(
                    rights,
                    "can_delete_outgoing_messages",
                    getattr(rights, "can_delete_sent_messages", False),
                )
            )
            if rights
            else False
        )

        warning_lines = []
        if not can_reply:
            warning_lines.append("⚠️ Отключено право <b>отправки сообщений</b> — команды не смогут отвечать.")
        if not can_del_all:
            warning_lines.append("⚠️ Отключено право <b>удаления всех сообщений</b> — функция <code>.mute</code> не сможет удалять входящие.")
        if not can_del_out:
            warning_lines.append("ℹ️ Отключено право <b>удаления исходящих</b> — командные триггеры останутся в чате.")

        extra_info = (
            "\n\n" + "\n".join(warning_lines)
            if warning_lines
            else "\n\n✅ Все необходимые права предоставлены."
        )

        try:
            await bot.send_message(
                chat_id=bc.user_chat_id,
                text=(
                    "⚡ <b>Hestle.Exe подключён</b>\n\n"
                    f"Аккаунт <b>{escape_html(bc.user.full_name)}</b> успешно синхронизирован.\n"
                    "Настройки изолированы и закреплены только за вашим профилем."
                    f"{extra_info}\n\n"
                    "Откройте /settings для настройки или напишите <code>.help</code> в любом чате."
                ),
            )
        except TelegramAPIError as exc:
            logger.warning("Не удалось отправить приветствие владельцу %s: %s", bc.user.id, exc)
    else:
        to_cancel = [key for key in ACTIVE_SPAM_TASKS if key[0] == bc.id]
        for key in to_cancel:
            task = ACTIVE_SPAM_TASKS.pop(key, None)
            if task and not task.done():
                task.cancel()

        try:
            await bot.send_message(
                chat_id=bc.user_chat_id,
                text=(
                    "🔌 <b>Hestle.Exe отключён</b>\n\n"
                    "Интеграция с Telegram Business приостановлена. "
                    "Ваши настройки сохранены и восстановятся при повторном подключении."
                ),
            )
        except TelegramAPIError:
            pass


# --- 2. ОБРАБОТКА ЛИЧНЫХ СООБЩЕНИЙ БОТУ (/start, /status, /settings, /help) ---
@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return
    conn = storage.get_user_active_connection(message.from_user.id)
    status_badge = "🟢 Активно" if conn else "⚪️ Не подключено"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings"),
                InlineKeyboardButton(text="📡 Статус", callback_data="menu:status"),
            ],
            [
                InlineKeyboardButton(text="📖 Список команд", callback_data="menu:help"),
            ],
        ]
    )

    await message.answer(
        "⚡ <b>Hestle.Exe</b>\n"
        "<i>Персональный ассистент для Telegram Business</i>\n\n"
        f"Статус подключения: <b>{status_badge}</b>\n\n"
        "<b>Как подключить за 30 секунд:</b>\n"
        "1. Откройте <b>Настройки Telegram → Telegram Business → Чат-боты</b>.\n"
        "2. Укажите имя этого бота и выберите его.\n"
        "3. Выдайте разрешения на управление сообщениями.\n\n"
        "После подключения используйте команды с точкой (<code>.help</code>, <code>.mute</code>, <code>.Avtootvet</code>) прямо в ваших диалогах.",
        reply_markup=kb,
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not message.from_user:
        return
    conn = storage.get_user_active_connection(message.from_user.id)
    if not conn:
        await message.answer(
            "📡 <b>Статус подключения — Hestle.Exe</b>\n\n"
            "Статус: ⚪️ <b>Не подключено</b>\n\n"
            "Перейдите в <i>Настройки Telegram → Telegram Business → Чат-боты</i> и добавьте этого бота."
        )
        return

    rights = conn.get("rights", {})
    r_reply = "✅" if rights.get("can_reply") else "❌"
    r_del_all = "✅" if rights.get("can_delete_all_messages") else "❌"
    r_del_out = "✅" if rights.get("can_delete_outgoing_messages") else "❌"
    r_read = "✅" if rights.get("can_read_messages") else "❌"

    await message.answer(
        "📡 <b>Статус подключения — Hestle.Exe</b>\n\n"
        "Статус: 🟢 <b>Подключено и активно</b>\n"
        f"Владелец: <b>{escape_html(conn['owner_name'])}</b>\n"
        f"ID сессии: <code>{escape_html(conn['connection_id'])}</code>\n\n"
        "<b>Права доступа:</b>\n"
        f"{r_reply} Отправка сообщений\n"
        f"{r_read} Чтение сообщений\n"
        f"{r_del_all} Удаление всех сообщений\n"
        f"{r_del_out} Удаление исходящих сообщений"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    await state.clear()
    conn = storage.get_user_active_connection(message.from_user.id)
    if not conn:
        await message.answer(
            "⚙️ <b>Настройки недоступны</b>\n\n"
            "Сначала подключите бота в разделе <b>Telegram Business → Чат-боты</b>."
        )
        return

    settings = storage.get_settings(conn["connection_id"])
    await message.answer(
        build_settings_text(conn, settings),
        reply_markup=build_settings_keyboard(settings),
    )


@router.message(Command("help"))
async def cmd_help_private(message: Message) -> None:
    await message.answer(format_help_text())


# --- 3. CALLBACK-ОБРАБОТЧИКИ МЕНЮ, НАСТРОЕК И МИНИ-ИГР ---
@router.callback_query(F.data.startswith("menu:"))
async def on_main_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        return
    action = callback.data.split(":", 1)[1]
    await state.clear()

    if action == "help":
        await callback.message.edit_text(
            format_help_text(),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")]]
            ),
        )
        await callback.answer()
        return

    if action == "status":
        conn = storage.get_user_active_connection(callback.from_user.id)
        if not conn:
            text = (
                "📡 <b>Статус подключения — Hestle.Exe</b>\n\n"
                "Статус: ⚪️ <b>Не подключено</b>\n"
                "Добавьте бота в <i>Telegram Business → Чат-боты</i>."
            )
        else:
            rights = conn.get("rights", {})
            text = (
                "📡 <b>Статус подключения — Hestle.Exe</b>\n\n"
                "Статус: 🟢 <b>Активно</b>\n"
                f"Владелец: <b>{escape_html(conn['owner_name'])}</b>\n"
                f"• Отправка: {'✅' if rights.get('can_reply') else '❌'}\n"
                f"• Удаление всех: {'✅' if rights.get('can_delete_all_messages') else '❌'}\n"
                f"• Удаление исходящих: {'✅' if rights.get('can_delete_outgoing_messages') else '❌'}"
            )
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")]]
            ),
        )
        await callback.answer()
        return

    if action == "settings":
        conn = storage.get_user_active_connection(callback.from_user.id)
        if not conn:
            await callback.answer("Сначала подключите Telegram Business.", show_alert=True)
            return
        settings = storage.get_settings(conn["connection_id"])
        await callback.message.edit_text(
            build_settings_text(conn, settings),
            reply_markup=build_settings_keyboard(settings),
        )
        await callback.answer()
        return

    if action == "back":
        conn = storage.get_user_active_connection(callback.from_user.id)
        status_badge = "🟢 Активно" if conn else "⚪️ Не подключено"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings"),
                    InlineKeyboardButton(text="📡 Статус", callback_data="menu:status"),
                ],
                [
                    InlineKeyboardButton(text="📖 Список команд", callback_data="menu:help"),
                ],
            ]
        )
        await callback.message.edit_text(
            "⚡ <b>Hestle.Exe</b>\n"
            "<i>Персональный ассистент для Telegram Business</i>\n\n"
            f"Статус подключения: <b>{status_badge}</b>\n\n"
            "<b>Как подключить за 30 секунд:</b>\n"
            "1. Откройте <b>Настройки Telegram → Telegram Business → Чат-боты</b>.\n"
            "2. Укажите имя этого бота и выберите его.\n"
            "3. Выдайте разрешения на управление сообщениями.",
            reply_markup=kb,
        )
        await callback.answer()


@router.callback_query(F.data.startswith("cfg:"))
async def on_settings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        return

    conn = storage.get_user_active_connection(callback.from_user.id)
    if not conn:
        await callback.answer("Активное подключение Telegram Business не найдено.", show_alert=True)
        return

    conn_id = conn["connection_id"]
    settings = storage.get_settings(conn_id)
    parts = callback.data.split(":")
    action = parts[1]

    if action == "toggle" and len(parts) == 3:
        feature_key = parts[2]
        if feature_key in settings and isinstance(settings[feature_key], bool):
            settings[feature_key] = not settings[feature_key]
            await storage.save()
            await callback.message.edit_text(
                build_settings_text(conn, settings),
                reply_markup=build_settings_keyboard(settings),
            )
            await callback.answer("Параметр обновлён")
        return

    if action == "toggle_oneshot":
        settings["autoreply_one_shot"] = not settings["autoreply_one_shot"]
        await storage.save()
        await callback.message.edit_text(
            build_settings_text(conn, settings),
            reply_markup=build_settings_keyboard(settings),
        )
        await callback.answer("Режим автоответчика изменён")
        return

    if action == "reset":
        storage.data["settings"][conn_id] = storage.default_settings()
        await storage.save()
        settings = storage.get_settings(conn_id)
        await callback.message.edit_text(
            build_settings_text(conn, settings),
            reply_markup=build_settings_keyboard(settings),
        )
        await callback.answer("Настройки сброшены по умолчанию")
        return

    if action == "edit_autoreply":
        await state.set_state(SettingsFSM.waiting_autoreply_text)
        await callback.message.answer(
            "✏️ <b>Новый текст автоответчика</b>\n\n"
            "Отправьте новое сообщение (до 500 символов) или /cancel для отмены."
        )
        await callback.answer()
        return

    if action == "edit_mute":
        await state.set_state(SettingsFSM.waiting_mute_text)
        await callback.message.answer(
            "✏️ <b>Новое уведомление при включении .mute</b>\n\n"
            "Отправьте текст уведомления (до 300 символов) или /cancel для отмены."
        )
        await callback.answer()
        return

    if action == "edit_interval":
        await state.set_state(SettingsFSM.waiting_spam_interval)
        await callback.message.answer(
            f"⏱ <b>Интервал между сообщениями .spam</b>\n\n"
            f"Введите число в секундах от <code>{MIN_SPAM_INTERVAL}</code> до <code>{MAX_SPAM_INTERVAL}</code> (например: <code>1.5</code>) или /cancel для отмены."
        )
        await callback.answer()
        return

    if action == "edit_troll":
        await state.set_state(SettingsFSM.waiting_troll_phrase)
        await callback.message.answer(
            "💬 <b>Добавить фразу для .troll</b>\n\n"
            "Отправьте новую фразу (до 250 символов) или /cancel для отмены."
        )
        await callback.answer()
        return


@router.callback_query(F.data.startswith("ms:"))
async def on_minesweeper_click(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        return
    game_id, cell_arg = parts[1], parts[2]
    game = MINESWEEPER_GAMES.get(game_id)
    if not game or game["over"]:
        await callback.answer("Игра уже завершена.")
        return

    if cell_arg == "mode":
        game["flag_mode"] = not game["flag_mode"]
        await callback.answer("Режим переключён")
    else:
        idx = int(cell_arg)
        if game["flag_mode"]:
            if idx not in game["revealed"]:
                if idx in game["flags"]:
                    game["flags"].remove(idx)
                else:
                    game["flags"].add(idx)
        else:
            if idx in game["flags"] or idx in game["revealed"]:
                await callback.answer()
                return
            if idx in game["mines"]:
                game["revealed"].add(idx)
                game["over"] = True
                game["won"] = False
            else:
                game["revealed"].add(idx)
                total_safe = game["size"] * game["size"] - len(game["mines"])
                if len(game["revealed"]) >= total_safe:
                    game["over"] = True
                    game["won"] = True
        await callback.answer()

    status = "💣 <b>Сапёр — Hestle.Exe</b>\n\nОткрывайте безопасные клетки."
    if game["over"]:
        status = (
            "🏆 <b>Сапёр — Победа!</b> Все мины успешно обнаружены."
            if game["won"]
            else "💥 <b>Сапёр — Взрыв!</b> Попалась мина."
        )

    if callback.inline_message_id:
        await callback.bot.edit_message_text(
            inline_message_id=callback.inline_message_id,
            text=status,
            reply_markup=render_minesweeper_kb(game),
        )
    elif callback.message:
        await callback.message.edit_text(
            text=status,
            reply_markup=render_minesweeper_kb(game),
        )


@router.callback_query(F.data.startswith("ttt:"))
async def on_ttt_click(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        return
    game_id, idx_str = parts[1], parts[2]
    game = TTT_GAMES.get(game_id)
    if not game or game["over"]:
        await callback.answer("Игра завершена.")
        return

    idx = int(idx_str)
    if game["board"][idx]:
        await callback.answer("Клетка занята.")
        return

    mark = game["turn"]
    game["board"][idx] = mark
    winner = check_ttt_winner(game["board"])
    if winner:
        game["over"] = True
        header = (
            "🤝 <b>Крестики-нолики — Ничья!</b>"
            if winner == "DRAW"
            else f"🏆 <b>Крестики-нолики — Победили {winner}!</b>"
        )
    else:
        game["turn"] = "⭕️" if mark == "❌" else "❌"
        header = f"🎮 <b>Крестики-нолики</b>\nСейчас ходят: <b>{game['turn']}</b>"

    await callback.answer()
    if callback.inline_message_id:
        await callback.bot.edit_message_text(
            inline_message_id=callback.inline_message_id,
            text=header,
            reply_markup=render_ttt_kb(game),
        )
    elif callback.message:
        await callback.message.edit_text(
            text=header,
            reply_markup=render_ttt_kb(game),
        )


@router.callback_query(F.data.startswith("rec:"))
async def on_reaction_game_click(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 2 or not callback.from_user:
        return
    start_ts = float(parts[1])
    elapsed = max(0.01, time.time() - start_ts)
    winner = escape_html(callback.from_user.full_name)
    text = (
        "⚡ <b>Игра на реакцию — Финиш!</b>\n\n"
        f"🏆 Победитель: <b>{winner}</b>\n"
        f"⏱ Время реакции: <code>{elapsed:.2f} сек.</code>"
    )
    await callback.answer(f"Ваш результат: {elapsed:.2f} сек.!")
    if callback.inline_message_id:
        await callback.bot.edit_message_text(
            inline_message_id=callback.inline_message_id,
            text=text,
        )
    elif callback.message:
        await callback.message.edit_text(text=text)


@router.callback_query(F.data.startswith("tl:"))
async def on_translate_button(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        return
    lang, encoded = parts[1], parts[2]
    try:
        src_text = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        await callback.answer("Ошибка декодирования текста.", show_alert=True)
        return

    api_url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl={quote(lang)}&dt=t&q={quote(src_text)}"
    )
    data = await fetch_json(api_url)
    translated = ""
    if isinstance(data, list) and data and isinstance(data[0], list):
        translated = "".join(chunk[0] for chunk in data[0] if chunk and chunk[0])

    if not translated:
        await callback.answer("Сервис перевода временно недоступен.", show_alert=True)
        return

    out_text = (
        f"🌐 <b>Перевод ({lang.upper()}):</b>\n\n"
        f"{escape_html(translated)}"
    )
    await callback.answer("Переведено")
    if callback.inline_message_id:
        await callback.bot.edit_message_text(
            inline_message_id=callback.inline_message_id,
            text=out_text,
        )
    elif callback.message:
        await callback.message.edit_text(text=out_text)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("❌ Действие отменено.")


@router.message(SettingsFSM.waiting_autoreply_text)
async def process_new_autoreply_text(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    conn = storage.get_user_active_connection(message.from_user.id)
    if not conn:
        await state.clear()
        await message.answer("⚠️ Подключение не найдено.")
        return

    new_text = message.text.strip()
    if not new_text or len(new_text) > 500:
        await message.answer("⚠️ Текст должен содержать от 1 до 500 символов. Попробуйте снова:")
        return

    settings = storage.get_settings(conn["connection_id"])
    settings["autoreply_text"] = new_text
    await storage.save()
    await state.clear()

    await message.answer(
        "✅ <b>Текст автоответчика сохранён.</b>\n\n"
        + build_settings_text(conn, settings),
        reply_markup=build_settings_keyboard(settings),
    )


@router.message(SettingsFSM.waiting_mute_text)
async def process_new_mute_text(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    conn = storage.get_user_active_connection(message.from_user.id)
    if not conn:
        await state.clear()
        await message.answer("⚠️ Подключение не найдено.")
        return

    new_text = message.text.strip()
    if not new_text or len(new_text) > 300:
        await message.answer("⚠️ Текст должен содержать от 1 до 300 символов. Попробуйте снова:")
        return

    settings = storage.get_settings(conn["connection_id"])
    settings["mute_notice_text"] = new_text
    await storage.save()
    await state.clear()

    await message.answer(
        "✅ <b>Уведомление режима тишины обновлено.</b>\n\n"
        + build_settings_text(conn, settings),
        reply_markup=build_settings_keyboard(settings),
    )


@router.message(SettingsFSM.waiting_spam_interval)
async def process_new_spam_interval(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    conn = storage.get_user_active_connection(message.from_user.id)
    if not conn:
        await state.clear()
        await message.answer("⚠️ Подключение не найдено.")
        return

    try:
        val = float(message.text.strip().replace(",", "."))
        if not (MIN_SPAM_INTERVAL <= val <= MAX_SPAM_INTERVAL):
            raise ValueError
    except ValueError:
        await message.answer(
            f"⚠️ Введите корректное число от <code>{MIN_SPAM_INTERVAL}</code> до <code>{MAX_SPAM_INTERVAL}</code>:"
        )
        return

    settings = storage.get_settings(conn["connection_id"])
    settings["spam_interval"] = round(val, 2)
    await storage.save()
    await state.clear()

    await message.answer(
        "✅ <b>Интервал рассылки обновлён.</b>\n\n"
        + build_settings_text(conn, settings),
        reply_markup=build_settings_keyboard(settings),
    )


@router.message(SettingsFSM.waiting_troll_phrase)
async def process_new_troll_phrase(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return
    conn = storage.get_user_active_connection(message.from_user.id)
    if not conn:
        await state.clear()
        await message.answer("⚠️ Подключение не найдено.")
        return

    phrase = message.text.strip()
    if not phrase or len(phrase) > 250:
        await message.answer("⚠️ Фраза должна быть от 1 до 250 символов:")
        return

    settings = storage.get_settings(conn["connection_id"])
    settings["troll_phrases"].append(phrase)
    if len(settings["troll_phrases"]) > 30:
        settings["troll_phrases"] = settings["troll_phrases"][-30:]
    await storage.save()
    await state.clear()

    await message.answer(
        "✅ <b>Фраза добавлена в список .troll.</b>\n\n"
        + build_settings_text(conn, settings),
        reply_markup=build_settings_keyboard(settings),
    )


# --- 4. ПОНЯТНЫЙ ОТВЕТ НА КОМАНДЫ В ЛИЧНОМ ЧАТЕ С БОТОМ ---
@router.message(F.text)
async def private_text_fallback(message: Message, state: FSMContext) -> None:
    """Не даём dot-командам молча пропадать в личке с ботом."""
    if message.chat.type != "private" or not message.text:
        return

    text = message.text.strip()
    normalized = text.lower()

    if normalized in {".help", "help"}:
        await cmd_help_private(message)
        return
    if normalized in {".status", "status"}:
        await cmd_status(message)
        return
    if normalized in {".settings", "settings"}:
        await cmd_settings(message, state)
        return

    if normalized.startswith((".", "/")):
        await message.answer(
            "ℹ️ <b>Команда получена, но этот чат не является Business-перепиской.</b>\n\n"
            "В личном чате со мной доступны <code>/start</code>, <code>/help</code>, "
            "<code>/status</code> и <code>/settings</code>.\n\n"
            "Команды управления перепиской — например <code>.mute</code>, "
            "<code>.unmute</code>, <code>.afk</code> и <code>.auto</code> — "
            "отправляйте от своего аккаунта в обычной переписке, которую вы подключили "
            "через <b>Настройки Telegram → Telegram Business → Чат-боты</b>."
        )


# --- 5. ОБРАБОТКА УДАЛЕНИЯ СООБЩЕНИЙ (ДЛЯ АНТИ-МУТА .nomute) ---
@router.deleted_business_messages()
async def on_deleted_business_messages(event: BusinessMessagesDeleted, bot: Bot) -> None:
    conn_id = event.business_connection_id
    chat_id = event.chat.id
    conn = storage.get_connection(conn_id)
    if not conn or not conn.get("is_enabled"):
        return

    settings = storage.get_settings(conn_id)
    if not settings.get("antimute_mode", False):
        return

    for mid in event.message_ids:
        cached_text = SENT_OWNER_MESSAGES.pop((conn_id, chat_id, mid), None)
        if cached_text:
            await send_biz(
                bot,
                conn_id,
                chat_id,
                f"🛡 <b>Восстановлено:</b>\n{escape_html(cached_text)}",
            )


# --- 5. ОБРАБОТКА ВСЕХ TELEGRAM BUSINESS СООБЩЕНИЙ ---
@router.business_message()
async def on_business_message(message: Message, bot: Bot) -> None:
    connection_id = message.business_connection_id
    if not connection_id:
        logger.warning(
            "Получено business_message без business_connection_id: chat_id=%s message_id=%s",
            message.chat.id,
            message.message_id,
        )
        return

    conn = storage.get_connection(connection_id)
    if not conn:
        logger.warning(
            "Business-сообщение пришло для неизвестного подключения: connection_id=%s chat_id=%s",
            connection_id,
            message.chat.id,
        )
        return
    if not conn.get("is_enabled"):
        logger.warning(
            "Business-сообщение пришло для отключённого подключения: connection_id=%s",
            connection_id,
        )
        return

    owner_id: int = conn["owner_id"]
    chat_id: int = message.chat.id
    sender_id: Optional[int] = message.from_user.id if message.from_user else None

    settings = storage.get_settings(connection_id)
    chat_state = storage.get_chat_state(connection_id, chat_id)

    # Учёт ID сообщения и статистики диалога
    chat_state["msg_ids"].append(message.message_id)
    if len(chat_state["msg_ids"]) > 200:
        chat_state["msg_ids"] = chat_state["msg_ids"][-200:]

    hour_key = str(datetime.now(timezone(timedelta(hours=3))).hour)
    stats = chat_state["stats"]
    stats["hours"][hour_key] = stats["hours"].get(hour_key, 0) + 1
    if message.text:
        for w in re.findall(r"[а-яА-ЯёЁa-zA-Z]{3,}", message.text.lower()):
            stats["words"][w] = stats["words"].get(w, 0) + 1
            if len(stats["words"]) > 150:
                top_items = sorted(stats["words"].items(), key=lambda x: x[1], reverse=True)[:80]
                stats["words"] = dict(top_items)

    # Автоудаление в режиме .bchat
    burn_chat_sec = int(chat_state.get("burn_chat_sec", 0))
    if burn_chat_sec > 0:
        asyncio.create_task(
            run_delayed_delete(bot, connection_id, chat_id, message.message_id, burn_chat_sec)
        )

    is_owner_message = sender_id == owner_id
    logger.info(
        "Business update: connection_id=%s chat_id=%s sender_id=%s owner_id=%s owner_message=%s text=%r",
        connection_id,
        chat_id,
        sender_id,
        owner_id,
        is_owner_message,
        (message.text or message.caption or "")[:120],
    )

    # =================================================================
    # ВЕТКА А: ВХОДЯЩИЕ СООБЩЕНИЯ ОТ СОБЕСЕДНИКОВ ИЛИ ДРУГИХ БОТОВ
    # =================================================================
    if not is_owner_message:
        stats["peer_msgs"] = stats.get("peer_msgs", 0) + 1

        # 1. Режим тишины (.mute)
        if chat_state.get("muted") and settings.get("feature_mute", True):
            await safe_delete_business_message(bot, connection_id, chat_id, message.message_id)
            return

        # 2. Автоудаление стикеров и GIF (.wsag)
        if chat_state.get("wsag") and (message.sticker or message.animation):
            await safe_delete_business_message(bot, connection_id, chat_id, message.message_id)
            return

        # 3. Режим троллинга (.troll)
        if chat_state.get("troll"):
            phrases = settings.get("troll_phrases") or DEFAULT_TROLL_PHRASES
            phrase = random.choice(phrases)
            await asyncio.sleep(float(settings.get("troll_delay", 0.5)))
            await send_biz(
                bot,
                connection_id,
                chat_id,
                phrase,
                reply_to_message_id=message.message_id,
            )

        # 4. Режим AFK (.afk)
        if settings.get("afk_active"):
            since = int(settings.get("afk_since", time.time()))
            elapsed = format_duration(int(time.time()) - since)
            reason = settings.get("afk_reason") or "Временно отсутствую"
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"💤 <b>AFK-режим</b>\nПричина: <i>{escape_html(reason)}</i>\nОтсутствую: <b>{elapsed}</b>",
                reply_to_message_id=message.message_id,
            )
            return

        # 5. Автоответчик (.Avtootvet / .auto)
        if chat_state.get("autoreply") and settings.get("feature_autoreply", True):
            reply_text = settings.get("autoreply_text") or DEFAULT_AUTOREPLY_TEXT
            await send_biz(bot, connection_id, chat_id, reply_text)
            if settings.get("autoreply_one_shot", True):
                chat_state["autoreply"] = False
                await storage.save()
        return

    # =================================================================
    # ВЕТКА Б: СООБЩЕНИЯ И КОМАНДЫ ВЛАДЕЛЬЦА АККАУНТА
    # =================================================================
    stats["owner_msgs"] = stats.get("owner_msgs", 0) + 1
    raw_text = (message.text or message.caption or "").strip()

    if raw_text:
        SENT_OWNER_MESSAGES[(connection_id, chat_id, message.message_id)] = raw_text
        if len(SENT_OWNER_MESSAGES) > 1000:
            oldest_key = next(iter(SENT_OWNER_MESSAGES))
            SENT_OWNER_MESSAGES.pop(oldest_key, None)

    # Автоматическое снятие AFK при отправке обычного сообщения
    if settings.get("afk_active") and not raw_text.lower().startswith(".afk"):
        settings["afk_active"] = False
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "🟢 <b>Вы вернулись в сеть.</b> AFK-режим отключён.")

    # Быстрые автозамены (*команда)
    if raw_text.startswith("*") and len(raw_text) > 1:
        replaces: Dict[str, str] = settings.get("replaces", {})
        if raw_text in replaces:
            await safe_edit_business_message(
                bot, connection_id, chat_id, message.message_id, replaces[raw_text]
            )
            return

    # В Business-чатах поддерживаем и dot-команды, и slash-алиасы.
    # Например, .mute и /mute выполняют одно и то же действие.
    if raw_text.startswith("/"):
        slash_parts = raw_text.split(maxsplit=1)
        command_name = slash_parts[0][1:].split("@", 1)[0]
        command_args = slash_parts[1] if len(slash_parts) > 1 else ""
        raw_text = f".{command_name}" + (f" {command_args}" if command_args else "")

    # Если это не команда — проверяем режимы стилизации (.bold / .kawaii).
    if not raw_text.startswith("."):
        if raw_text and message.text:
            if settings.get("bold_mode"):
                await safe_edit_business_message(
                    bot,
                    connection_id,
                    chat_id,
                    message.message_id,
                    f"<b>{escape_html(raw_text)}</b>",
                )
            elif settings.get("kawaii_mode"):
                face = random.choice(KAWAII_FACES)
                kawaii_txt = f"{escape_html(raw_text)} {face} ✨"
                await safe_edit_business_message(
                    bot,
                    connection_id,
                    chat_id,
                    message.message_id,
                    kawaii_txt,
                )
        return

    parts = raw_text.split(maxsplit=2)
    cmd = parts[0].lower()
    arg_all = raw_text[len(parts[0]):].strip()
    logger.info(
        "Business-команда: %s | connection_id=%s | chat_id=%s | owner_id=%s",
        cmd,
        connection_id,
        chat_id,
        owner_id,
    )

    async def delete_trigger() -> None:
        SENT_OWNER_MESSAGES.pop((connection_id, chat_id, message.message_id), None)
        await safe_delete_business_message(bot, connection_id, chat_id, message.message_id)

    # -----------------------------------------------------------------
    # 1. МОДЕРАЦИЯ И ЗАЩИТА ЧАТА
    # -----------------------------------------------------------------
    if cmd == ".mute":
        if not settings.get("feature_mute", True):
            return
        await delete_trigger()
        chat_state["muted"] = True
        await storage.save()
        notice = settings.get("mute_notice_text") or DEFAULT_MUTE_NOTICE_TEXT
        await send_biz(bot, connection_id, chat_id, notice)
        return

    if cmd == ".unmute":
        await delete_trigger()
        chat_state["muted"] = False
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "🔊 Режим тишины отключён.")
        return

    if cmd == ".nomute":
        await delete_trigger()
        settings["antimute_mode"] = not settings.get("antimute_mode", False)
        await storage.save()
        state_lbl = "включена" if settings["antimute_mode"] else "отключена"
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🛡 Защита от удаления ваших сообщений (анти-мут) <b>{state_lbl}</b>.",
        )
        return

    if cmd == ".wsag":
        await delete_trigger()
        chat_state["wsag"] = True
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "🚫 Автоудаление стикеров и GIF в чате <b>включено</b>.")
        return

    if cmd == ".unwsag":
        await delete_trigger()
        chat_state["wsag"] = False
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "✅ Автоудаление стикеров и GIF <b>отключено</b>.")
        return

    if cmd == ".burn":
        await delete_trigger()
        if len(parts) < 3:
            await send_biz(bot, connection_id, chat_id, "🔥 <b>Формат:</b> <code>.burn 30s секретный текст</code>")
            return
        sec = parse_time_arg(parts[1])
        if not sec or not (1 <= sec <= 3600):
            await send_biz(bot, connection_id, chat_id, "⚠️ Укажите время от <code>1s</code> до <code>3600s</code>.")
            return
        sent = await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🔥 <i>[Удалится через {format_duration(sec)}]</i>\n{escape_html(parts[2])}",
        )
        if sent:
            asyncio.create_task(run_delayed_delete(bot, connection_id, chat_id, sent.message_id, sec))
        return

    if cmd == ".bchat":
        await delete_trigger()
        if len(parts) < 2:
            await send_biz(bot, connection_id, chat_id, "⏳ <b>Формат:</b> <code>.bchat 2m</code>")
            return
        sec = parse_time_arg(parts[1])
        if not sec or not (5 <= sec <= 3600):
            await send_biz(bot, connection_id, chat_id, "⚠️ Укажите интервал от <code>5s</code> до <code>60m</code>.")
            return
        chat_state["burn_chat_sec"] = sec
        await storage.save()
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"⏳ <b>Режим автоудаления чата включён.</b>\nНовые сообщения удаляются через <b>{format_duration(sec)}</b>.",
        )
        return

    if cmd == ".unbchat":
        await delete_trigger()
        chat_state["burn_chat_sec"] = 0
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "✅ Режим автоудаления чата отключён.")
        return

    if cmd in (".panic", ".del"):
        await delete_trigger()
        n = int(parts[1]) if (len(parts) >= 2 and parts[1].isdigit()) else 10
        n = max(1, min(50, n))
        ids_to_del = list(reversed(chat_state.get("msg_ids", [])))[:n]
        deleted_cnt = 0
        for mid in ids_to_del:
            if await safe_delete_business_message(bot, connection_id, chat_id, mid):
                deleted_cnt += 1
                if mid in chat_state["msg_ids"]:
                    chat_state["msg_ids"].remove(mid)
        await storage.save()
        notice = await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🧹 Очищено сообщений из буфера сессии: <b>{deleted_cnt}</b>.",
        )
        if notice:
            asyncio.create_task(run_delayed_delete(bot, connection_id, chat_id, notice.message_id, 4))
        return

    if cmd == ".pin":
        await delete_trigger()
        if not message.reply_to_message:
            await send_biz(bot, connection_id, chat_id, "📌 Ответьте этой командой на сообщение, которое нужно закрепить.")
            return
        try:
            await bot.pin_chat_message(
                business_connection_id=connection_id,
                chat_id=chat_id,
                message_id=message.reply_to_message.message_id,
            )
            await send_biz(bot, connection_id, chat_id, "📌 Сообщение закреплено.")
        except TelegramAPIError as exc:
            await send_biz(bot, connection_id, chat_id, f"⚠️ Не удалось закрепить сообщение: <code>{escape_html(str(exc))}</code>")
        return

    if cmd == ".unpin":
        await delete_trigger()
        try:
            await bot.unpin_chat_message(
                business_connection_id=connection_id,
                chat_id=chat_id,
                message_id=message.reply_to_message.message_id if message.reply_to_message else None,
            )
            await send_biz(bot, connection_id, chat_id, "📍 Сообщение откреплено.")
        except TelegramAPIError as exc:
            await send_biz(bot, connection_id, chat_id, f"⚠️ Не удалось открепить: <code>{escape_html(str(exc))}</code>")
        return

    if cmd == ".warn":
        await delete_trigger()
        target_user = message.reply_to_message.from_user if message.reply_to_message else None
        if not target_user:
            await send_biz(bot, connection_id, chat_id, "⚠️ Ответьте командой <code>.warn</code> на сообщение собеседника.")
            return
        uid_key = str(target_user.id)
        warns = chat_state.setdefault("warns", {})
        warns[uid_key] = warns.get(uid_key, 0) + 1
        cnt = warns[uid_key]
        if cnt >= 3:
            chat_state["muted"] = True
            warns[uid_key] = 0
            await storage.save()
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"🚫 <b>{escape_html(target_user.full_name)}</b> получил <b>3/3</b> предупреждений.\nРежим тишины (<code>.mute</code>) активирован автоматически.",
            )
        else:
            await storage.save()
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"⚠️ Предупреждение для <b>{escape_html(target_user.full_name)}</b>: <b>{cnt}/3</b>.",
            )
        return

    # -----------------------------------------------------------------
    # 2. АВТООТВЕТЧИК, AFK, STREAK
    # -----------------------------------------------------------------
    if cmd == ".avtootvet":
        if not settings.get("feature_autoreply", True):
            return
        await delete_trigger()
        chat_state["autoreply"] = True
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "📨 Автоответчик активирован для этого чата.")
        return

    if cmd in (".noavtootvet", ".unauto", ".unautoai", ".unafkai"):
        await delete_trigger()
        chat_state["autoreply"] = False
        settings["afk_active"] = False
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "📭 Автоответчик и авто-режимы выключены.")
        return

    if cmd in (".auto", ".autoai", ".autocmd"):
        if not settings.get("feature_autoreply", True):
            return
        await delete_trigger()
        if arg_all:
            settings["autoreply_text"] = arg_all[:500]
        chat_state["autoreply"] = True
        await storage.save()
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"📨 <b>Автоответчик включён</b>\nТекст: <i>«{escape_html(settings['autoreply_text'])}»</i>",
        )
        return

    if cmd in (".afk", ".afkai"):
        await delete_trigger()
        reason = arg_all or "Отошёл по делам"
        settings["afk_active"] = True
        settings["afk_reason"] = reason[:200]
        settings["afk_since"] = int(time.time())
        await storage.save()
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"💤 <b>AFK-режим активирован</b>\nПричина: <i>{escape_html(reason)}</i>",
        )
        return

    if cmd == ".streak":
        await delete_trigger()
        today = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d")
        if chat_state.get("streak_last_day") != today:
            chat_state["streak_count"] = int(chat_state.get("streak_count", 0)) + 1
            chat_state["streak_last_day"] = today
            await storage.save()
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🔥 <b>Серия общения активна: {chat_state['streak_count']} дн.</b>",
        )
        return

    if cmd == ".unstreak":
        await delete_trigger()
        chat_state["streak_count"] = 0
        chat_state["streak_last_day"] = ""
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "❄️ Серия общения сброшена.")
        return

    # -----------------------------------------------------------------
    # 3. ДИАГНОСТИЧЕСКИЕ И ВИЗУАЛЬНЫЕ ОТЧЁТЫ (В СТИЛЕ .snos)
    # -----------------------------------------------------------------
    if cmd == ".snos":
        if not settings.get("feature_snos", True):
            return
        await delete_trigger()
        asyncio.create_task(
            run_animated_report(
                bot=bot,
                connection_id=connection_id,
                chat_id=chat_id,
                title="Диагностический отчёт",
                steps=[
                    "Инициализация модуля проверки сессии…",
                    "Сверка параметров и формирование пакета отчёта…",
                    "Фиксация контрольной суммы в журнале…",
                ],
                final_body=(
                    "• Статус: <b>Локальная фиксация выполнена</b>\n"
                    "• Модуль: <code>Session-Check v2.6</code>\n"
                    "• Запись сохранена в журнал текущего диалога."
                ),
                reply_to_msg=message.reply_to_message,
                target_override=arg_all if arg_all else None,
            )
        )
        return

    if cmd == ".dox":
        if not settings.get("feature_snos", True):
            return
        await delete_trigger()
        target_user = message.reply_to_message.from_user if message.reply_to_message else message.chat
        uid = getattr(target_user, "id", chat_id)
        uname = getattr(target_user, "username", None)
        uname_str = f"@{uname}" if uname else "отсутствует"
        full_name = getattr(target_user, "full_name", None) or getattr(target_user, "title", "Пользователь")
        reg_year = estimate_reg_date(uid) if isinstance(uid, int) and uid > 0 else "—"
        dc_id = (abs(int(uid)) % 5) + 1 if isinstance(uid, int) else 2
        asyncio.create_task(
            run_animated_report(
                bot=bot,
                connection_id=connection_id,
                chat_id=chat_id,
                title="Карточка профиля",
                steps=[
                    "Сбор открытых метаданных аккаунта…",
                    "Определение дата-центра и диапазона ID…",
                    "Формирование сводного досье…",
                ],
                final_body=(
                    f"• Имя: <b>{escape_html(full_name)}</b>\n"
                    f"• Telegram ID: <code>{uid}</code>\n"
                    f"• Username: <code>{escape_html(uname_str)}</code>\n"
                    f"• Дата-центр: <code>DC-{dc_id}</code>\n"
                    f"• Оценка регистрации: <code>{reg_year}</code>"
                ),
                reply_to_msg=message.reply_to_message,
            )
        )
        return

    if cmd == ".osint":
        if not settings.get("feature_snos", True):
            return
        await delete_trigger()
        nick = (arg_all or (message.reply_to_message.from_user.username if (message.reply_to_message and message.reply_to_message.from_user) else "") or "").lstrip("@").strip()
        if not nick:
            await send_biz(bot, connection_id, chat_id, "🔍 <b>Формат:</b> <code>.osint username</code> или ответом на сообщение.")
            return
        safe_nick = quote(nick)
        asyncio.create_task(
            run_animated_report(
                bot=bot,
                connection_id=connection_id,
                chat_id=chat_id,
                title="Поиск по никнейму",
                steps=[
                    "Формирование прямых ссылок на публичные профили…",
                    "Проверка синтаксиса идентификатора…",
                    "Сборка каталога площадок…",
                ],
                final_body=(
                    f"• Запрос: <code>@{escape_html(nick)}</code>\n"
                    f"• Telegram: https://t.me/{safe_nick}\n"
                    f"• GitHub: https://github.com/{safe_nick}\n"
                    f"• Reddit: https://www.reddit.com/user/{safe_nick}\n"
                    f"• TikTok: https://www.tiktok.com/@{safe_nick}"
                ),
                target_override=f"@{nick}",
            )
        )
        return

    if cmd in (".logger", ".getlink", ".getweb"):
        if not settings.get("feature_snos", True):
            return
        await delete_trigger()
        token_hex = f"{random.getrandbits(48):012x}"
        labels = {
            ".logger": ("Генератор трекинг-ссылки", f"https://t.me/iv?url=https%3A%2F%2Fhestle.local%2Fr%2F{token_hex}"),
            ".getlink": ("Звуковой модуль ссылки", f"https://hestle.local/audio/{token_hex}"),
            ".getweb": ("Сессия веб-журнала", f"https://hestle.local/session/{connection_id[:8]}-{token_hex[:6]}"),
        }
        title, gen_url = labels[cmd]
        asyncio.create_task(
            run_animated_report(
                bot=bot,
                connection_id=connection_id,
                chat_id=chat_id,
                title=title,
                steps=[
                    "Выделение уникального идентификатора сессии…",
                    "Привязка к текущему подключению…",
                    "Генерация ключа доступа завершена…",
                ],
                final_body=(
                    f"• Идентификатор: <code>{token_hex}</code>\n"
                    f"• Ссылка сессии: <code>{gen_url}</code>\n"
                    f"• Статус: <b>Активна в рамках текущей сессии</b>"
                ),
            )
        )
        return

    if cmd == ".krek":
        if not settings.get("feature_snos", True):
            return
        await delete_trigger()
        asyncio.create_task(
            run_animated_report(
                bot=bot,
                connection_id=connection_id,
                chat_id=chat_id,
                title="Проверка совместимости клиента",
                steps=[
                    "Анализ заголовков текущего диалога…",
                    "Тестирование рендеринга Unicode-последовательностей…",
                    "Завершение диагностики…",
                ],
                final_body=(
                    "• Кодировка: <code>UTF-8 / Strict</code>\n"
                    "• Совместимость клиента: <b>Подтверждена</b>\n"
                    "• Аномалий отрисовки не обнаружено."
                ),
                reply_to_msg=message.reply_to_message,
            )
        )
        return

    # -----------------------------------------------------------------
    # 4. ИНФОРМАЦИЯ О ПРОФИЛЕ, СТАТИСТИКА И ПИНГ
    # -----------------------------------------------------------------
    if cmd in (".info", ".get"):
        await delete_trigger()
        target = message.reply_to_message.from_user if message.reply_to_message else None
        if target:
            uid = target.id
            name = target.full_name
            uname = f"@{target.username}" if target.username else "—"
            is_bot = "Да" if target.is_bot else "Нет"
            is_prem = "Да" if getattr(target, "is_premium", False) else "Нет"
            reg = estimate_reg_date(uid)
            await send_biz(
                bot,
                connection_id,
                chat_id,
                "🪪 <b>Досье пользователя — Hestle.Exe</b>\n\n"
                f"• Имя: <b>{escape_html(name)}</b>\n"
                f"• ID: <code>{uid}</code>\n"
                f"• Username: <code>{escape_html(uname)}</code>\n"
                f"• Telegram Premium: <b>{is_prem}</b>\n"
                f"• Бот: <b>{is_bot}</b>\n"
                f"• Оценка регистрации: <code>{reg}</code>",
            )
        else:
            await send_biz(
                bot,
                connection_id,
                chat_id,
                "🪪 <b>Информация о диалоге — Hestle.Exe</b>\n\n"
                f"• Chat ID: <code>{chat_id}</code>\n"
                f"• Тип чата: <code>{message.chat.type}</code>\n"
                f"• Владелец сессии: <b>{escape_html(conn['owner_name'])}</b>\n\n"
                "<i>Совет: ответьте командой на сообщение собеседника, чтобы увидеть его данные.</i>",
            )
        return

    if cmd == ".id":
        await delete_trigger()
        reply_uid = (
            message.reply_to_message.from_user.id
            if (message.reply_to_message and message.reply_to_message.from_user)
            else "—"
        )
        reply_mid = message.reply_to_message.message_id if message.reply_to_message else "—"
        await send_biz(
            bot,
            connection_id,
            chat_id,
            "🆔 <b>Идентификаторы</b>\n\n"
            f"• Chat ID: <code>{chat_id}</code>\n"
            f"• Ваш ID: <code>{owner_id}</code>\n"
            f"• ID собеседника: <code>{reply_uid}</code>\n"
            f"• ID сообщения: <code>{reply_mid}</code>",
        )
        return

    if cmd == ".stat":
        await delete_trigger()
        o_cnt = stats.get("owner_msgs", 0)
        p_cnt = stats.get("peer_msgs", 0)
        total = o_cnt + p_cnt
        hours: Dict[str, int] = stats.get("hours", {})
        peak_hour = max(hours.items(), key=lambda x: x[1])[0] + ":00" if hours else "—"
        words: Dict[str, int] = stats.get("words", {})
        top_w = ", ".join(
            f"{w} ({c})" for w, c in sorted(words.items(), key=lambda x: x[1], reverse=True)[:5]
        ) or "недостаточно данных"

        await send_biz(
            bot,
            connection_id,
            chat_id,
            "📊 <b>Статистика диалога — Hestle.Exe</b>\n\n"
            f"• Всего учтено сообщений: <b>{total}</b>\n"
            f"• Ваших сообщений: <b>{o_cnt}</b>\n"
            f"• Сообщений собеседника: <b>{p_cnt}</b>\n"
            f"• Пиковый час активности: <b>{peak_hour} (МСК)</b>\n"
            f"• Частые слова: <i>{escape_html(top_w)}</i>",
        )
        return

    if cmd == ".ping":
        await delete_trigger()
        t0 = time.perf_counter()
        sent = await send_biz(bot, connection_id, chat_id, "🏓 Измерение задержки…")
        dt_ms = (time.perf_counter() - t0) * 1000
        if sent:
            await safe_edit_business_message(
                bot,
                connection_id,
                chat_id,
                sent.message_id,
                f"🏓 <b>Pong!</b> Задержка Telegram API: <code>{dt_ms:.1f} мс</code>",
            )
        return

    # -----------------------------------------------------------------
    # 5. ПЕРЕВОДЧИК, ТЕКСТОВЫЕ УТИЛИТЫ И АНАЛИЗ ДИАЛОГА
    # -----------------------------------------------------------------
    if cmd == ".translate":
        await delete_trigger()
        src = arg_all or (
            (message.reply_to_message.text or message.reply_to_message.caption or "")
            if message.reply_to_message
            else ""
        )
        if not src:
            await send_biz(bot, connection_id, chat_id, "🌐 Ответьте на сообщение или напишите: <code>.translate Hello world</code>")
            return
        api_url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=auto&tl=ru&dt=t&q={quote(src)}"
        )
        data = await fetch_json(api_url)
        translated = ""
        if isinstance(data, list) and data and isinstance(data[0], list):
            translated = "".join(chunk[0] for chunk in data[0] if chunk and chunk[0])
        if translated:
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"🌐 <b>Перевод на русский:</b>\n\n{escape_html(translated)}",
            )
        else:
            await send_biz(bot, connection_id, chat_id, "⚠️ Не удалось выполнить перевод. Попробуйте позже.")
        return

    if cmd == ".tl":
        await delete_trigger()
        src = arg_all or (
            (message.reply_to_message.text or message.reply_to_message.caption or "")
            if message.reply_to_message
            else ""
        )
        if not src:
            await send_biz(bot, connection_id, chat_id, "🌐 Укажите текст или ответьте на сообщение командой <code>.tl</code>.")
            return
        short_src = src[:120]
        encoded = base64.urlsafe_b64encode(short_src.encode("utf-8")).decode("ascii")
        if len(encoded) > 54:
            short_src = src[:35]
            encoded = base64.urlsafe_b64encode(short_src.encode("utf-8")).decode("ascii")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🇷🇺 RU", callback_data=f"tl:ru:{encoded}"),
                    InlineKeyboardButton(text="🇬🇧 EN", callback_data=f"tl:en:{encoded}"),
                    InlineKeyboardButton(text="🇩🇪 DE", callback_data=f"tl:de:{encoded}"),
                ],
                [
                    InlineKeyboardButton(text="🇫🇷 FR", callback_data=f"tl:fr:{encoded}"),
                    InlineKeyboardButton(text="🇪🇸 ES", callback_data=f"tl:es:{encoded}"),
                    InlineKeyboardButton(text="🇹🇷 TR", callback_data=f"tl:tr:{encoded}"),
                ],
            ]
        )
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🌐 <b>Выберите язык перевода:</b>\n<i>«{escape_html(short_src)}»</i>",
            reply_markup=kb,
        )
        return

    if cmd == ".sw":
        await delete_trigger()
        src = arg_all or (
            (message.reply_to_message.text or "") if message.reply_to_message else ""
        )
        if not src:
            await send_biz(bot, connection_id, chat_id, "⌨️ Укажите текст или ответьте на сообщение: <code>.sw Ghbdtn</code>")
            return
        await send_biz(bot, connection_id, chat_id, f"⌨️ {escape_html(switch_keyboard_layout(src))}")
        return

    if cmd == ".dumb":
        await delete_trigger()
        src = arg_all or (
            (message.reply_to_message.text or "") if message.reply_to_message else ""
        )
        if not src:
            await send_biz(bot, connection_id, chat_id, "🤪 Укажите текст: <code>.dumb Привет, как дела?</code>")
            return
        await send_biz(bot, connection_id, chat_id, escape_html(to_olbanian(src)))
        return

    if cmd == ".leet":
        await delete_trigger()
        src = arg_all or (
            (message.reply_to_message.text or "") if message.reply_to_message else ""
        )
        if not src:
            await send_biz(bot, connection_id, chat_id, "👾 Укажите текст: <code>.leet Привет мир</code>")
            return
        await send_biz(bot, connection_id, chat_id, f"<code>{escape_html(src.translate(LEET_MAP))}</code>")
        return

    if cmd == ".morse":
        await delete_trigger()
        src = arg_all or (
            (message.reply_to_message.text or "") if message.reply_to_message else ""
        )
        if not src:
            await send_biz(bot, connection_id, chat_id, "📡 Укажите текст или ответьте на код Морзе.")
            return
        if re.fullmatch(r"[.\-/\s]+", src):
            decoded = morse_to_text(src)
            await send_biz(bot, connection_id, chat_id, f"📡 <b>Расшифровка:</b> {escape_html(decoded)}")
        else:
            encoded = text_to_morse(src)
            await send_biz(bot, connection_id, chat_id, f"📡 <b>Код Морзе:</b>\n<code>{escape_html(encoded)}</code>")
        return

    if cmd == ".pqt":
        await delete_trigger()
        quote_text = arg_all
        author = conn["owner_name"]
        if message.reply_to_message:
            if not quote_text:
                quote_text = message.reply_to_message.text or message.reply_to_message.caption or "[Медиа]"
            if message.reply_to_message.from_user:
                author = message.reply_to_message.from_user.full_name
        if not quote_text:
            await send_biz(bot, connection_id, chat_id, "💬 Ответьте на сообщение или напишите текст: <code>.pqt текст</code>")
            return
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"<blockquote>{escape_html(quote_text)}</blockquote>\n— <b>{escape_html(author)}</b>",
        )
        return

    if cmd in (".ai", ".gpt"):
        await delete_trigger()
        question = arg_all or (
            (message.reply_to_message.text or "") if message.reply_to_message else ""
        )
        if not question:
            await send_biz(bot, connection_id, chat_id, "🧠 Укажите запрос: <code>.ai Что такое квантовая запутанность?</code>")
            return
        # Используем открытый API Википедии для точных справок без API-ключей
        search_url = (
            "https://ru.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={quote(question)}&utf8=&format=json&srlimit=1"
        )
        search_data = await fetch_json(search_url)
        summary_text = ""
        if isinstance(search_data, dict):
            hits = search_data.get("query", {}).get("search", [])
            if hits:
                page_title = hits[0]["title"]
                sum_url = f"https://ru.wikipedia.org/api/rest_v1/page/summary/{quote(page_title)}"
                sum_data = await fetch_json(sum_url)
                if isinstance(sum_data, dict) and sum_data.get("extract"):
                    summary_text = sum_data["extract"]

        if summary_text:
            if len(summary_text) > 700:
                summary_text = summary_text[:697] + "..."
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"🧠 <b>Справка по запросу «{escape_html(question)}»:</b>\n\n{escape_html(summary_text)}",
            )
        else:
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"🧠 <b>Запрос принят:</b> <i>«{escape_html(question)}»</i>\n\n"
                "Краткая энциклопедическая статья по точной формулировке не найдена. Попробуйте указать ключевое понятие.",
            )
        return

    if cmd in (".dialog", ".pms"):
        await delete_trigger()
        o_cnt = stats.get("owner_msgs", 0)
        p_cnt = stats.get("peer_msgs", 0)
        ratio = round((o_cnt / max(1, p_cnt)), 2)
        tone = "нейтрально-деловой"
        if message.reply_to_message and message.reply_to_message.text:
            sample = message.reply_to_message.text
            if "!" in sample or sample.isupper():
                tone = "эмоциональный / напряжённый"
            elif "?" in sample:
                tone = "вопросительный / уточняющий"
            elif any(x in sample.lower() for x in ("спасибо", "отлично", "супер", "рад", "хорошо")):
                tone = "доброжелательный"

        await send_biz(
            bot,
            connection_id,
            chat_id,
            "🧩 <b>Анализ переписки — Hestle.Exe</b>\n\n"
            f"• Баланс активности (Вы / Собеседник): <b>{o_cnt} / {p_cnt}</b> (коэф. {ratio})\n"
            f"• Оценка тона последнего контекста: <b>{tone}</b>\n"
            "• Рекомендация: поддерживайте чёткую структуру ответов и уточняйте детали.",
        )
        return

    # -----------------------------------------------------------------
    # 6. РАССЫЛКА, ТРОЛЛИНГ, СТИЛИЗАЦИЯ И АНИМАЦИИ ТЕКСТА
    # -----------------------------------------------------------------
    if cmd == ".spam":
        if not settings.get("feature_spam", True):
            return
        await delete_trigger()
        if len(parts) < 3 or not parts[1].isdigit():
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"⚠️ <b>Формат:</b> <code>.spam [1–{MAX_SPAM_COUNT}] [текст]</code>",
            )
            return
        count = int(parts[1])
        spam_text = parts[2].strip()
        if not (1 <= count <= MAX_SPAM_COUNT) or not spam_text:
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"⚠️ Допустимое количество сообщений: от <b>1</b> до <b>{MAX_SPAM_COUNT}</b>.",
            )
            return

        task_key = (connection_id, chat_id)
        existing_task = ACTIVE_SPAM_TASKS.get(task_key)
        if existing_task and not existing_task.done():
            existing_task.cancel()

        interval = float(settings.get("spam_interval", DEFAULT_SPAM_INTERVAL))
        ACTIVE_SPAM_TASKS[task_key] = asyncio.create_task(
            run_spam_worker(bot, connection_id, chat_id, count, spam_text, interval)
        )
        return

    if cmd in (".nospam", ".stopspam"):
        await delete_trigger()
        task_key = (connection_id, chat_id)
        existing_task = ACTIVE_SPAM_TASKS.pop(task_key, None)
        if existing_task and not existing_task.done():
            existing_task.cancel()
            await send_biz(bot, connection_id, chat_id, "🛑 Отправка сообщений остановлена.")
        else:
            await send_biz(bot, connection_id, chat_id, "ℹ️ Активная рассылка в этом чате отсутствует.")
        return

    if cmd == ".haha":
        await delete_trigger()
        laughs = ["АХАХАХАХА", "АХХАХАХАХХ 😂", "ХАХАХАХАХА", "АХАХАХХААХ 🤣", "ХЫХЫХАХАХА"]
        task_key = (connection_id, chat_id)
        existing_task = ACTIVE_SPAM_TASKS.get(task_key)
        if existing_task and not existing_task.done():
            existing_task.cancel()

        async def _haha_worker() -> None:
            for item in laughs:
                await send_biz(bot, connection_id, chat_id, item)
                await asyncio.sleep(0.8)

        ACTIVE_SPAM_TASKS[task_key] = asyncio.create_task(_haha_worker())
        return

    if cmd == ".stair":
        await delete_trigger()
        words = arg_all.split()[:5]
        if not words:
            await send_biz(bot, connection_id, chat_id, "🪜 <b>Формат:</b> <code>.stair слово1 слово2 слово3</code>")
            return
        for idx, w in enumerate(words):
            indent = "⠀" * idx
            await send_biz(bot, connection_id, chat_id, f"{indent}{escape_html(w)}")
            await asyncio.sleep(0.6)
        return

    if cmd == ".troll":
        await delete_trigger()
        chat_state["troll"] = True
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "🎭 Режим троллинга в диалоге <b>включён</b>.")
        return

    if cmd == ".untroll":
        await delete_trigger()
        chat_state["troll"] = False
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "✅ Режим троллинга <b>отключён</b>.")
        return

    if cmd == ".tset":
        await delete_trigger()
        if not arg_all:
            phrases_preview = "\n".join(
                f"{i + 1}. {escape_html(p)}" for i, p in enumerate(settings.get("troll_phrases", [])[:10])
            )
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"🎭 <b>Текущие фразы .troll:</b>\n{phrases_preview}\n\n"
                "Добавить фразу: <code>.tset Ваша фраза</code>",
            )
            return
        settings["troll_phrases"].append(arg_all[:250])
        await storage.save()
        await send_biz(bot, connection_id, chat_id, f"✅ Фраза добавлена: <i>«{escape_html(arg_all[:250])}»</i>")
        return

    if cmd == ".bold":
        await delete_trigger()
        settings["bold_mode"] = not settings.get("bold_mode", False)
        await storage.save()
        lbl = "включён" if settings["bold_mode"] else "отключён"
        await send_biz(bot, connection_id, chat_id, f"🅱️ Автоматический жирный шрифт <b>{lbl}</b>.")
        return

    if cmd == ".kawaii":
        await delete_trigger()
        settings["kawaii_mode"] = True
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "🌸 Каваи-режим активирован (◕‿◕✿)")
        return

    if cmd == ".unkawaii":
        await delete_trigger()
        settings["kawaii_mode"] = False
        await storage.save()
        await send_biz(bot, connection_id, chat_id, "🌿 Каваи-режим отключён.")
        return

    if cmd == ".replace":
        await delete_trigger()
        if len(parts) < 3 or not parts[1].startswith("*"):
            reps = settings.get("replaces", {})
            rep_list = "\n".join(
                f"• <code>{escape_html(k)}</code> → {escape_html(v)}" for k, v in reps.items()
            ) or "список пуст"
            await send_biz(
                bot,
                connection_id,
                chat_id,
                f"⚡ <b>Быстрые автозамены:</b>\n{rep_list}\n\n"
                "Формат: <code>.replace *ключ текст замены</code>",
            )
            return
        key_word = parts[1]
        val_text = parts[2]
        settings.setdefault("replaces", {})[key_word] = val_text
        await storage.save()
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"✅ Автозамена сохранена: <code>{escape_html(key_word)}</code> → {escape_html(val_text)}",
        )
        return

    # --- Анимации текста ---
    if cmd == ".anim":
        await delete_trigger()
        if len(parts) < 3 or parts[1] not in ("1", "2", "3"):
            await send_biz(bot, connection_id, chat_id, "✨ <b>Формат:</b> <code>.anim [1|2|3] текст</code>")
            return
        mode = parts[1]
        txt = parts[2][:120]
        if mode == "1":
            frames = [escape_html(txt[:i]) + "▌" for i in range(1, len(txt) + 1, max(1, len(txt) // 8))]
            frames.append(escape_html(txt))
        elif mode == "2":
            e = escape_html(txt)
            frames = [f"<code>{e}</code>", f"<i>{e}</i>", f"<u>{e}</u>", f"<b>{e}</b>"]
        else:
            e = escape_html(txt)
            glyphs = "#@$%&*01"
            frames = [
                f"<code>{''.join(random.choice(glyphs) for _ in range(min(16, len(txt))))}</code>",
                f"<code>{e[:len(e)//2]}{''.join(random.choice(glyphs) for _ in range(6))}</code>",
                f"<b>{e}</b>",
            ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.55))
        return

    if cmd == ".print":
        await delete_trigger()
        txt = (arg_all or "Hestle.Exe")[:100]
        step = max(1, len(txt) // 8)
        frames = [f"<code>{escape_html(txt[:i])}▌</code>" for i in range(1, len(txt) + 1, step)]
        frames.append(escape_html(txt))
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.5))
        return

    if cmd == ".magic":
        await delete_trigger()
        e = escape_html(arg_all or "Магия")
        frames = [
            f"✨ <i>{e}</i> ✨",
            f"🔮 <b>{e}</b> 🔮",
            f"🪄 ✨ <b>{e}</b> ✨ 🪄",
        ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.6))
        return

    if cmd == ".matrix":
        await delete_trigger()
        e = escape_html(arg_all or "ACCESS GRANTED")
        frames = [
            "<code>01001000 01000101 01010011 01010100</code>",
            "<code>[DECRYPTING STREAM...] 64%</code>",
            f"🟩 <b><code>{e}</code></b>",
        ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.65))
        return

    if cmd in (".heart", ".love"):
        await delete_trigger()
        e = escape_html(arg_all or "❤️")
        frames = [
            f"🤍 {e}",
            f"🩷 {e}",
            f"❤️ <b>{e}</b>",
            f"💖 <b>{e}</b> 💖",
        ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.55))
        return

    if cmd == ".fire":
        await delete_trigger()
        e = escape_html(arg_all or "Огонь")
        frames = [
            f"🕯 {e}",
            f"🔥 {e} 🔥",
            f"💥🔥 <b>{e}</b> 🔥💥",
        ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.55))
        return

    if cmd == ".boom":
        await delete_trigger()
        frames = [
            "💣 <code>3...</code>",
            "💣 <code>2...</code>",
            "💣 <code>1...</code>",
            "💥 <b>БА-БАХ!</b>",
        ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.6))
        return

    if cmd == ".load":
        await delete_trigger()
        e = escape_html(arg_all or "Завершено")
        frames = [
            "⏳ <code>[▓▓░░░░░░░░] 20%</code>",
            "⏳ <code>[▓▓▓▓▓░░░░░] 50%</code>",
            "⏳ <code>[▓▓▓▓▓▓▓▓░░] 80%</code>",
            f"✅ <code>[▓▓▓▓▓▓▓▓▓▓] 100%</code> — <b>{e}</b>",
        ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.6))
        return

    if cmd == ".police":
        await delete_trigger()
        e = escape_html(arg_all or "Внимание")
        frames = [
            f"🔴🔵 <b>{e}</b> 🔵🔴",
            f"🔵🔴 <b>{e}</b> 🔴🔵",
            f"🚨 <b>{e}</b> 🚨",
        ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.55))
        return

    if cmd == ".clown":
        await delete_trigger()
        e = escape_html(arg_all or "Цирк")
        frames = [
            f"🙂 {e}",
            f"🤡 {e}",
            f"🎪🤡 <b>{e}</b> 🤡🎪",
        ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.6))
        return

    # -----------------------------------------------------------------
    # 7. УТИЛИТЫ, ПОГОДА, КУРСЫ, ГЕО, ССЫЛКИ И КАРТОЧКИ ЧЕКОВ
    # -----------------------------------------------------------------
    if cmd == ".calc":
        if not settings.get("feature_tools", True):
            return
        await delete_trigger()
        if not arg_all:
            await send_biz(bot, connection_id, chat_id, "🧮 <b>Формат:</b> <code>.calc (125 + 75) / 4</code>")
            return
        try:
            result = safe_eval_math(arg_all)
            formatted_res = (
                f"{int(result)}"
                if result.is_integer()
                else f"{result:.8f}".rstrip("0").rstrip(".")
            )
            body = (
                "🧮 <b>Hestle.Exe — Калькулятор</b>\n\n"
                f"Выражение: <code>{escape_html(arg_all)}</code>\n"
                f"Результат: <b><code>{formatted_res}</code></b>"
            )
        except ZeroDivisionError:
            body = "⚠️ <b>Ошибка расчёта:</b> деление на ноль невозможно."
        except Exception:
            body = "⚠️ <b>Некорректное выражение.</b> Используйте числа и знаки <code>+ - * / ( ) % ^</code>."
        await send_biz(bot, connection_id, chat_id, body)
        return

    if cmd == ".timer":
        if not settings.get("feature_tools", True):
            return
        await delete_trigger()
        if len(parts) < 2 or not parts[1].isdigit():
            await send_biz(bot, connection_id, chat_id, "⏳ <b>Формат:</b> <code>.timer [секунды 1–3600] [заметка]</code>")
            return
        seconds = int(parts[1])
        if not (1 <= seconds <= 3600):
            await send_biz(bot, connection_id, chat_id, "⚠️ Укажите время от <b>1</b> до <b>3600</b> секунд.")
            return
        label = parts[2].strip() if len(parts) >= 3 else ""
        asyncio.create_task(run_timer_worker(bot, connection_id, chat_id, seconds, label))
        note_preview = f" ({escape_html(label)})" if label else ""
        await send_biz(bot, connection_id, chat_id, f"⏳ Таймер установлен на <b>{format_duration(seconds)}</b>{note_preview}.")
        return

    if cmd in (".remind", ".remindf"):
        if not settings.get("feature_tools", True):
            return
        await delete_trigger()
        if len(parts) < 3:
            await send_biz(bot, connection_id, chat_id, f"⏰ <b>Формат:</b> <code>{cmd} 30m текст напоминания</code>")
            return
        sec = parse_schedule_time(parts[1])
        if not sec or sec > 86400:
            await send_biz(bot, connection_id, chat_id, "⚠️ Укажите корректное время (например: <code>30m</code> или <code>18:30</code>).")
            return
        note_txt = parts[2].strip()
        to_pm = cmd == ".remind"
        asyncio.create_task(
            run_timer_worker(
                bot,
                connection_id,
                chat_id,
                sec,
                note_txt,
                to_owner_pm=to_pm,
                owner_chat_id=conn.get("user_chat_id"),
            )
        )
        dest = "в личные сообщения с ботом" if to_pm else "в этот чат"
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"⏰ Напоминание установлено через <b>{format_duration(sec)}</b> ({dest}).",
        )
        return

    if cmd == ".weather":
        await delete_trigger()
        city = arg_all or "Москва"
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={quote(city)}&count=1&language=ru&format=json"
        geo_data = await fetch_json(geo_url)
        if not isinstance(geo_data, dict) or not geo_data.get("results"):
            await send_biz(bot, connection_id, chat_id, f"🌦 Город <b>{escape_html(city)}</b> не найден.")
            return
        place = geo_data["results"][0]
        lat, lon = place["latitude"], place["longitude"]
        resolved_name = place.get("name", city)
        w_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
            "&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=2"
        )
        w_data = await fetch_json(w_url)
        if not isinstance(w_data, dict) or "current" not in w_data:
            await send_biz(bot, connection_id, chat_id, "⚠️ Сервис погоды временно недоступен.")
            return
        cur = w_data["current"]
        daily = w_data.get("daily", {})
        t_now = cur.get("temperature_2m", "—")
        hum = cur.get("relative_humidity_2m", "—")
        wind = cur.get("wind_speed_10m", "—")
        t_min = daily.get("temperature_2m_min", ["—", "—"])[-1]
        t_max = daily.get("temperature_2m_max", ["—", "—"])[-1]
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🌤 <b>Погода — {escape_html(resolved_name)}</b>\n\n"
            f"• Сейчас: <b>{t_now}°C</b>\n"
            f"• Влажность: <b>{hum}%</b> | Ветер: <b>{wind} км/ч</b>\n"
            f"• Прогноз на завтра: <b>{t_min}°C … {t_max}°C</b>",
        )
        return

    if cmd == ".rates":
        await delete_trigger()
        crypto_url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,ethereum,the-open-network,tron,tether&vs_currencies=usd,rub&include_24hr_change=true"
        )
        c_data = await fetch_json(crypto_url)
        if not isinstance(c_data, dict) or "bitcoin" not in c_data:
            await send_biz(bot, connection_id, chat_id, "⚠️ Не удалось получить актуальные курсы. Повторите через минуту.")
            return

        def fmt_coin(cid: str, label: str) -> str:
            item = c_data.get(cid, {})
            usd = item.get("usd", 0)
            rub = item.get("rub", 0)
            chg = item.get("usd_24h_change", 0)
            sign = "+" if chg >= 0 else ""
            return f"• <b>{label}:</b> <code>${usd:,.2f}</code> ({rub:,.1f} ₽) [{sign}{chg:.1f}%]"

        usdt_rub = c_data.get("tether", {}).get("rub", 0)
        await send_biz(
            bot,
            connection_id,
            chat_id,
            "💱 <b>Актуальные курсы — Hestle.Exe</b>\n\n"
            f"{fmt_coin('bitcoin', 'BTC')}\n"
            f"{fmt_coin('ethereum', 'ETH')}\n"
            f"{fmt_coin('the-open-network', 'TON')}\n"
            f"{fmt_coin('tron', 'TRX')}\n"
            f"• <b>USDT / RUB:</b> <code>{usdt_rub:.2f} ₽</code>",
        )
        return

    if cmd == ".iss":
        await delete_trigger()
        iss_data = await fetch_json("http://api.open-notify.org/iss-now.json")
        if isinstance(iss_data, dict) and "iss_position" in iss_data:
            pos = iss_data["iss_position"]
            lat, lon = pos["latitude"], pos["longitude"]
            await send_biz(
                bot,
                connection_id,
                chat_id,
                "🛰 <b>Координаты МКС (ISS) в реальном времени</b>\n\n"
                f"• Широта: <code>{lat}</code>\n"
                f"• Долгота: <code>{lon}</code>\n"
                f"• Карта: https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=4/{lat}/{lon}",
            )
        else:
            await send_biz(bot, connection_id, chat_id, "⚠️ Не удалось получить телеметрию МКС.")
        return

    if cmd in (".geo", ".geolive", ".livegeo"):
        await delete_trigger()
        query = arg_all or "Москва, Красная площадь"
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={quote(query)}&count=1&language=ru&format=json"
        geo_data = await fetch_json(geo_url)
        if not isinstance(geo_data, dict) or not geo_data.get("results"):
            await send_biz(bot, connection_id, chat_id, f"📍 Локация <b>{escape_html(query)}</b> не найдена.")
            return
        place = geo_data["results"][0]
        lat, lon = float(place["latitude"]), float(place["longitude"])
        try:
            await bot.send_location(
                business_connection_id=connection_id,
                chat_id=chat_id,
                latitude=lat,
                longitude=lon,
            )
        except TelegramAPIError as exc:
            await send_biz(bot, connection_id, chat_id, f"⚠️ Не удалось отправить геопозицию: <code>{escape_html(str(exc))}</code>")
        return

    if cmd == ".qr":
        await delete_trigger()
        if not arg_all:
            await send_biz(bot, connection_id, chat_id, "📱 <b>Формат:</b> <code>.qr https://example.com</code>")
            return
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={quote(arg_all)}"
        img_bytes = await fetch_bytes(qr_url)
        if img_bytes:
            try:
                await bot.send_photo(
                    business_connection_id=connection_id,
                    chat_id=chat_id,
                    photo=BufferedInputFile(img_bytes, filename="qrcode.png"),
                    caption=f"📱 <b>QR-код:</b> <code>{escape_html(arg_all[:100])}</code>",
                )
            except TelegramAPIError as exc:
                await send_biz(bot, connection_id, chat_id, f"⚠️ Ошибка отправки QR: <code>{escape_html(str(exc))}</code>")
        else:
            await send_biz(bot, connection_id, chat_id, "⚠️ Сервис генерации QR временно недоступен.")
        return

    if cmd == ".short":
        await delete_trigger()
        if not arg_all.startswith(("http://", "https://")):
            await send_biz(bot, connection_id, chat_id, "🔗 <b>Формат:</b> <code>.short https://example.com</code>")
            return
        short_api = f"https://clck.ru/--?url={quote(arg_all)}"
        raw_bytes = await fetch_bytes(short_api)
        if raw_bytes:
            short_link = raw_bytes.decode("utf-8", errors="ignore").strip()
            await send_biz(bot, connection_id, chat_id, f"🔗 <b>Короткая ссылка:</b> {escape_html(short_link)}")
        else:
            await send_biz(bot, connection_id, chat_id, "⚠️ Не удалось сократить ссылку.")
        return

    if cmd == ".unshort":
        await delete_trigger()
        if not arg_all.startswith(("http://", "https://")):
            await send_biz(bot, connection_id, chat_id, "🔍 <b>Формат:</b> <code>.unshort https://clck.ru/...</code>")
            return
        chain = await resolve_redirect_chain(arg_all)
        lines = "\n".join(f"{i + 1}. <code>{escape_html(u)}</code>" for i, u in enumerate(chain))
        await send_biz(bot, connection_id, chat_id, f"🔍 <b>Цепочка перенаправлений:</b>\n\n{lines}")
        return

    if cmd == ".link":
        await delete_trigger()
        uname = conn.get("owner_username")
        if not uname:
            await send_biz(bot, connection_id, chat_id, "⚠️ Для генерации ссылки установите @username в настройках Telegram.")
            return
        preset = quote(arg_all or "Привет!")
        deep_link = f"https://t.me/{uname}?text={preset}"
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🔗 <b>Ссылка с готовым текстом:</b>\n<code>{deep_link}</code>",
        )
        return

    if cmd == ".fakec":
        await delete_trigger()
        amount = arg_all or "1000"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"Получить {amount} ₽", url="https://t.me/CryptoBot")]
            ]
        )
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"💎 <b>Чек Crypto Bot на {escape_html(amount)} ₽</b>\n\n"
            "Нажмите кнопку ниже для просмотра параметров перевода.",
            reply_markup=kb,
        )
        return

    if cmd == ".fakel":
        await delete_trigger()
        amount_str = arg_all or "100"
        try:
            usd_val = float(amount_str.replace(",", "."))
            gram_val = round(usd_val * 42.5, 2)
        except ValueError:
            usd_val = 100.0
            gram_val = 4250.0
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"Открыть чек ({usd_val:g} USD)", url="https://t.me/wallet")]
            ]
        )
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🪙 <b>Чек Лавешка — {usd_val:g} USD</b>\n"
            f"Эквивалент: <code>{gram_val:g} GRAM</code>",
            reply_markup=kb,
        )
        return

    # -----------------------------------------------------------------
    # 8. МИНИ-ИГРЫ И RP-ДЕЙСТВИЯ
    # -----------------------------------------------------------------
    if cmd == ".saper":
        await delete_trigger()
        game = create_minesweeper_board(size=5, mines=5)
        MINESWEEPER_GAMES[game["id"]] = game
        await send_biz(
            bot,
            connection_id,
            chat_id,
            "💣 <b>Сапёр — Hestle.Exe</b>\n\nОткрывайте безопасные клетки.",
            reply_markup=render_minesweeper_kb(game),
        )
        return

    if cmd == ".ttt":
        await delete_trigger()
        gid = f"{random.randint(10000, 99999)}"
        game = {"id": gid, "board": [""] * 9, "turn": "❌", "over": False}
        TTT_GAMES[gid] = game
        await send_biz(
            bot,
            connection_id,
            chat_id,
            "🎮 <b>Крестики-нолики</b>\nСейчас ходят: <b>❌</b>",
            reply_markup=render_ttt_kb(game),
        )
        return

    if cmd == ".rec":
        await delete_trigger()
        now_ts = f"{time.time():.3f}"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚡ НАЖАТЬ СЕЙЧАС!", callback_data=f"rec:{now_ts}")]
            ]
        )
        await send_biz(
            bot,
            connection_id,
            chat_id,
            "⚡ <b>Игра на реакцию!</b> Кто нажмёт кнопку быстрее?",
            reply_markup=kb,
        )
        return

    if cmd == ".rps":
        await delete_trigger()
        choices = ["🪨 Камень", "✂️ Ножницы", "📄 Бумага"]
        p1 = random.choice(choices)
        p2 = random.choice(choices)
        peer_name = (
            message.reply_to_message.from_user.full_name
            if (message.reply_to_message and message.reply_to_message.from_user)
            else "Собеседник"
        )
        await send_biz(
            bot,
            connection_id,
            chat_id,
            "🎮 <b>Камень, ножницы, бумага</b>\n\n"
            f"• <b>{escape_html(conn['owner_name'])}:</b> {p1}\n"
            f"• <b>{escape_html(peer_name)}:</b> {p2}",
        )
        return

    if cmd in (".ball", ".8ball"):
        await delete_trigger()
        q = escape_html(arg_all) if arg_all else "Без вопроса"
        ans = random.choice(EIGHT_BALL_ANSWERS)
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🎱 <b>Магический шар</b>\n\nВопрос: <i>{q}</i>\nОтвет: <b>{ans}</b>",
        )
        return

    if cmd == ".coin":
        await delete_trigger()
        side = random.choice(["🦅 Орёл", "🪙 Решка"])
        frames = [
            "🪙 <i>Подбрасываем монетку…</i>",
            "🔄 <i>Вращение в воздухе…</i>",
            f"✨ Результат: <b>{side}</b>",
        ]
        asyncio.create_task(run_text_frames_animation(bot, connection_id, chat_id, frames, 0.6))
        return

    if cmd == ".roll":
        await delete_trigger()
        nums = re.findall(r"-?\d+", arg_all)
        if len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
            low, high = min(a, b), max(a, b)
        elif len(nums) == 1:
            low, high = 1, max(1, int(nums[0]))
        else:
            low, high = 1, 100
        res = random.randint(low, high)
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"🎲 <b>Случайное число</b> (<code>{low}…{high}</code>): <b>{res}</b>",
        )
        return

    if cmd == ".tod":
        await delete_trigger()
        if random.choice([True, False]):
            item = random.choice(TRUTH_LIST)
            await send_biz(bot, connection_id, chat_id, f"❓ <b>Правда:</b> {item}")
        else:
            item = random.choice(DARE_LIST)
            await send_biz(bot, connection_id, chat_id, f"🔥 <b>Действие:</b> {item}")
        return

    if cmd == ".mog":
        await delete_trigger()
        peer_name = (
            message.reply_to_message.from_user.full_name
            if (message.reply_to_message and message.reply_to_message.from_user)
            else "Собеседник"
        )
        s1 = random.randint(60, 99)
        s2 = random.randint(60, 99)
        winner = conn["owner_name"] if s1 >= s2 else peer_name
        await send_biz(
            bot,
            connection_id,
            chat_id,
            "⚔️ <b>Mog Battle — Сравнение профилей</b>\n\n"
            f"• <b>{escape_html(conn['owner_name'])}:</b> {s1} pts\n"
            f"• <b>{escape_html(peer_name)}:</b> {s2} pts\n\n"
            f"🏆 Лидер раунда: <b>{escape_html(winner)}</b>",
        )
        return

    # --- Конструктор пользовательских RP-действий ---
    if cmd == ".addrp":
        await delete_trigger()
        rp_parts = arg_all.split(maxsplit=1)
        if len(rp_parts) < 2 or not rp_parts[0].startswith("."):
            await send_biz(bot, connection_id, chat_id, "🎭 <b>Формат:</b> <code>.addrp .кусь укусил(-а) за ушко</code>")
            return
        rp_cmd = rp_parts[0].lower()
        rp_phrase = rp_parts[1].strip()[:100]
        custom_rp: Dict[str, str] = settings.setdefault("custom_rp", {})
        if len(custom_rp) >= 10 and rp_cmd not in custom_rp:
            await send_biz(bot, connection_id, chat_id, "⚠️ Достигнут лимит пользовательских RP-команд (10 шт.).")
            return
        custom_rp[rp_cmd] = rp_phrase
        await storage.save()
        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"✅ RP-команда <code>{escape_html(rp_cmd)}</code> создана: <i>«{escape_html(rp_phrase)}»</i>",
        )
        return

    if cmd == ".myrp":
        await delete_trigger()
        custom_rp = settings.get("custom_rp", {})
        if not custom_rp:
            await send_biz(bot, connection_id, chat_id, "🎭 У вас пока нет пользовательских RP-команд. Создайте через <code>.addrp</code>.")
            return
        lines = "\n".join(
            f"• <code>{escape_html(k)}</code> — {escape_html(v)}" for k, v in custom_rp.items()
        )
        await send_biz(bot, connection_id, chat_id, f"🎭 <b>Ваши RP-команды:</b>\n\n{lines}")
        return

    if cmd == ".delrp":
        await delete_trigger()
        target_rp = arg_all.lower().strip()
        custom_rp = settings.get("custom_rp", {})
        if target_rp in custom_rp:
            del custom_rp[target_rp]
            await storage.save()
            await send_biz(bot, connection_id, chat_id, f"🗑 RP-команда <code>{escape_html(target_rp)}</code> удалена.")
        else:
            await send_biz(bot, connection_id, chat_id, "⚠️ Указанная RP-команда не найдена.")
        return

    # --- Встроенные и пользовательские RP-команды ---
    custom_rp = settings.get("custom_rp", {})
    if cmd in BUILTIN_RP_ACTIONS or cmd in custom_rp:
        await delete_trigger()
        actor = escape_html(conn["owner_name"])
        if message.reply_to_message and message.reply_to_message.from_user:
            target_name = escape_html(message.reply_to_message.from_user.full_name)
        elif arg_all:
            target_name = escape_html(arg_all)
        else:
            target_name = "собеседника"

        if cmd in custom_rp:
            emoji_icon = "🎭"
            action_phrase = escape_html(custom_rp[cmd])
        else:
            emoji_icon, action_phrase = BUILTIN_RP_ACTIONS[cmd]

        await send_biz(
            bot,
            connection_id,
            chat_id,
            f"{emoji_icon} <b>{actor}</b> {action_phrase} <b>{target_name}</b>",
        )
        return

    # --- КОМАНДА .help ---
    if cmd == ".help":
        await delete_trigger()
        await send_biz(bot, connection_id, chat_id, format_help_text())
        return

    logger.warning(
        "Неизвестная Business-команда: %s | connection_id=%s | chat_id=%s",
        cmd,
        connection_id,
        chat_id,
    )
    await send_biz(
        bot,
        connection_id,
        chat_id,
        f"❔ Команда <code>{escape_html(cmd)}</code> не найдена.\n"
        "Напишите <code>.help</code>, чтобы увидеть список доступных команд.",
    )


# =====================================================================
# MIDDLEWARE ДЕДУПЛИКАЦИИ UPDATES
# =====================================================================
class UpdateDeduplicationMiddleware:
    async def __call__(self, handler, event, data):
        update_id = getattr(event, "update_id", None)
        if update_id is not None and is_duplicate_update(update_id):
            logger.debug("Пропущен дублирующий update_id=%s", update_id)
            return None
        return await handler(event, data)


# =====================================================================
# ТОЧКА ВХОДА ПРИЛОЖЕНИЯ
# =====================================================================
async def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.critical(
            "Не указан токен бота! Откройте bot.py и замените YOUR_BOT_TOKEN_HERE на токен от @BotFather."
        )
        raise SystemExit(1)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(UpdateDeduplicationMiddleware())
    dp.include_router(router)

    try:
        me = await bot.get_me()
        logger.info("====================================================")
        logger.info("Запуск Hestle.Exe (@%s | ID: %s)", me.username, me.id)
        logger.info("Поддержка Telegram Business Connections активна")
        logger.info("Личные команды: /start, /help, /status, /settings")
        logger.info("Команды управления чатами работают в подключённых Business-переписках")
        logger.info("====================================================")
    except TelegramForbiddenError:
        logger.critical("Недействительный токен бота (Unauthorized). Проверьте BOT_TOKEN.")
        raise SystemExit(1)
    except TelegramAPIError as exc:
        logger.critical("Ошибка подключения к Telegram API при старте: %s", exc)
        raise SystemExit(1)

    allowed_updates = [
        "message",
        "callback_query",
        "business_connection",
        "business_message",
        "edited_business_message",
        "deleted_business_messages",
    ]

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=allowed_updates)
    finally:
        for task in list(ACTIVE_SPAM_TASKS.values()):
            if not task.done():
                task.cancel()
        await storage.save()
        await bot.session.close()
        logger.info("Hestle.Exe корректно остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
