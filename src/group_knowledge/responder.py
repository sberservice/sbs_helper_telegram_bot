"""
Автоответчик для Telegram-групп на основе базы Q&A-пар.

Слушает новые сообщения в настроенных группах, определяет
является ли сообщение вопросом, ищет ответ в базе знаний
и отвечает (или логирует в dry-run режиме).
"""

import asyncio
import logging
import re
import time
from collections import defaultdict
from typing import Dict, List, Optional

from config import ai_settings
from src.common.constants.sync import (
    GK_RATE_LIMIT_USER_MAX,
    GK_RATE_LIMIT_USER_WINDOW,
    GK_RATE_LIMIT_GROUP_MAX,
    GK_RATE_LIMIT_GROUP_WINDOW,
)
from src.group_knowledge import database as gk_db
from src.group_knowledge.models import ResponderResult
from src.group_knowledge.qa_search import QASearchService
from src.group_knowledge.settings import (
    MIN_QUESTION_LENGTH,
    QUESTION_KEYWORDS_RU,
    MAX_MESSAGE_AGE_SECONDS,
)

logger = logging.getLogger(__name__)


class GKRateLimiter:
    """
    Rate limiter со скользящим окном для автоответчика.

    Ограничивает количество ответов на уровне пользователя и группы.
    """

    def __init__(self):
        """Инициализация rate limiter."""
        self._user_timestamps: Dict[int, List[float]] = defaultdict(list)
        self._group_timestamps: Dict[int, List[float]] = defaultdict(list)

    def check_user(self, user_id: int) -> Optional[int]:
        """
        Проверить rate limit для пользователя.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            None если запрос разрешён, иначе число секунд ожидания.
        """
        return self._check(
            self._user_timestamps[user_id],
            GK_RATE_LIMIT_USER_MAX,
            GK_RATE_LIMIT_USER_WINDOW,
        )

    def check_group(self, group_id: int) -> Optional[int]:
        """
        Проверить rate limit для группы.

        Args:
            group_id: Telegram ID группы.

        Returns:
            None если запрос разрешён, иначе число секунд ожидания.
        """
        return self._check(
            self._group_timestamps[group_id],
            GK_RATE_LIMIT_GROUP_MAX,
            GK_RATE_LIMIT_GROUP_WINDOW,
        )

    def record(self, user_id: int, group_id: int) -> None:
        """
        Записать факт ответа.

        Args:
            user_id: Telegram ID пользователя.
            group_id: Telegram ID группы.
        """
        now = time.time()
        self._user_timestamps[user_id].append(now)
        self._group_timestamps[group_id].append(now)

    @staticmethod
    def _check(timestamps: List[float], max_count: int, window: int) -> Optional[int]:
        """Проверить скользящее окно."""
        now = time.time()
        cutoff = now - window

        # Очистить устаревшие
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if len(timestamps) >= max_count:
            wait_seconds = int(timestamps[0] + window - now) + 1
            return max(1, wait_seconds)

        return None


