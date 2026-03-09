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
from typing import Any, Dict, List, Optional

from config import ai_settings
from src.common.constants.sync import (
    GK_RATE_LIMIT_USER_MAX,
    GK_RATE_LIMIT_USER_WINDOW,
    GK_RATE_LIMIT_GROUP_MAX,
    GK_RATE_LIMIT_GROUP_WINDOW,
)
from src.group_knowledge import database as gk_db
from src.group_knowledge.models import ResponderResult
from src.group_knowledge.question_classifier import QuestionClassifierService
from src.group_knowledge.qa_search import QASearchService
from src.group_knowledge.settings import (
    GK_IGNORED_SENDER_IDS,
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
        test_group_mapping: Optional[Dict[int, int]] = None,
        redirect_output_group: Optional[Dict[str, Any]] = None,
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
        self._question_classifier = QuestionClassifierService()
        self._test_group_mapping = {
            int(group_id): int(real_group_id)
            for group_id, real_group_id in (test_group_mapping or {}).items()
        }
        self._redirect_output_group = dict(redirect_output_group or {})
        self._redirect_output_group_id = self._parse_group_id(
            self._redirect_output_group.get("id")
        )

    @property
    def dry_run(self) -> bool:
        """Режим dry-run."""
        return self._dry_run

    def preload_search_resources(self, preload_vector_model: bool = True) -> Dict[str, Any]:
        """Предзагрузить поисковые ресурсы Q&A сервиса перед запуском listener."""
        return self._qa_service.warmup(preload_vector_model=preload_vector_model)

    async def handle_message(
        self,
        event,
        group_ids: set,
        question_override: Optional[str] = None,
        force_as_question: bool = False,
    ) -> Optional[ResponderResult]:
        """
        Обработать новое сообщение и решить, нужно ли отвечать.

        Args:
            event: Telethon NewMessage event.
            group_ids: Множество отслеживаемых group_id.
            question_override: Явный текст вопроса (например, из команды /qa).

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

        effective_group_id = self._resolve_effective_group_id(chat_id)

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
            logger.info(
                "Автоответчик пропускает сообщение: sender бот group=%d actual_group=%d msg=%d",
                effective_group_id,
                chat_id,
                message.id,
            )
            return None

        sender_id = getattr(sender, "id", 0) if sender else 0
        if sender_id in GK_IGNORED_SENDER_IDS and chat_id not in self._test_group_mapping:
            logger.info(
                "Автоответчик пропускает сообщение: sender в GK_IGNORED_SENDER_IDS sender=%d group=%d actual_group=%d msg=%d ignored=%s",
                sender_id,
                effective_group_id,
                chat_id,
                message.id,
                sorted(GK_IGNORED_SENDER_IDS),
            )
            return None
        if sender_id in GK_IGNORED_SENDER_IDS and chat_id in self._test_group_mapping:
            logger.info(
                "Автоответчик: sender=%d в ignored, но chat=%d запущен в test-mode — пропуск отключён",
                sender_id,
                chat_id,
            )

        # Пропустить команды
        text = (question_override if question_override is not None else (message.text or message.message or "")).strip()
        if question_override is None and text.startswith("/"):
            return None

        # Определить, является ли сообщение вопросом
        if not await self._is_question_message(text, force_as_question=force_as_question):
            logger.info(
                "Автоответчик пропускает сообщение: не распознано как вопрос group=%d actual_group=%d msg=%d text=%s",
                effective_group_id,
                chat_id,
                message.id,
                text[:160],
            )
            return None

        logger.info(
            "Запуск RAG-поиска: group=%d actual_group=%d msg=%d dry_run=%s text=%s",
            effective_group_id,
            chat_id,
            message.id,
            self._dry_run,
            text[:200],
        )

        # Rate limit: пользователь
        user_wait = self._rate_limiter.check_user(sender_id)
        if user_wait is not None:
            logger.debug(
                "Rate limit (user): user=%d wait=%ds",
                sender_id, user_wait,
            )
            return None

        # Rate limit: группа
        group_wait = self._rate_limiter.check_group(effective_group_id)
        if group_wait is not None:
            logger.debug(
                "Rate limit (group): group=%d wait=%ds actual_group=%d",
                effective_group_id, group_wait, chat_id,
            )
            return None

        # Поиск ответа в Q&A базе
        answer_result = await self._qa_service.answer_question(text)
        if not answer_result:
            logger.info(
                "RAG не нашёл ответ: group=%d actual_group=%d msg=%d text=%s",
                effective_group_id,
                chat_id,
                message.id,
                text[:200],
            )
            return None

        format_answer = getattr(self._qa_service, "format_answer_for_user", None)
        answer_text = ""
        if callable(format_answer):
            answer_text = format_answer(answer_result)
        if not isinstance(answer_text, str) or not answer_text.strip():
            answer_text = answer_result.get("answer", "")
            primary_source_link = answer_result.get("primary_source_link")
            if primary_source_link:
                answer_text = (
                    f"**Отвечает робот Арчи**: {answer_text}\n\n"
                    f"Похожий случай в группе, ссылка на ответ: {primary_source_link}"
                )
        confidence = answer_result["confidence"]
        source_ids = answer_result.get("source_pair_ids", [])

        # Проверить порог уверенности
        if confidence < self._confidence_threshold:
            logger.info(
                "Уверенность ниже порога: conf=%.2f threshold=%.2f msg=%d",
                confidence, self._confidence_threshold, message.id,
            )
            return None

        # Записать rate limit
        self._rate_limiter.record(sender_id, effective_group_id)

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
            group_id=effective_group_id,
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
                message.id, effective_group_id,
                confidence, source_ids,
                text[:200],
                answer_text[:300],
            )
        else:
            # Отправить ответ
            try:
                source_group_title = self._resolve_chat_title(chat)
                sender_label = self._format_sender_label(sender, sender_id)
                await self._send_answer(
                    event=event,
                    answer_text=answer_text,
                    question_text=text,
                    source_group_id=chat_id,
                    source_group_title=source_group_title,
                    sender_label=sender_label,
                    source_message_id=message.id,
                )
                result.responded = True
                logger.info(
                    "Ответ отправлен: msg=%d group=%d conf=%.2f redirected_group=%s",
                    message.id,
                    chat_id,
                    confidence,
                    self._redirect_output_group_id,
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

    async def _is_question_message(
        self,
        text: str,
        force_as_question: bool = False,
    ) -> bool:
        """Определить, является ли сообщение вопросом для автоответчика."""
        normalized = (text or "").strip()
        if not normalized:
            return False

        if force_as_question:
            return True

        if "?" in normalized:
            return True

        return await self._classify_message_as_question(normalized)

    async def _classify_message_as_question(self, text: str) -> bool:
        """Определить через LLM, является ли сообщение вопросом без вопросительного знака."""
        try:
            result = await self._question_classifier.classify(text)
            logger.debug(
                "LLM-классификация вопроса: is_question=%s confidence=%.2f text=%s",
                result.is_question,
                result.confidence,
                text[:120],
            )
            return result.is_question
        except Exception as exc:
            logger.warning(
                "Ошибка LLM-классификации вопроса, используется эвристика: %s",
                exc,
            )
            return self._looks_like_question(text)

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

    def _resolve_effective_group_id(self, chat_id: int) -> int:
        """Вернуть реальный group_id для тестовой группы или исходный group_id."""
        return self._test_group_mapping.get(chat_id, chat_id)

    async def _send_answer(
        self,
        event,
        answer_text: str,
        question_text: str,
        source_group_id: int,
        source_group_title: str,
        sender_label: str,
        source_message_id: int,
    ) -> None:
        """Отправить ответ либо reply в исходную группу, либо в тестовую группу."""
        if self._redirect_output_group_id is None:
            await event.reply(answer_text)
            return

        client = getattr(event, "client", None)
        if client is None or not hasattr(client, "send_message"):
            raise RuntimeError("У события отсутствует Telethon client для send_message")

        redirect_message = self._build_redirect_message(
            answer_text=answer_text,
            question_text=question_text,
            source_group_id=source_group_id,
            source_group_title=source_group_title,
            sender_label=sender_label,
            source_message_id=source_message_id,
        )
        await client.send_message(self._redirect_output_group_id, redirect_message)

    def _build_redirect_message(
        self,
        answer_text: str,
        question_text: str,
        source_group_id: int,
        source_group_title: str,
        sender_label: str,
        source_message_id: int,
    ) -> str:
        """Сформировать сообщение для перенаправленного test mode."""
        source_link = self._build_group_message_link(source_group_id, source_message_id)
        source_group_title = source_group_title or "Без названия"
        sender_label = sender_label or "Неизвестный отправитель"
        link_line = source_link if source_link else f"msg_id={source_message_id}"

        header = [
            "GK REDIRECT TEST MODE",
            f"Источник: {source_group_title} ({source_group_id})",
            f"Отправитель: {sender_label}",
            f"Сообщение: {link_line}",
            "",
            "Вопрос:",
            self._truncate_for_telegram(question_text, 1200),
            "",
            "Ответ:",
            self._truncate_for_telegram(answer_text, 2400),
        ]
        return "\n".join(header)

    @staticmethod
    def _truncate_for_telegram(text: str, max_length: int) -> str:
        """Обрезать текст до безопасной длины для Telegram."""
        normalized = (text or "").strip()
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 1].rstrip() + "…"

    @staticmethod
    def _resolve_chat_title(chat) -> str:
        """Извлечь название чата, если оно доступно."""
        title = getattr(chat, "title", "")
        return title if isinstance(title, str) else ""

    @staticmethod
    def _format_sender_label(sender, sender_id: int) -> str:
        """Сформировать читаемую подпись отправителя."""
        if sender is None:
            return str(sender_id) if sender_id else "Неизвестно"

        title = getattr(sender, "title", None)
        if isinstance(title, str) and title.strip():
            return title.strip()

        first_name = getattr(sender, "first_name", None)
        first_name = first_name.strip() if isinstance(first_name, str) else ""
        last_name = getattr(sender, "last_name", None)
        last_name = last_name.strip() if isinstance(last_name, str) else ""
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()
        username = getattr(sender, "username", None)
        username = username.strip() if isinstance(username, str) else ""
        if full_name and username:
            return f"{full_name} (@{username}, id={sender_id})"
        if full_name:
            return f"{full_name} (id={sender_id})"
        if username:
            return f"@{username} (id={sender_id})"
        return str(sender_id) if sender_id else "Неизвестно"

    @staticmethod
    def _build_group_message_link(group_id: int, telegram_message_id: int) -> Optional[str]:
        """Построить ссылку на исходное сообщение группы."""
        if not group_id or not telegram_message_id:
            return None

        normalized_group_id = str(abs(group_id))
        if normalized_group_id.startswith("100"):
            normalized_group_id = normalized_group_id[3:]
        if not normalized_group_id:
            return None
        return f"https://t.me/c/{normalized_group_id}/{telegram_message_id}"

    @staticmethod
    def _parse_group_id(value: Any) -> Optional[int]:
        """Преобразовать group_id из конфига в целое число."""
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning("Некорректный redirect group id: %s", value)
            return None

    @staticmethod
    def _resolve_chat_id(chat) -> int:
        """Извлечь chat_id, учитывая формат для супергрупп."""
        chat_id = getattr(chat, "id", 0)
        if chat_id > 0:
            if getattr(chat, "megagroup", False) or getattr(chat, "broadcast", False):
                return -int(f"100{chat_id}")
            return -chat_id
        return chat_id
