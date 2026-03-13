#!/usr/bin/env python3
"""
THE_HELPER — Telethon-скрипт мониторинга /helpme в группах и супергруппах.

Слушает новые сообщения с командой /helpme в настроенных группах,
маршрутизирует запрос через существующий AI-роутер (RAG / UPOS) и
отвечает пользователю в стиле «плейсхолдер → редактирование».

Режимы:
    python scripts/the_helper.py                 — запустить слушатель
    python scripts/the_helper.py --manage-groups — управление списком групп (CLI)
"""

import asyncio
import argparse
import html
import json
import logging
import re
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Корень проекта для импортов
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from telethon import TelegramClient, events
from telethon.extensions import html as telethon_html
from telethon.utils import get_peer_id

from src.common.constants.sync import (
    TELETHON_API_ID,
    TELETHON_API_HASH,
    HELPER_SESSION_NAME,
    HELPER_RATE_LIMIT_USER_MAX,
    HELPER_RATE_LIMIT_USER_WINDOW,
    HELPER_RATE_LIMIT_GROUP_MAX,
    HELPER_RATE_LIMIT_GROUP_WINDOW,
)
from src.common.pii_masking import mask_sensitive_data
from src.core.ai.rag_service import preload_rag_runtime_dependencies
from src.group_knowledge.telethon_session import start_telegram_client_with_logging

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [THE_HELPER] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("the_helper")

# ---------------------------------------------------------------------------
# Путь к конфигурации групп
# ---------------------------------------------------------------------------
GROUPS_CONFIG_PATH = PROJECT_ROOT / "config" / "helper_groups.json"

# Максимальный возраст сообщения (секунды) — старые пропускаются при реконнекте
MAX_MESSAGE_AGE_SECONDS = 60

# Максимальная длина текста запроса
MAX_QUERY_LENGTH = 4000

# Максимальная длина одного сообщения Telegram (с запасом)
MAX_TELEGRAM_MESSAGE_LENGTH = 3900

# Паттерн команды /helpme (с возможным @username бота)
HELP_COMMAND_RE = re.compile(r"^/helpme(?:@\w+)?\s*(.*)", re.DOTALL | re.IGNORECASE)

# Разрешённые intent'ы для THE_HELPER
HELPER_ALLOWED_INTENTS = {
    "upos_error_lookup",
    "rag_qa",
    "general_chat",
}

# ---------------------------------------------------------------------------
# MarkdownV2-экранированные сообщения
# ---------------------------------------------------------------------------
MSG_PROCESSING = "⏳ _Читаю ваш вопрос\\.\\.\\._"
MSG_WAITING_AI = "⏳ _Ожидаю ответа ИИ_"
MSG_PREFILTERING = "⏳ _Подбираю подходящие материалы из базы знаний\\._"
MSG_AUGMENTED = "⏳ _Собираю слова в предложения \\(до 20 секунд\\)\\._"
MSG_UPOS_FALLBACK = "🔎 Код ошибки не найден в базе UPOS\\. Проверяю базу знаний\\."

MSG_ERROR = (
    "❌ *Произошла ошибка при обработке запроса*\n\n"
    "Попробуйте позже\\."
)

MSG_RATE_LIMIT_USER = (
    "⚠️ *Слишком много запросов*\n\n"
    "Подождите {seconds} сек\\. перед следующим запросом\\."
)

MSG_RATE_LIMIT_GROUP = (
    "⚠️ *Слишком много запросов в этой группе*\n\n"
    "Подождите {seconds} сек\\."
)

MSG_USAGE_HINT = (
    "ℹ️ *Как пользоваться /helpme*\n\n"
    "• `/helpme ваш вопрос` — задать вопрос\n"
    "• Ответьте `/helpme` на чужое сообщение — "
    "получить ответ по тексту сообщения"
)


def _strip_markdown_v2_escaping(text: str) -> str:
    """Убрать MarkdownV2-экранирование из текста для plain-text отправки."""
    return re.sub(r'\\+([_*\[\]()~`>#+\-=|{}.!])', r'\1', text)


def _prepare_markdown_for_telethon(text: str) -> str:
    """
    Подготовить MarkdownV2-текст к отправке через Telethon Markdown.

    THE_HELPER получает ответы, экранированные под Telegram MarkdownV2.
    Telethon в этом скрипте использует markdown-парсер, поэтому сначала
    снимаем MarkdownV2-экранирование, чтобы не показывать пользователю
    лишние обратные слэши.
    """
    return _strip_markdown_v2_escaping(text or "")


