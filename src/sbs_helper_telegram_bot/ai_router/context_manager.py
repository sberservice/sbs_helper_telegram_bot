"""
context_manager.py — менеджер контекста диалога для AI-маршрутизации.

Хранит последние сообщения пользователя в памяти для формирования
контекста LLM-запросов (поддержка коротких диалогов из 3-5 сообщений).
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings

logger = logging.getLogger(__name__)


@dataclass
class ContextMessage:
    """Одно сообщение в контексте диалога."""

    role: str
    """Роль: 'user' или 'assistant'."""

    content: str
    """Текст сообщения."""

    timestamp: float
    """Время добавления (monotonic)."""


class ConversationContextManager:
    """
    Менеджер контекста диалога.

    Хранит последние сообщения каждого пользователя в in-memory deque.
    Поддерживает TTL — автоматически удаляет устаревшие сообщения.
    """

    def __init__(
        self,
        max_messages: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
    ):
        """
        Инициализация менеджера контекста.

        Args:
            max_messages: Максимальное число сообщений в контексте.
            ttl_seconds: Время жизни сообщений в секундах.
        """
        self._max_messages = max_messages or ai_settings.MAX_CONTEXT_MESSAGES
        self._ttl_seconds = ttl_seconds or ai_settings.CONTEXT_TTL_SECONDS
        self._contexts: Dict[int, deque[ContextMessage]] = defaultdict(
            lambda: deque(maxlen=self._max_messages)
        )

    def add_message(self, user_id: int, role: str, content: str) -> None:
        """
        Добавить сообщение в контекст пользователя.

        Args:
            user_id: Telegram ID пользователя.
            role: Роль ('user' или 'assistant').
            content: Текст сообщения.
        """
        self._prune_expired(user_id)
        msg = ContextMessage(
            role=role,
            content=content,
            timestamp=time.monotonic(),
        )
        self._contexts[user_id].append(msg)

    def get_messages(self, user_id: int) -> List[Dict[str, str]]:
        """
        Получить сообщения контекста в формате для LLM API.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            Список словарей [{"role": ..., "content": ...}, ...].
        """
        self._prune_expired(user_id)
        ctx = self._contexts.get(user_id)
        if not ctx:
            return []
        return [{"role": msg.role, "content": msg.content} for msg in ctx]

    def clear(self, user_id: int) -> None:
        """
        Очистить контекст пользователя.

        Args:
            user_id: Telegram ID пользователя.
        """
        self._contexts.pop(user_id, None)

    def clear_all(self) -> None:
        """Очистить все контексты."""
        self._contexts.clear()

    def has_context(self, user_id: int) -> bool:
        """
        Проверить, есть ли контекст у пользователя.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            True если есть непустой и непросроченный контекст.
        """
        self._prune_expired(user_id)
        ctx = self._contexts.get(user_id)
        return bool(ctx)

    def _prune_expired(self, user_id: int) -> None:
        """Удалить устаревшие сообщения из контекста пользователя."""
        ctx = self._contexts.get(user_id)
        if not ctx:
            return

        now = time.monotonic()
        cutoff = now - self._ttl_seconds

        while ctx and ctx[0].timestamp < cutoff:
            ctx.popleft()

        # Если все сообщения удалены — убираем запись
        if not ctx:
            self._contexts.pop(user_id, None)
