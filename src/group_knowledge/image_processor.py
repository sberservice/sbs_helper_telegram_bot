"""
Обработчик изображений для подсистемы Group Knowledge.

Скачивает изображения из Telegram-сообщений, описывает их через
GigaChat Vision API и обновляет записи в базе данных.
"""

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Optional, Union, Any

from config import ai_settings
from src.core.ai.llm_provider import GigaChatProvider, get_provider_class, is_provider_registered
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
        self._provider = gigachat_provider or self._build_runtime_provider()
        self._storage_path = storage_path or ai_settings.GK_IMAGE_STORAGE_PATH

    @staticmethod
    def _build_runtime_provider() -> Any:
        """Собрать vision-провайдер по runtime-настройкам GK."""
        provider_name = ai_settings.get_active_gk_image_provider()
        if not is_provider_registered(provider_name):
            logger.warning(
                "GK ImageProcessor: провайдер '%s' не зарегистрирован, используем gigachat",
                provider_name,
            )
            provider_name = "gigachat"

        provider_class = get_provider_class(provider_name)
        if provider_class is None:
            logger.warning(
                "GK ImageProcessor: класс провайдера '%s' недоступен, используем GigaChatProvider",
                provider_name,
            )
            provider_class = GigaChatProvider

        model_name = ai_settings.get_active_gk_image_description_model()
        try:
            provider = provider_class(model=model_name)
        except TypeError:
            provider = provider_class()

        if not hasattr(provider, "describe_image"):
            logger.warning(
                "GK ImageProcessor: провайдер '%s' не поддерживает describe_image, используем GigaChatProvider",
                provider_name,
            )
            provider = GigaChatProvider(model=model_name)

        return provider

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

    def _is_stop_set(self, stop_event: Optional[Union[asyncio.Event, threading.Event]]) -> bool:
        """Проверить, установлен ли сигнал остановки (поддержка asyncio.Event и threading.Event)."""
        if stop_event is None:
            return False
        return stop_event.is_set()

    async def _wait_for_stop(
        self,
        stop_event: Optional[Union[asyncio.Event, threading.Event]],
        timeout: float,
    ) -> bool:
        """
        Ждать сигнала остановки с таймаутом.

        Поддерживает asyncio.Event (ожидание через wait_for) и threading.Event
        (поллинг через asyncio.sleep).

        Returns:
            True если сигнал остановки был получен, False по таймауту.
        """
        if stop_event is None:
            await asyncio.sleep(timeout)
            return False

        if isinstance(stop_event, asyncio.Event):
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=timeout)
                return True
            except asyncio.TimeoutError:
                return False

        # threading.Event — поллинг с мелким шагом
        elapsed = 0.0
        step = min(0.5, timeout)
        while elapsed < timeout:
            if stop_event.is_set():
                return True
            await asyncio.sleep(step)
            elapsed += step
        return stop_event.is_set()

    async def process_queue_loop(
        self,
        poll_interval: float = 10.0,
        stop_event: Optional[Union[asyncio.Event, threading.Event]] = None,
        drain_remaining: bool = False,
    ) -> int:
        """
        Запустить цикл обработки очереди изображений.

        Args:
            poll_interval: Интервал опроса очереди (секунды).
            stop_event: Событие для остановки цикла (asyncio.Event или threading.Event).
            drain_remaining: Если True, после получения сигнала остановки дообработать
                             все оставшиеся изображения в очереди перед выходом.

        Returns:
            Общее число обработанных изображений.
        """
        logger.info("Запущен цикл обработки очереди изображений (интервал=%.1fs)", poll_interval)
        total_processed = 0

        while True:
            if self._is_stop_set(stop_event):
                logger.info("Получен сигнал остановки цикла обработки очереди изображений")
                break

            try:
                processed = await self.process_queue()
                if processed > 0:
                    total_processed += processed
                    logger.info("Обработано изображений: %d (всего: %d)", processed, total_processed)
            except Exception as exc:
                logger.error(
                    "Ошибка в цикле обработки очереди: %s", exc, exc_info=True
                )

            # Ожидание с проверкой stop_event
            stopped = await self._wait_for_stop(stop_event, poll_interval)
            if stopped:
                break

        # Дообработка оставшихся изображений после остановки
        if drain_remaining:
            logger.info("Дообработка оставшихся изображений в очереди...")
            while True:
                try:
                    processed = await self.process_queue(batch_size=10)
                    if processed == 0:
                        break
                    total_processed += processed
                    logger.info("Дообработка: обработано %d (всего: %d)", processed, total_processed)
                except Exception as exc:
                    logger.error(
                        "Ошибка при дообработке очереди: %s", exc, exc_info=True
                    )
                    break

        logger.info("Цикл обработки очереди изображений завершён: всего обработано %d", total_processed)
        return total_processed