_HTML_TOKEN_PREFIX = "THEHELPERTOKEN"
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*([^*\n][^\n]*?)\*")
_ITALIC_RE = re.compile(r"_([^_\n][^\n]*?)_")


def _prepare_html_for_telethon(text: str) -> str:
    """
    Подготовить MarkdownV2-текст к безопасной отправке через HTML parse mode.

    Причина: ответы в проекте формируются как MarkdownV2 (экранированные строки),
    а markdown-парсер Telethon может падать на отдельных кейсах. HTML-представление
    с экранированием стабильнее для reply/edit в групповых чатах.
    """
    raw = _prepare_markdown_for_telethon(text)
    placeholders: Dict[str, str] = {}

    def _store(replacement_html: str) -> str:
        token = f"{_HTML_TOKEN_PREFIX}{len(placeholders)}END"
        placeholders[token] = replacement_html
        return token

    prepared = _INLINE_CODE_RE.sub(
        lambda m: _store(f"<code>{html.escape(m.group(1))}</code>"),
        raw,
    )
    prepared = _BOLD_RE.sub(
        lambda m: _store(f"<b>{html.escape(m.group(1))}</b>"),
        prepared,
    )
    prepared = _ITALIC_RE.sub(
        lambda m: _store(f"<i>{html.escape(m.group(1))}</i>"),
        prepared,
    )

    escaped = html.escape(prepared)
    for token, replacement in placeholders.items():
        escaped = escaped.replace(html.escape(token), replacement)

    return escaped


async def _reply_safe(event, text: str):
    """Безопасно отправить reply с markdown-форматированием."""
    prepared = _prepare_html_for_telethon(text)
    try:
        return await event.reply(prepared, parse_mode=telethon_html)
    except Exception as exc:
        logger.warning("Reply markdown parse failed, fallback to plain text: %s", exc)
        return await event.reply(_prepare_markdown_for_telethon(text))


async def _send_message_safe(client: TelegramClient, chat_id: int, text: str, reply_to: Optional[int] = None):
    """Безопасно отправить сообщение с markdown-форматированием."""
    prepared = _prepare_html_for_telethon(text)
    try:
        return await client.send_message(
            chat_id,
            prepared,
            parse_mode=telethon_html,
            reply_to=reply_to,
        )
    except Exception as exc:
        logger.warning("Send markdown parse failed, fallback to plain text: %s", exc)
        return await client.send_message(
            chat_id,
            _prepare_markdown_for_telethon(text),
            reply_to=reply_to,
        )


# ---------------------------------------------------------------------------
# Rate Limiter (per-user + per-group, sliding window)
# ---------------------------------------------------------------------------

class HelperRateLimiter:
    """
    Ограничитель частоты запросов для THE_HELPER.

    Поддерживает два уровня: per-user и per-group.
    Использует in-memory sliding window (время запросов в списке).
    """

    def __init__(
        self,
        user_max: int = HELPER_RATE_LIMIT_USER_MAX,
        user_window: int = HELPER_RATE_LIMIT_USER_WINDOW,
        group_max: int = HELPER_RATE_LIMIT_GROUP_MAX,
        group_window: int = HELPER_RATE_LIMIT_GROUP_WINDOW,
    ):
        self._user_max = user_max
        self._user_window = user_window
        self._group_max = group_max
        self._group_window = group_window
        self._user_requests: Dict[int, List[float]] = defaultdict(list)
        self._group_requests: Dict[int, List[float]] = defaultdict(list)

    def _cleanup(self, timestamps: List[float], window: int, now: float) -> List[float]:
        """Убрать просроченные записи из окна."""
        cutoff = now - window
        return [t for t in timestamps if t > cutoff]

    def check_user(self, user_id: int) -> Tuple[bool, Optional[int]]:
        """
        Проверить rate-limit пользователя.

        Returns:
            (разрешено, оставшиеся_секунды | None)
        """
        now = time.time()
        timestamps = self._cleanup(self._user_requests[user_id], self._user_window, now)
        self._user_requests[user_id] = timestamps
        if len(timestamps) >= self._user_max:
            oldest = timestamps[0]
            remaining = int(oldest + self._user_window - now) + 1
            return False, max(remaining, 1)
        return True, None

    def check_group(self, group_id: int) -> Tuple[bool, Optional[int]]:
        """
        Проверить rate-limit группы.

        Returns:
            (разрешено, оставшиеся_секунды | None)
        """
        now = time.time()
        timestamps = self._cleanup(self._group_requests[group_id], self._group_window, now)
        self._group_requests[group_id] = timestamps
        if len(timestamps) >= self._group_max:
            oldest = timestamps[0]
            remaining = int(oldest + self._group_window - now) + 1
            return False, max(remaining, 1)
        return True, None

    def record(self, user_id: int, group_id: int) -> None:
        """Зафиксировать успешный запрос."""
        now = time.time()
        self._user_requests[user_id].append(now)
        self._group_requests[group_id].append(now)


