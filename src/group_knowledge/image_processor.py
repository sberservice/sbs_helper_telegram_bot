"""
Обработчик изображений для подсистемы Group Knowledge.

Скачивает изображения из Telegram-сообщений, описывает их через
GigaChat Vision API и обновляет записи в базе данных.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from config import ai_settings
from src.core.ai.llm_provider import GigaChatProvider
from src.group_knowledge import database as gk_db
from src.group_knowledge.models import ImageDescription

logger = logging.getLogger(__name__)


class ImageProcessor:
    """
    Обработчик изображений: скачивание из Telegram + описание через GigaChat.

    Работает как фоновая задача, опрашивая очередь gk_image_queue
    и обрабатывая изображения по одному.
    """

    def __init__(
        self,
        gigachat_provider: Optional[GigaChatProvider] = None,
        storage_path: Optional[str] = None,
    ):
        """
        Инициализация обработчика изображений.

        Args:
            gigachat_provider: Провайдер GigaChat (создаётся по умолчанию).
            storage_path: Путь к хранилищу изображений (по умолчанию из настроек).
        """
        self._provider = gigachat_provider or GigaChatProvider()
        self._storage_path = storage_path or ai_settings.GK_IMAGE_STORAGE_PATH

    @staticmethod
    def _truncate_for_log(value: str, max_chars: int = 500) -> str:
        """Ограничить длину описания изображения в логах."""
        text = str(value or "")
        if len(text) <= max_chars:
            return text
        suffix = f"... [truncated {len(text) - max_chars} chars]"
        return text[:max_chars] + suffix

    async def download_image(
        self,
        client,
        message,
        group_id: int,
    ) -> Optional[str]:
        """
        Скачать фото/документ из Telegram-сообщения на диск.

        Args:
            client: Экземпляр TelegramClient.
            message: Объект Telethon Message.
            group_id: ID группы для организации директорий.

        Returns:
            Путь к сохранённому файлу или None при ошибке.
        """
        from datetime import datetime

        try:
            date_str = datetime.fromtimestamp(
                message.date.timestamp()
            ).strftime("%Y-%m-%d")

            # Создать директорию: {storage_path}/{group_id}/{date}/
            dir_path = Path(self._storage_path) / str(group_id) / date_str
            dir_path.mkdir(parents=True, exist_ok=True)

            # Определить имя файла
            msg_id = message.id
            file_path = dir_path / f"{msg_id}.jpg"

            # Скачать файл через Telethon
            downloaded_path = await client.download_media(
                message,
                file=str(file_path),
            )

            if downloaded_path:
                logger.info(
                    "Изображение скачано: group=%d msg=%d path=%s",
                    group_id, msg_id, downloaded_path,
                )
                return str(downloaded_path)
            else:
                logger.warning(
                    "Не удалось скачать изображение: group=%d msg=%d",
                    group_id, msg_id,
                )
                return None
        except Exception as exc:
            logger.error(
                "Ошибка скачивания изображения: group=%d msg=%d error=%s",
                group_id, getattr(message, "id", 0), exc,
                exc_info=True,
            )
            return None

    async def describe_image(
        self,
        image_path: str,
        prompt: Optional[str] = None,
    ) -> ImageDescription:
        """
        Описать изображение через GigaChat Vision.

        Args:
            image_path: Путь к файлу изображения.
            prompt: Промпт для описания (по умолчанию из настроек).

        Returns:
            ImageDescription с результатом.
        """
        if not os.path.exists(image_path):
            return ImageDescription(
                image_path=image_path,
                description="",
                success=False,
                error=f"Файл не найден: {image_path}",
            )

        try:
            description = await self._provider.describe_image(
                image_path=image_path,
                prompt=prompt,
            )
            return ImageDescription(
                image_path=image_path,
                description=description,
                model_used=self._provider.get_model_name() or "",
                success=True,
            )
        except Exception as exc:
            logger.error(
                "Ошибка описания изображения: path=%s error=%s",
                image_path, exc,
                exc_info=True,
            )
            return ImageDescription(
                image_path=image_path,
                description="",
                model_used=self._provider.get_model_name() or "",
                success=False,
                error=str(exc),
            )

    async def process_queue(self, batch_size: int = 5) -> int:
        """
        Обработать очередь изображений: описать через GigaChat.

        Args:
            batch_size: Число изображений для обработки за один проход.

        Returns:
            Число успешно обработанных изображений.
        """
        pending = gk_db.get_pending_images(limit=batch_size)
        if not pending:
            return 0

        processed_count = 0
        for item in pending:
            queue_id = item["id"]
            message_id = item["message_id"]
            image_path = item["image_path"]

            logger.info(
                "Обработка изображения из очереди: queue_id=%d message_id=%d path=%s",
                queue_id, message_id, image_path,
            )

            # Отметить как "в обработке"
            gk_db.update_image_status(queue_id, status=1)

            result = await self.describe_image(image_path)

            if result.success and result.description:
                # Обновить описание в таблице сообщений
                gk_db.update_message_image_description(message_id, result.description)
                # Отметить как "готово"
                gk_db.update_image_status(queue_id, status=2)
                processed_count += 1
                logger.info(
                    "Изображение описано: queue_id=%d len=%d",
                    queue_id, len(result.description),
                )
                logger.info(
                    "GigaChat видит на изображении: queue_id=%d message_id=%d description=%s",
                    queue_id,
                    message_id,
                    self._truncate_for_log(result.description),
                )
            else:
                # Отметить как "ошибка"
                gk_db.update_image_status(
                    queue_id, status=3, error_message=result.error or "Неизвестная ошибка"
                )
                logger.warning(
                    "Ошибка описания изображения: queue_id=%d error=%s",
                    queue_id, result.error,
                )

            # Пауза между запросами к GigaChat (rate limit)
            await asyncio.sleep(1.0)

        return processed_count

    async def process_queue_loop(
        self,
        poll_interval: float = 10.0,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """
        Запустить цикл обработки очереди изображений.

        Args:
            poll_interval: Интервал опроса очереди (секунды).
            stop_event: Событие для остановки цикла.
        """
        logger.info("Запущен цикл обработки очереди изображений (интервал=%.1fs)", poll_interval)

        while True:
            if stop_event and stop_event.is_set():
                logger.info("Остановка цикла обработки очереди изображений")
                break

            try:
                processed = await self.process_queue()
                if processed > 0:
                    logger.info("Обработано изображений: %d", processed)
            except Exception as exc:
                logger.error(
                    "Ошибка в цикле обработки очереди: %s", exc, exc_info=True
                )

            # Ожидание с проверкой stop_event
            if stop_event:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                    break
                except asyncio.TimeoutError:
                    continue
            else:
                await asyncio.sleep(poll_interval)
