"""Склейка соседних сообщений пользователя и запуск автоответчика в daemon collector."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.group_knowledge import database as gk_db
from src.group_knowledge.models import GroupMessage
from src.group_knowledge.responder import GroupResponder
from src.group_knowledge.settings import GK_IGNORED_SENDER_IDS

logger = logging.getLogger(__name__)


@dataclass
class PendingQuestionBundle:
    """Буфер соседних сообщений пользователя для единого вопроса."""

    root_event: object
    latest_event: object
    messages: List[GroupMessage] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    created_at: float = 0.0
    updated_at: float = 0.0


class CollectorResponderBridge:
    """Склеивает сообщения и передаёт их в GroupResponder."""

    def __init__(
        self,
        responder: GroupResponder,
        group_ids: set[int],
        grouping_window_seconds: int,
        test_group_ids: Optional[set[int]] = None,
    ) -> None:
        self._responder = responder
        self._group_ids = set(group_ids)
        self._test_group_ids = set(test_group_ids or set())
        self._grouping_window_seconds = max(1, int(grouping_window_seconds))
        self._pending: Dict[Tuple[int, int], PendingQuestionBundle] = {}
        self._stats = {"scheduled": 0, "processed": 0, "answered": 0, "dry_run": 0}

    @property
    def stats(self) -> dict:
        """Статистика bridge."""
        return dict(self._stats)

    async def queue_message(self, event, message_record: Optional[GroupMessage]) -> None:
        """Добавить сообщение в буфер пользователя и запланировать совместную обработку."""
        if not message_record:
            logger.info("Буфер автоответчика: пропуск — пустой message_record")
            return
        if message_record.group_id not in self._group_ids:
            logger.info(
                "Буфер автоответчика: пропуск — группа не отслеживается group=%d tracked_groups=%s",
                message_record.group_id,
                sorted(self._group_ids),
            )
            return
        if message_record.sender_id in GK_IGNORED_SENDER_IDS and message_record.group_id not in self._test_group_ids:
            logger.info(
                "Буфер автоответчика: пропуск — sender в GK_IGNORED_SENDER_IDS sender=%d ignored=%s",
                message_record.sender_id,
                sorted(GK_IGNORED_SENDER_IDS),
            )
            return
        if message_record.sender_id in GK_IGNORED_SENDER_IDS and message_record.group_id in self._test_group_ids:
            logger.info(
                "Буфер автоответчика: sender=%d в ignored, но группа %d помечена как test-mode — пропуск отключён",
                message_record.sender_id,
                message_record.group_id,
            )

        key = (message_record.group_id, message_record.sender_id)
        now = time.time()
        bundle = self._pending.get(key)
        if bundle is None:
            bundle = PendingQuestionBundle(
                root_event=event,
                latest_event=event,
                messages=[message_record],
                created_at=now,
                updated_at=now,
            )
            self._pending[key] = bundle
        else:
            bundle.latest_event = event
            bundle.messages.append(message_record)
            bundle.updated_at = now
            if bundle.task is not None:
                bundle.task.cancel()

        bundle.task = asyncio.create_task(self._flush_after_delay(key))
        self._stats["scheduled"] += 1
        logger.info(
            "Буфер автоответчика: group=%d sender=%d msg_tg=%d flush_in=%ds queued_messages=%d is_question_hint=%s",
            message_record.group_id,
            message_record.sender_id,
            message_record.telegram_message_id,
            self._grouping_window_seconds,
            len(bundle.messages),
            message_record.is_question,
        )

    async def stop(self) -> None:
        """Остановить bridge и дождаться обработки буферов."""
        tasks = []
        for bundle in self._pending.values():
            if bundle.task is not None:
                bundle.task.cancel()
                tasks.append(bundle.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._pending.clear()

    async def _flush_after_delay(self, key: Tuple[int, int]) -> None:
        """Дождаться окна склейки и обработать объединённый вопрос."""
        try:
            await asyncio.sleep(self._grouping_window_seconds)
        except asyncio.CancelledError:
            return

        bundle = self._pending.pop(key, None)
        if bundle is None:
            return

        latest_messages = self._refresh_messages_from_db(bundle.messages)
        combined_text = self._build_combined_question(latest_messages)
        if not combined_text:
            return

        logger.info(
            "Bridge запускает автоответчик: group=%d sender=%d messages=%d text=%s",
            key[0],
            key[1],
            len(latest_messages),
            combined_text[:200],
        )

        force_as_question = any(msg.is_question is True for msg in latest_messages)
        result = await self._responder.handle_message(
            bundle.root_event,
            self._group_ids,
            question_override=combined_text,
            force_as_question=force_as_question,
        )
        self._stats["processed"] += 1
        if result:
            if result.dry_run:
                self._stats["dry_run"] += 1
            elif result.responded:
                self._stats["answered"] += 1

    @staticmethod
    def _refresh_messages_from_db(messages: List[GroupMessage]) -> List[GroupMessage]:
        """Обновить сообщения из БД перед flush, чтобы подтянуть caption/image_description."""
        refreshed: List[GroupMessage] = []
        refreshed_count = 0

        for msg in messages:
            latest = gk_db.get_message_by_telegram_id(msg.group_id, msg.telegram_message_id)
            if latest is None:
                refreshed.append(msg)
                continue

            refreshed.append(latest)

            had_textual_image_context = bool((msg.caption or "").strip() or (msg.image_description or "").strip())
            has_textual_image_context_now = bool((latest.caption or "").strip() or (latest.image_description or "").strip())
            if latest.full_text.strip() != msg.full_text.strip() or (not had_textual_image_context and has_textual_image_context_now):
                refreshed_count += 1

        if refreshed_count:
            logger.info(
                "Bridge обновил сообщения из БД перед автоответом: refreshed=%d total=%d",
                refreshed_count,
                len(messages),
            )

        return refreshed

    @staticmethod
    def _build_combined_question(messages: List[GroupMessage]) -> str:
        """Собрать единый текст вопроса из соседних сообщений пользователя."""
        parts: List[str] = []
        seen_parts = set()
        ordered_messages = sorted(
            messages,
            key=lambda item: (item.message_date, item.telegram_message_id),
        )

        for msg in ordered_messages:
            text = msg.full_text.strip()
            if text and text not in seen_parts:
                parts.append(text)
                seen_parts.add(text)
                continue

            if msg.has_image:
                marker = "[Пользователь приложил изображение без подписи]"
                if marker not in seen_parts:
                    parts.append(marker)
                    seen_parts.add(marker)

        return "\n".join(parts).strip()