# ---------------------------------------------------------------------------
# Конфигурация групп
# ---------------------------------------------------------------------------

def load_groups() -> List[dict]:
    """
    Загрузить список активных групп из JSON-конфига.

    Группы с ``disabled: true`` исключаются из результата.

    Returns:
        Список словарей {"id": int, "title": str}.
    """
    if not GROUPS_CONFIG_PATH.exists():
        return []
    try:
        with open(GROUPS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        all_groups = data.get("groups", [])
        enabled = [g for g in all_groups if not g.get("disabled", False)]
        if len(enabled) < len(all_groups):
            logger.info(
                "Отфильтровано %d отключённых Helper-групп из %d",
                len(all_groups) - len(enabled),
                len(all_groups),
            )
        return enabled
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Ошибка чтения %s: %s", GROUPS_CONFIG_PATH, exc)
        return []


def save_groups(groups: List[dict]) -> None:
    """Сохранить список групп в JSON-конфиг."""
    with open(GROUPS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"groups": groups}, f, ensure_ascii=False, indent=4)
    logger.info("Сохранено %d групп(а) в %s", len(groups), GROUPS_CONFIG_PATH)


def get_group_ids(groups: List[dict]) -> List[int]:
    """Извлечь ID групп из конфигурации."""
    return [g["id"] for g in groups if isinstance(g.get("id"), int)]


def parse_index_selection(raw_value: str, max_index: int) -> List[int]:
    """
    Распарсить ввод номеров элементов в формате "1,3-5".

    Args:
        raw_value: Строка ввода пользователя.
        max_index: Максимально допустимый индекс (включительно).

    Returns:
        Отсортированный список уникальных индексов (1-based).

    Raises:
        ValueError: Если формат ввода некорректный.
    """
    value = (raw_value or "").strip()
    if not value:
        return []

    selected: set[int] = set()
    for chunk in value.split(","):
        part = chunk.strip()
        if not part:
            continue

        if "-" in part:
            left, right = [x.strip() for x in part.split("-", 1)]
            if not left.isdigit() or not right.isdigit():
                raise ValueError("Диапазон должен содержать только числа")
            start, end = int(left), int(right)
            if start > end:
                raise ValueError("Начало диапазона не может быть больше конца")
            for idx in range(start, end + 1):
                if idx < 1 or idx > max_index:
                    raise ValueError(f"Номер {idx} вне допустимого диапазона 1..{max_index}")
                selected.add(idx)
            continue

        if not part.isdigit():
            raise ValueError("Номера должны быть целыми числами")
        idx = int(part)
        if idx < 1 or idx > max_index:
            raise ValueError(f"Номер {idx} вне допустимого диапазона 1..{max_index}")
        selected.add(idx)

    return sorted(selected)


async def get_user_groups(client: TelegramClient) -> List[dict]:
    """
    Получить список групп и супергрупп, где состоит авторизованный пользователь.

    Returns:
        Список словарей вида {"id": int, "title": str}, отсортированный по title.
    """
    dialogs = await client.get_dialogs(limit=None)
    groups_by_id: Dict[int, dict] = {}

    for dialog in dialogs:
        if not getattr(dialog, "is_group", False):
            continue

        try:
            chat_id = int(get_peer_id(dialog.entity))
        except Exception:
            continue

        title = (dialog.name or "").strip() or str(chat_id)
        groups_by_id[chat_id] = {"id": chat_id, "title": title}

    return sorted(groups_by_id.values(), key=lambda x: x["title"].lower())


# ---------------------------------------------------------------------------
# Разбиение длинных сообщений
# ---------------------------------------------------------------------------