class GroupResponder:
    """
    Автоответчик для Telegram-групп.

    Анализирует входящие сообщения, определяет вопросы и
    отвечает на них используя базу Q&A-пар.
    """

    def __init__(
        self,
        dry_run: bool = True,
        qa_service: Optional[QASearchService] = None,
        confidence_threshold: Optional[float] = None,
    ):
        """
        Инициализация автоответчика.

        Args:
            dry_run: Режим dry-run (не отправлять реальные ответы).
            qa_service: Сервис поиска Q&A (создаётся по умолчанию).
            confidence_threshold: Минимальная уверенность для ответа.
        """
        self._dry_run = dry_run
        self._qa_service = qa_service or QASearchService()
        self._confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else ai_settings.GK_RESPONDER_CONFIDENCE_THRESHOLD
        )
        self._rate_limiter = GKRateLimiter()
        self._stop_event = asyncio.Event()

    @property
    def dry_run(self) -> bool:
        """Режим dry-run."""
        return self._dry_run

    async def handle_message(
        self,
        event,
        group_ids: set,
    ) -> Optional[ResponderResult]:
        """
        Обработать новое сообщение и решить, нужно ли отвечать.

        Args:
            event: Telethon NewMessage event.
            group_ids: Множество отслеживаемых group_id.

        Returns:
            ResponderResult или None, если ответ не требуется.
        """
        message = event.message

        # Пропустить служебные
        if not message or message.action:
            return None

        # Извлечь chat_id
        chat = event.chat
        if not chat:
            return None
        chat_id = self._resolve_chat_id(chat)

        if chat_id not in group_ids:
            return None

        # Пропустить старые сообщения
        if message.date:
            msg_age = time.time() - message.date.timestamp()
            if msg_age > MAX_MESSAGE_AGE_SECONDS:
                return None

        # Пропустить reply (скорее всего, это ответ, а не вопрос)
        if message.reply_to:
            return None

        # Пропустить ботов
        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            return None

        sender_id = getattr(sender, "id", 0) if sender else 0

        # Пропустить команды
        text = message.text or message.message or ""
        if text.startswith("/"):
            return None

        # Определить, похоже ли на вопрос
        if not self._looks_like_question(text):
            return None

        # Rate limit: пользователь
        user_wait = self._rate_limiter.check_user(sender_id)
        if user_wait is not None:
            logger.debug(
                "Rate limit (user): user=%d wait=%ds",
                sender_id, user_wait,
            )
            return None

        # Rate limit: группа
        group_wait = self._rate_limiter.check_group(chat_id)
        if group_wait is not None:
            logger.debug(
                "Rate limit (group): group=%d wait=%ds",
                chat_id, group_wait,
            )
            return None

        # Поиск ответа в Q&A базе
        answer_result = await self._qa_service.answer_question(text)
        if not answer_result:
            logger.debug("Ответ не найден: group=%d msg=%d", chat_id, message.id)
            return None

        answer_text = answer_result["answer"]
        confidence = answer_result["confidence"]
        source_ids = answer_result.get("source_pair_ids", [])
        primary_source_link = answer_result.get("primary_source_link")

        if primary_source_link:
            answer_text = (
                f"{answer_text}\n\n"
                f"Похожий случай в группе: {primary_source_link}"
            )

        # Проверить порог уверенности
        if confidence < self._confidence_threshold:
            logger.info(
                "Уверенность ниже порога: conf=%.2f threshold=%.2f msg=%d",
                confidence, self._confidence_threshold, message.id,
            )
            return None

        # Записать rate limit
        self._rate_limiter.record(sender_id, chat_id)

        # Создать результат
        result = ResponderResult(
            question_text=text,
            answer_text=answer_text,
            confidence=confidence,
            source_qa_pair_ids=source_ids,
            dry_run=self._dry_run,
        )

        # Логировать
        gk_db.store_responder_log(
            group_id=chat_id,
            question_message_id=message.id,
            question_text=text,
            answer_text=answer_text,
            qa_pair_id=source_ids[0] if source_ids else None,
            confidence=confidence,
            dry_run=self._dry_run,
        )

        if self._dry_run:
            logger.info(
                "DRY-RUN: Ответил бы на msg %d в группе %d "
                "(conf=%.2f, sources=%s):\n"
                "  Вопрос: %s\n"
                "  Ответ: %s",
                message.id, chat_id,
                confidence, source_ids,
                text[:200],
                answer_text[:300],
            )
        else:
            # Отправить ответ
            try:
                await event.reply(answer_text)
                result.responded = True
                logger.info(
                    "Ответ отправлен: msg=%d group=%d conf=%.2f",
                    message.id, chat_id, confidence,
                )
            except Exception as exc:
                logger.error(
                    "Ошибка отправки ответа: msg=%d error=%s",
                    message.id, exc,
                    exc_info=True,
                )

        return result

    def stop(self) -> None:
        """Послать сигнал остановки."""
        self._stop_event.set()

    @staticmethod
    def _looks_like_question(text: str) -> bool:
        """
        Эвристика: похоже ли сообщение на вопрос.

        Args:
            text: Текст сообщения.

        Returns:
            True если сообщение похоже на вопрос.
        """
        if not text or len(text.strip()) < MIN_QUESTION_LENGTH:
            return False

        text_lower = text.lower().strip()

        # Явный знак вопроса
        if "?" in text:
            return True

        # Начинается с вопросительного слова
        first_word = text_lower.split()[0] if text_lower.split() else ""
        if first_word in QUESTION_KEYWORDS_RU:
            return True

        # Содержит вопросительные конструкции
        question_patterns = [
            r"\bкак\s+(можно|сделать|настроить|решить|починить|устранить|исправить)",
            r"\bчто\s+(делать|значит|означает|показывает|за\s+ошибка)",
            r"\bпочему\s+(не\s+работает|выдаёт|показывает|появляется)",
            r"\bкто\s+(знает|подскажет|сталкивался|может)",
            r"\bподскажите",
            r"\bпомогите",
            r"\bне\s+(работает|включается|загружается|отвечает|подключается)",
            r"\bошибка\b",
            r"\bпроблема\b",
        ]

        for pattern in question_patterns:
            if re.search(pattern, text_lower):
                return True

        return False

    @staticmethod
    def _resolve_chat_id(chat) -> int:
        """Извлечь chat_id, учитывая формат для супергрупп."""
        chat_id = getattr(chat, "id", 0)
        if chat_id > 0:
            if getattr(chat, "megagroup", False) or getattr(chat, "broadcast", False):
                return -int(f"100{chat_id}")
            return -chat_id
        return chat_id