def split_message(text: str, max_len: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> List[str]:
    """
    Разбить длинный MarkdownV2-текст на части для Telegram.

    Разбиение производится по переносу строки, затем по пробелу.
    Не допускается завершение чанка одинарным обратным слэшем.
    """
    if len(text) <= max_len:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_len:
            chunk = remaining
            remaining = ""
        else:
            chunk = remaining[:max_len]
            split_idx = chunk.rfind("\n")
            if split_idx < int(max_len * 0.5):
                split_idx = chunk.rfind(" ")
            if split_idx > 0:
                chunk = remaining[:split_idx]
                remaining = remaining[split_idx:].lstrip("\n ")
            else:
                remaining = remaining[max_len:]

        if chunk.endswith("\\") and remaining:
            chunk = chunk[:-1]
            remaining = "\\" + remaining

        if chunk:
            chunks.append(chunk)

    return chunks or [text]


# ---------------------------------------------------------------------------
# Безопасное редактирование сообщения
# ---------------------------------------------------------------------------

async def _edit_safe(client: TelegramClient, chat_id: int, msg_id: int, text: str) -> None:
    """
    Отредактировать сообщение с markdown, при ошибке парсинга — plain text fallback.

    Args:
        client: Telethon-клиент.
        chat_id: ID чата.
        msg_id: ID сообщения.
        text: Новый текст (может быть в MarkdownV2-экранировании).
    """
    prepared = _prepare_html_for_telethon(text)
    try:
        await client.edit_message(
            chat_id,
            msg_id,
            prepared,
            parse_mode=telethon_html,
        )
    except Exception as exc:
        exc_msg = str(exc)
        if "parse" in exc_msg.lower() or "entity" in exc_msg.lower():
            logger.warning(
                "MarkdownV2 parse failed on edit, fallback to plain text: %s "
                "(msg_id=%s, chat_id=%s)",
                exc, msg_id, chat_id,
            )
            plain = _prepare_markdown_for_telethon(text)
            try:
                await client.edit_message(chat_id, msg_id, plain)
            except Exception as plain_exc:
                logger.error(
                    "Plain text edit also failed: %s (msg_id=%s, chat_id=%s)",
                    plain_exc, msg_id, chat_id,
                )
        else:
            logger.error(
                "edit_message failed: %s (msg_id=%s, chat_id=%s)",
                exc, msg_id, chat_id,
            )


# ---------------------------------------------------------------------------
# Обработка /helpme
# ---------------------------------------------------------------------------

async def handle_help(
    event: events.NewMessage.Event,
    client: TelegramClient,
    rate_limiter: HelperRateLimiter,
) -> None:
    """
    Обработать команду /helpme в группе.

    Маршрутизация:
        1. Голый /helpme (ответ на сообщение) → RAG по тексту сообщения-оригинала.
        2. /helpme <текст> → полная AI-маршрутизация (RAG или UPOS).
        3. Голый /helpme без ответа → подсказка по использованию.
    """
    chat_id = event.chat_id
    user_id = event.sender_id
    message_date = event.message.date

    # --- Пропускаем старые сообщения (при реконнекте) ---
    if message_date:
        from datetime import timezone
        age = (datetime.now(timezone.utc) - message_date).total_seconds()
        if age > MAX_MESSAGE_AGE_SECONDS:
            logger.debug("Пропуск старого сообщения: age=%.0fs, chat=%s", age, chat_id)
            return

    # --- Пропускаем ботов ---
    sender = await event.get_sender()
    if sender and getattr(sender, "bot", False):
        logger.debug("Пропуск сообщения бота: sender=%s, chat=%s", user_id, chat_id)
        return

    # --- Парсинг команды ---
    match = HELP_COMMAND_RE.match(event.raw_text or "")
    if not match:
        return

    query_text = (match.group(1) or "").strip()
    is_reply = event.message.reply_to is not None
    reply_msg_id = getattr(event.message.reply_to, "reply_to_msg_id", None) if is_reply else None
    direct_rag = False  # Флаг: напрямую в RAG, без полного роутера

    if not query_text and is_reply and reply_msg_id:
        # Голый /helpme в ответ на сообщение → берём текст оригинала
        try:
            replied = await client.get_messages(chat_id, ids=reply_msg_id)
            if replied and replied.text:
                query_text = replied.text.strip()
                direct_rag = True
            else:
                logger.info(
                    "Ответ на сообщение без текста: chat=%s, reply_to=%s",
                    chat_id, reply_msg_id,
                )
        except Exception as fetch_exc:
            logger.warning(
                "Не удалось получить сообщение-оригинал: chat=%s, reply_to=%s, error=%s",
                chat_id, reply_msg_id, fetch_exc,
            )

    if not query_text:
        # Голый /helpme без текста и без ответа → подсказка
        try:
            await _reply_safe(event, MSG_USAGE_HINT)
        except Exception as hint_exc:
            logger.warning("Не удалось отправить подсказку: %s", hint_exc)
            try:
                await event.reply(_prepare_markdown_for_telethon(MSG_USAGE_HINT))
            except Exception:
                pass
        return

    # --- Rate-limit check ---
    user_ok, user_remaining = rate_limiter.check_user(user_id)
    if not user_ok:
        logger.info("Rate-limit пользователя: user=%s, remaining=%ss", user_id, user_remaining)
        msg = MSG_RATE_LIMIT_USER.format(seconds=str(user_remaining))
        try:
            await _reply_safe(event, msg)
        except Exception:
            await event.reply(_prepare_markdown_for_telethon(msg))
        return

    group_ok, group_remaining = rate_limiter.check_group(chat_id)
    if not group_ok:
        logger.info("Rate-limit группы: chat=%s, remaining=%ss", chat_id, group_remaining)
        msg = MSG_RATE_LIMIT_GROUP.format(seconds=str(group_remaining))
        try:
            await _reply_safe(event, msg)
        except Exception:
            await event.reply(_prepare_markdown_for_telethon(msg))
        return

    # --- Фиксируем запрос ---
    rate_limiter.record(user_id, chat_id)
    logger.info(
        "Обработка /helpme: user=%s, chat=%s, direct_rag=%s, query_preview=%.80s",
        user_id, chat_id, direct_rag, mask_sensitive_data(query_text[:80]),
    )

    # --- Отправляем плейсхолдер ---
    placeholder = None
    try:
        placeholder = await _reply_safe(event, MSG_PROCESSING)
    except Exception as ph_exc:
        logger.warning("Не удалось отправить плейсхолдер: %s", ph_exc)
        try:
            placeholder = await event.reply(_prepare_markdown_for_telethon(MSG_PROCESSING))
        except Exception as ph2_exc:
            logger.error("Полный сбой отправки плейсхолдера: %s", ph2_exc)
            return

    # --- Обрезаем длинный текст ---
    if len(query_text) > MAX_QUERY_LENGTH:
        query_text = query_text[:MAX_QUERY_LENGTH]

    # --- Вызов AI-пайплайна ---
    response: Optional[str] = None
    status: str = "error"
    progress_callback = _make_progress_callback(client, chat_id, placeholder.id)

    try:
        if direct_rag:
            await _edit_safe(client, chat_id, placeholder.id, MSG_WAITING_AI)
            response, status = await _run_rag_only(
                query_text,
                user_id=user_id,
                on_progress=progress_callback,
            )
        else:
            # Полный роутер (RAG / UPOS / другие)
            from src.sbs_helper_telegram_bot.ai_router.intent_router import get_router

            router = get_router()
            classified_intent: Optional[str] = None
            base_classified_callback = _make_classified_callback(client, chat_id, placeholder.id)

            async def _on_classified_limited(classification) -> None:
                """Сохранить классифицированный intent и обновить плейсхолдер."""
                nonlocal classified_intent
                classified_intent = (getattr(classification, "intent", "") or "").strip()
                await base_classified_callback(classification)

            response, status = await router.route(
                query_text,
                user_id,
                on_classified=_on_classified_limited,
                on_progress=progress_callback,
            )

            if classified_intent and classified_intent not in HELPER_ALLOWED_INTENTS:
                logger.info(
                    "THE_HELPER intent ограничен allowlist: intent=%s, fallback=rag_qa",
                    classified_intent,
                )
                await _edit_safe(client, chat_id, placeholder.id, MSG_WAITING_AI)
                response, status = await _run_rag_only(
                    query_text,
                    user_id=user_id,
                    on_progress=progress_callback,
                )
    except Exception as route_exc:
        logger.error(
            "Ошибка AI-маршрутизации: user=%s, chat=%s, error=%s",
            user_id, chat_id, route_exc, exc_info=True,
        )
        response = None
        status = "error"

    # --- Отправляем ответ ---
    try:
        if response and status in ("routed", "chat", "rate_limited", "module_disabled"):
            prepared_response = _prepare_markdown_for_telethon(response)
            chunks = split_message(prepared_response)
            await _edit_safe(client, chat_id, placeholder.id, chunks[0])
            for chunk in chunks[1:]:
                try:
                    await _send_message_safe(client, chat_id, chunk, reply_to=event.message.id)
                except Exception:
                    await client.send_message(chat_id, chunk, reply_to=event.message.id)
        else:
            # Сообщение об ошибке / отсутствии ответа
            fallback = _get_fallback_message(status)
            await _edit_safe(client, chat_id, placeholder.id, fallback)
    except Exception as send_exc:
        logger.error(
            "Ошибка отправки ответа: user=%s, chat=%s, error=%s",
            user_id, chat_id, send_exc, exc_info=True,
        )
        try:
            await _edit_safe(client, chat_id, placeholder.id, MSG_ERROR)
        except Exception:
            pass

    logger.info(
        "Завершена обработка /helpme: user=%s, chat=%s, status=%s, "
        "response_len=%d",
        user_id, chat_id, status, len(response) if response else 0,
    )


async def _run_rag_only(
    query_text: str,
    user_id: int,
    on_progress=None,
) -> Tuple[Optional[str], str]:
    """
    Выполнить прямой RAG-запрос и вернуть результат в формате роутера.

    Returns:
        Кортеж (response, status), где status совместим со статусами router.route.
    """
    from src.core.ai.rag_service import get_rag_service
    from src.core.ai.formatters import format_rag_answer_markdown_v2

    rag_service = get_rag_service()
    rag_answer = await rag_service.answer_question(
        query_text,
        user_id=user_id,
        on_progress=on_progress,
    )

    if rag_answer and rag_answer.text:
        safe = format_rag_answer_markdown_v2(rag_answer.text)
        return f"📚 *Ответ по базе знаний*\n\n{safe}", "routed"

    return None, "low_confidence"


def _get_fallback_message(status: str) -> str:
    """Вернуть fallback-сообщение по статусу AI-маршрутизации."""
    from src.sbs_helper_telegram_bot.ai_router.messages import (
        get_ai_status_message,
    )  # Остаётся в ai_router — бот-специфичная функция
    msg = get_ai_status_message(status)
    if msg:
        return msg
    return MSG_ERROR


def _make_classified_callback(client, chat_id, msg_id):
    """Создать callback на событие классификации — обновить плейсхолдер."""
    async def _on_classified(classification) -> None:
        intent = getattr(classification, "intent", "")
        if intent == "rag_qa":
            try:
                await _edit_safe(client, chat_id, msg_id, MSG_WAITING_AI)
            except Exception as exc:
                logger.warning("Не удалось обновить плейсхолдер при классификации: %s", exc)
    return _on_classified


def _make_progress_callback(client, chat_id, msg_id):
    """Создать callback на события прогресса RAG — обновить плейсхолдер."""
    _upos_notice_sent = {"sent": False}

    async def _on_progress(stage: str, payload=None) -> None:
        stage_messages = {
            "rag_prefilter_started": MSG_PREFILTERING,
            "rag_augmented_request_started": MSG_AUGMENTED,
            "rag_fallback_started": MSG_AUGMENTED,
        }

        if stage == "upos_not_found_fallback_started":
            if _upos_notice_sent["sent"]:
                return
            _upos_notice_sent["sent"] = True
            try:
                await _send_message_safe(client, chat_id, MSG_UPOS_FALLBACK, reply_to=msg_id)
            except Exception as exc:
                logger.warning("Не удалось отправить UPOS fallback notice: %s", exc)
            return

        stage_msg = stage_messages.get(stage)
        if stage_msg:
            try:
                await _edit_safe(client, chat_id, msg_id, stage_msg)
            except Exception as exc:
                logger.warning(
                    "Не удалось обновить плейсхолдер на этапе %s: %s", stage, exc
                )

    return _on_progress


# ---------------------------------------------------------------------------
# Интерактивное управление группами (CLI)
# ---------------------------------------------------------------------------

async def manage_groups_interactive() -> None:
    """Интерактивный CLI для управления списком групп THE_HELPER."""
    print("\n🔧 THE_HELPER — Управление группами\n")

    session_path = str(PROJECT_ROOT / HELPER_SESSION_NAME)
    client = await start_telegram_client_with_logging(
        session_path=session_path,
        api_id=TELETHON_API_ID,
        api_hash=TELETHON_API_HASH,
        logger=logger,
        interactive=False,
    )
    if not client:
        logger.error(
            "Не удалось запустить THE_HELPER: отсутствует/невалидна Telethon-сессия. "
            "Создайте сессию командой: python scripts/the_helper.py --manage-groups",
        )
        sys.exit(1)
    await client.start()

    groups = load_groups()
    user_groups = await get_user_groups(client)

    def _print_current_groups() -> None:
        """Вывести текущий список отслеживаемых групп."""
        print("Текущие отслеживаемые группы:")
        if groups:
            for i, g in enumerate(groups, 1):
                print(f"  {i}. {g.get('title', 'Без названия')} (ID: {g['id']})")
        else:
            print("  (список пуст)")

    def _print_user_groups() -> None:
        """Вывести список групп пользователя с отметкой выбранных."""
        configured_ids = set(get_group_ids(groups))
        print("Мои группы и супергруппы:")
        if not user_groups:
            print("  (группы не найдены)")
            return
        for i, g in enumerate(user_groups, 1):
            mark = "[x]" if g["id"] in configured_ids else "[ ]"
            print(f"  {i}. {mark} {g['title']} (ID: {g['id']})")

    def _not_configured_user_groups() -> List[dict]:
        """Получить группы пользователя, ещё не добавленные в отслеживание."""
        configured_ids = set(get_group_ids(groups))
        return [g for g in user_groups if g["id"] not in configured_ids]

    while True:
        print("\n" + "=" * 50)
        _print_current_groups()
        print()
        print(f"Групп в аккаунте: {len(user_groups)}")
        print("Действия:")
        print("  1. Показать мои группы")
        print("  2. Добавить группы из моего аккаунта")
        print("  3. Добавить группу вручную (ID / @username / ссылка)")
        print("  4. Удалить группу из отслеживания")
        print("  5. Обновить список моих групп")
        print("  6. Сохранить и выйти")
        print("  7. Выйти без сохранения")
        print()

        choice = input("Выберите действие (1-7): ").strip()

        if choice == "1":
            _print_user_groups()

        elif choice == "2":
            candidates = _not_configured_user_groups()
            if not candidates:
                print("ℹ️  Все найденные группы уже добавлены в отслеживание.")
                continue

            print("Доступные для добавления группы:")
            for i, g in enumerate(candidates, 1):
                print(f"  {i}. {g['title']} (ID: {g['id']})")

            selected_raw = input(
                "Введите номера для добавления (например: 1,3-5), Enter — отмена: "
            ).strip()
            if not selected_raw:
                print("↩️  Добавление отменено.")
                continue

            try:
                selected_indexes = parse_index_selection(selected_raw, len(candidates))
            except ValueError as exc:
                print(f"❌ {exc}")
                continue

            added_count = 0
            for idx in selected_indexes:
                candidate = candidates[idx - 1]
                if any(g["id"] == candidate["id"] for g in groups):
                    continue
                groups.append({"id": candidate["id"], "title": candidate["title"]})
                added_count += 1

            print(f"✅ Добавлено групп: {added_count}")

        elif choice == "3":
            group_input = input(
                "Введите ID группы, username или ссылку (например, -100123456 или @group): "
            ).strip()
            if not group_input:
                print("❌ Пустой ввод.")
                continue

            # Проверяем дубликат по ID, если это число
            try:
                numeric_id = int(group_input)
                if any(g["id"] == numeric_id for g in groups):
                    print(f"⚠️  Группа с ID {numeric_id} уже в списке.")
                    continue
            except ValueError:
                numeric_id = None

            try:
                entity = await client.get_entity(
                    numeric_id if numeric_id is not None else group_input
                )
                resolved_id = entity.id
                # Добавляем -100 префикс для каналов/супергрупп
                if hasattr(entity, "megagroup") or hasattr(entity, "broadcast"):
                    if resolved_id > 0:
                        resolved_id = int(f"-100{resolved_id}")
                elif hasattr(entity, "chat_id"):
                    if resolved_id > 0:
                        resolved_id = -resolved_id

                title = getattr(entity, "title", str(resolved_id))

                if any(g["id"] == resolved_id for g in groups):
                    print(f"⚠️  Группа «{title}» (ID: {resolved_id}) уже в списке.")
                    continue

                groups.append({"id": resolved_id, "title": title})
                print(f"✅ Добавлена: {title} (ID: {resolved_id})")
            except Exception as exc:
                print(f"❌ Не удалось найти группу: {exc}")

        elif choice == "4":
            if not groups:
                print("❌ Список пуст, нечего удалять.")
                continue

            print("Группы для удаления:")
            for i, g in enumerate(groups, 1):
                print(f"  {i}. {g.get('title', 'N/A')} (ID: {g['id']})")

            idx_str = input(
                "Введите номера для удаления (например: 1,3), Enter — отмена: "
            ).strip()
            if not idx_str:
                print("↩️  Удаление отменено.")
                continue

            try:
                selected_indexes = parse_index_selection(idx_str, len(groups))
            except ValueError as exc:
                print(f"❌ {exc}")
                continue

            removed_items = [groups[i - 1] for i in selected_indexes]
            groups = [g for i, g in enumerate(groups, 1) if i not in set(selected_indexes)]

            print(f"✅ Удалено групп: {len(removed_items)}")
            for removed in removed_items:
                print(f"   • {removed.get('title', 'N/A')} (ID: {removed['id']})")

        elif choice == "5":
            user_groups = await get_user_groups(client)
            print(f"🔄 Список групп обновлён: найдено {len(user_groups)}")

        elif choice == "6":
            save_groups(groups)
            print("✅ Сохранено и выход.")
            break

        elif choice == "7":
            print("↩️  Выход без сохранения.")
            break

        else:
            print("❌ Неверный выбор, повторите.")

    await client.disconnect()


# ---------------------------------------------------------------------------
# Основной слушатель
# ---------------------------------------------------------------------------

async def run_listener() -> None:
    """Запустить Telethon-слушатель /helpme в настроенных группах."""
    await asyncio.to_thread(preload_rag_runtime_dependencies)

    groups = load_groups()
    group_ids = get_group_ids(groups)

    if not group_ids:
        logger.error(
            "Список групп пуст. Запустите: python scripts/the_helper.py --manage-groups"
        )
        sys.exit(1)

    if not TELETHON_API_ID or not TELETHON_API_HASH:
        logger.error(
            "TELETHON_API_ID и TELETHON_API_HASH должны быть заданы в .env"
        )
        sys.exit(1)

    session_path = str(PROJECT_ROOT / HELPER_SESSION_NAME)
    client = await start_telegram_client_with_logging(
        session_path=session_path,
        api_id=TELETHON_API_ID,
        api_hash=TELETHON_API_HASH,
        logger=logger,
        interactive=False,
    )
    if not client:
        logger.error(
            "Не удалось запустить THE_HELPER: Telethon-сессия отсутствует или не авторизована. "
            "Создайте/обновите сессию командой: python scripts/the_helper.py --manage-groups"
        )
        sys.exit(1)

    rate_limiter = HelperRateLimiter()

    logger.info("Запуск THE_HELPER...")
    logger.info("Отслеживаемые группы (%d):", len(group_ids))
    for g in groups:
        logger.info("  • %s (ID: %s)", g.get("title", "N/A"), g["id"])
    logger.info(
        "Rate-limit: user=%d/%ds, group=%d/%ds",
        HELPER_RATE_LIMIT_USER_MAX, HELPER_RATE_LIMIT_USER_WINDOW,
        HELPER_RATE_LIMIT_GROUP_MAX, HELPER_RATE_LIMIT_GROUP_WINDOW,
    )

    @client.on(events.NewMessage(
        chats=group_ids,
        pattern=HELP_COMMAND_RE,
    ))
    async def on_help_message(event: events.NewMessage.Event) -> None:
        """Обработчик новых сообщений /helpme в группах."""
        try:
            await handle_help(event, client, rate_limiter)
        except Exception as exc:
            logger.error(
                "Необработанная ошибка в handle_help: chat=%s, user=%s, error=%s",
                event.chat_id, event.sender_id, exc, exc_info=True,
            )
            # Пытаемся ответить об ошибке
            try:
                await _reply_safe(event, MSG_ERROR)
            except Exception:
                try:
                    await event.reply(_prepare_markdown_for_telethon(MSG_ERROR))
                except Exception:
                    pass

    logger.info("✅ THE_HELPER запущен и слушает /helpme в %d группах.", len(group_ids))

    # Корректное завершение
    stop_event = asyncio.Event()

    def _signal_handler(sig, frame):
        logger.info("Получен сигнал %s, завершение...", sig)
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("Отключение Telethon-клиента...")
        await client.disconnect()
        logger.info("✅ THE_HELPER остановлен.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(
        description="THE_HELPER — мониторинг /helpme в Telegram-группах",
    )
    parser.add_argument(
        "--manage-groups",
        action="store_true",
        help="Интерактивное управление списком групп",
    )
    args = parser.parse_args()

    if args.manage_groups:
        asyncio.run(manage_groups_interactive())
    else:
        asyncio.run(run_listener())


if __name__ == "__main__":
    main()
