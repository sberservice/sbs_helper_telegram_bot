"""
Коллектор сообщений из Telegram-групп.

Слушает новые сообщения в настроенных группах через Telethon,
сохраняет текст и подписи в БД, скачивает изображения
и ставит их в очередь на описание через GigaChat.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.group_knowledge import database as gk_db
from src.group_knowledge.image_processor import ImageProcessor
from src.group_knowledge.models import GroupMessage
from src.group_knowledge.question_classifier import QuestionClassifierService
from src.group_knowledge.settings import (
    MAX_MESSAGE_AGE_SECONDS,
    MAX_MESSAGE_TEXT_LENGTH,
    SUPPORTED_IMAGE_MIME_TYPES,
)

logger = logging.getLogger(__name__)

# Корень проекта
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Путь к конфигурации групп
GK_GROUPS_CONFIG_PATH = PROJECT_ROOT / "config" / "gk_groups.json"
GK_TEST_TARGET_GROUP_KEY = "test_target_group"


def _load_groups_config_data() -> Dict[str, Any]:
    """Загрузить полный JSON-конфиг Group Knowledge."""
    if not GK_GROUPS_CONFIG_PATH.exists():
        logger.warning("Файл конфигурации групп не найден: %s", GK_GROUPS_CONFIG_PATH)
        return {}

    try:
        with open(GK_GROUPS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        logger.error(
            "Некорректный формат конфигурации групп: ожидался объект JSON, получено %s",
            type(data).__name__,
        )
        return {}
    except (json.JSONDecodeError, IOError) as exc:
        logger.error("Ошибка чтения конфигурации групп: %s", exc)
        return {}


def _save_groups_config_data(data: Dict[str, Any]) -> None:
    """Сохранить полный JSON-конфиг Group Knowledge."""
    GK_GROUPS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GK_GROUPS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_groups_config() -> List[Dict[str, Any]]:
    """
    Загрузить конфигурацию отслеживаемых групп из JSON.

    Returns:
        Список групп [{id, title}, ...].
    """
    data = _load_groups_config_data()
    groups = data.get("groups", [])
    if isinstance(groups, list):
        return groups
    logger.error("Некорректный формат поля groups в %s", GK_GROUPS_CONFIG_PATH)
    return []


def load_test_target_group_config() -> Optional[Dict[str, Any]]:
    """Загрузить группу назначения для перенаправленного test mode."""
    data = _load_groups_config_data()
    test_target_group = data.get(GK_TEST_TARGET_GROUP_KEY)
    if not test_target_group:
        return None
    if not isinstance(test_target_group, dict):
        logger.error(
            "Некорректный формат поля %s в %s",
            GK_TEST_TARGET_GROUP_KEY,
            GK_GROUPS_CONFIG_PATH,
        )
        return None
    if "id" not in test_target_group:
        logger.error(
            "В конфигурации %s отсутствует id у %s",
            GK_GROUPS_CONFIG_PATH,
            GK_TEST_TARGET_GROUP_KEY,
        )
        return None
    return test_target_group


def save_groups_config(groups: List[Dict[str, Any]]) -> None:
    """
    Сохранить конфигурацию групп в JSON.

    Args:
        groups: Список групп [{id, title}, ...].
    """
    data = _load_groups_config_data()
    data["groups"] = groups
    _save_groups_config_data(data)
    logger.info("Конфигурация групп сохранена: %d групп", len(groups))


def save_test_target_group_config(group: Optional[Dict[str, Any]]) -> None:
    """Сохранить группу назначения для перенаправленного test mode."""
    data = _load_groups_config_data()
    if group is None:
        data.pop(GK_TEST_TARGET_GROUP_KEY, None)
        logger.info("Глобальная test target group очищена")
    else:
        data[GK_TEST_TARGET_GROUP_KEY] = group
        logger.info(
            "Глобальная test target group сохранена: %s (%s)",
            group.get("title", "Без названия"),
            group.get("id"),
        )
    _save_groups_config_data(data)


class MessageCollector:
    """
    Коллектор сообщений из Telegram-групп через Telethon.

    Слушает новые сообщения, сохраняет текст/подписи в БД,
    скачивает изображения и ставит их в очередь обработки.
    """

    def __init__(
        self,
        client,
        image_processor: Optional[ImageProcessor] = None,
        groups: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Инициализация коллектора.

        Args:
            client: Экземпляр TelegramClient.
            image_processor: Обработчик изображений (создаётся по умолчанию).
            groups: Список отслеживаемых групп (по умолчанию из конфига).
        """
        self._client = client
        self._image_processor = image_processor or ImageProcessor()
        self._question_classifier = QuestionClassifierService()
        self._groups = groups if groups is not None else load_groups_config()
        self._group_ids = {g["id"] for g in self._groups}
        self._group_titles = {g["id"]: g.get("title", "") for g in self._groups}
        self._stop_event = asyncio.Event()

    @property
    def group_ids(self) -> set:
        """Множество отслеживаемых group_id."""
        return self._group_ids

    async def handle_new_message(self, event) -> Optional[GroupMessage]:
        """
        Обработать новое сообщение из группы.

        Args:
            event: Telethon NewMessage event.
        """
        message = event.message

        # Пропустить служебные сообщения
        if not message or message.action:
            return None

        # Извлечь chat_id
        chat_id = self._get_chat_id(event)
        if chat_id not in self._group_ids:
            return None

        # Пропустить слишком старые сообщения (при реконнекте)
        if message.date:
            msg_age = time.time() - message.date.timestamp()
            if msg_age > MAX_MESSAGE_AGE_SECONDS:
                logger.debug(
                    "Пропущено старое сообщение: group=%d msg=%d age=%ds",
                    chat_id, message.id, int(msg_age),
                )
                return None

        existing_message = gk_db.get_message_by_telegram_id(chat_id, message.id)
        if existing_message:
            logger.debug(
                "Пропущено уже собранное live-сообщение: group=%d msg=%d",
                chat_id,
                message.id,
            )
            return None

        # Пропустить сообщения от ботов
        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            return None

        # Извлечь данные сообщения
        sender_id = getattr(sender, "id", 0) if sender else 0
        sender_name = self._get_sender_name(sender)
        message_text = message.text or ""
        caption = message.message if message.media and not message.text else None

        # Если текст = caption (Telethon может дублировать), убрать дубль
        if caption and message_text and caption == message_text:
            caption = None

        # Ограничить длину текста
        if len(message_text) > MAX_MESSAGE_TEXT_LENGTH:
            message_text = message_text[:MAX_MESSAGE_TEXT_LENGTH]
        if caption and len(caption) > MAX_MESSAGE_TEXT_LENGTH:
            caption = caption[:MAX_MESSAGE_TEXT_LENGTH]

        # Проверить наличие изображения
        has_image = self._message_has_image(message)

        # Определить reply-to
        reply_to_id = None
        if message.reply_to:
            reply_to_id = message.reply_to.reply_to_msg_id

        # Создать объект сообщения
        group_title = self._group_titles.get(chat_id, "")
        msg_obj = GroupMessage(
            telegram_message_id=message.id,
            group_id=chat_id,
            group_title=group_title,
            sender_id=sender_id,
            sender_name=sender_name,
            message_text=message_text,
            caption=caption,
            has_image=has_image,
            reply_to_message_id=reply_to_id,
            message_date=int(message.date.timestamp()) if message.date else int(time.time()),
        )

        await self._classify_message_question(msg_obj)

        # Сохранить в БД
        try:
            msg_db_id = gk_db.store_message(msg_obj)
            logger.info(
                "Сообщение сохранено: group=%d msg_tg=%d db_id=%d sender=%s has_image=%s message_ts=%s",
                chat_id,
                message.id,
                msg_db_id,
                sender_name,
                has_image,
                self._format_message_timestamp(msg_obj.message_date),
            )
        except Exception as exc:
            logger.error(
                "Ошибка сохранения сообщения: group=%d msg=%d error=%s",
                chat_id, message.id, exc,
                exc_info=True,
            )
            return None

        msg_obj.id = msg_db_id

        # Скачать изображение и поставить в очередь
        if has_image and msg_db_id:
            try:
                image_path = await self._image_processor.download_image(
                    client=self._client,
                    message=message,
                    group_id=chat_id,
                )
                if image_path:
                    gk_db.update_message_image_path(msg_db_id, image_path)
                    gk_db.enqueue_image(msg_db_id, image_path)
                    logger.info(
                        "Изображение добавлено в очередь: msg_db_id=%d path=%s",
                        msg_db_id, image_path,
                    )
            except Exception as exc:
                logger.error(
                    "Ошибка обработки изображения: msg_db_id=%d error=%s",
                    msg_db_id, exc,
                    exc_info=True,
                )

        return msg_obj

    async def backfill_messages(
        self,
        days: int = 7,
        group_id: Optional[int] = None,
        force: bool = False,
    ) -> int:
        """
        Загрузить историю сообщений за указанное число дней.

        Args:
            days: Число дней для загрузки.
            group_id: Конкретная группа (None — все группы).
            force: Принудительно обновить уже собранные сообщения и изображения.

        Returns:
            Число загруженных сообщений.
        """
        from datetime import timedelta

        target_groups = self._groups
        if group_id is not None:
            target_groups = [g for g in self._groups if g["id"] == group_id]

        if not target_groups:
            logger.warning("Нет групп для backfill")
            return 0

        total_collected = 0
        cutoff_date = datetime.now() - timedelta(days=days)

        for group_info in target_groups:
            if self._stop_event.is_set():
                logger.info("Backfill остановлен до обработки следующей группы")
                break

            gid = group_info["id"]
            title = group_info.get("title", "")
            logger.info(
                "Backfill: группа %d (%s), дней=%d, force=%s",
                gid, title, days, force,
            )

            try:
                entity = await self._client.get_entity(gid)
                count = 0
                inspected_count = 0
                skipped_existing_count = 0
                skipped_action_count = 0
                skipped_bot_count = 0

                async for message in self._client.iter_messages(
                    entity,
                    offset_date=None,
                    reverse=False,
                ):
                    if self._stop_event.is_set():
                        self._log_backfill_progress(
                            gid=gid,
                            title=title,
                            inspected_count=inspected_count,
                            saved_count=count,
                            skipped_existing_count=skipped_existing_count,
                            skipped_action_count=skipped_action_count,
                            skipped_bot_count=skipped_bot_count,
                            interrupted=True,
                        )
                        break

                    if message.date and message.date.timestamp() < cutoff_date.timestamp():
                        break

                    inspected_count += 1

                    if message.action:
                        skipped_action_count += 1
                        if inspected_count % 100 == 0:
                            self._log_backfill_progress(
                                gid=gid,
                                title=title,
                                inspected_count=inspected_count,
                                saved_count=count,
                                skipped_existing_count=skipped_existing_count,
                                skipped_action_count=skipped_action_count,
                                skipped_bot_count=skipped_bot_count,
                            )
                            await asyncio.sleep(0)
                        continue

                    existing_message = gk_db.get_message_by_telegram_id(gid, message.id)
                    if existing_message and not force:
                        skipped_existing_count += 1
                        if inspected_count % 100 == 0:
                            self._log_backfill_progress(
                                gid=gid,
                                title=title,
                                inspected_count=inspected_count,
                                saved_count=count,
                                skipped_existing_count=skipped_existing_count,
                                skipped_action_count=skipped_action_count,
                                skipped_bot_count=skipped_bot_count,
                            )
                            await asyncio.sleep(0)
                        continue

                    sender = await message.get_sender()
                    if sender and getattr(sender, "bot", False):
                        skipped_bot_count += 1
                        if inspected_count % 100 == 0:
                            self._log_backfill_progress(
                                gid=gid,
                                title=title,
                                inspected_count=inspected_count,
                                saved_count=count,
                                skipped_existing_count=skipped_existing_count,
                                skipped_action_count=skipped_action_count,
                                skipped_bot_count=skipped_bot_count,
                            )
                            await asyncio.sleep(0)
                        continue

                    sender_id = getattr(sender, "id", 0) if sender else 0
                    sender_name = self._get_sender_name(sender)
                    text = message.text or ""
                    caption = message.message if message.media and not message.text else None

                    if caption and text and caption == text:
                        caption = None

                    has_image = self._message_has_image(message)
                    reply_to_id = None
                    if message.reply_to:
                        reply_to_id = message.reply_to.reply_to_msg_id

                    msg_obj = GroupMessage(
                        telegram_message_id=message.id,
                        group_id=gid,
                        group_title=title,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        message_text=text[:MAX_MESSAGE_TEXT_LENGTH],
                        caption=caption[:MAX_MESSAGE_TEXT_LENGTH] if caption else None,
                        has_image=has_image,
                        reply_to_message_id=reply_to_id,
                        message_date=int(message.date.timestamp()) if message.date else 0,
                    )

                    await self._classify_message_question(msg_obj)

                    try:
                        msg_db_id = gk_db.store_message(msg_obj)
                        logger.info(
                            "Backfill: сообщение сохранено: group=%d msg_tg=%d db_id=%d sender=%s has_image=%s message_ts=%s",
                            gid,
                            message.id,
                            msg_db_id,
                            sender_name,
                            has_image,
                            self._format_message_timestamp(msg_obj.message_date),
                        )

                        if force and existing_message and msg_db_id:
                            if existing_message.image_path and os.path.exists(existing_message.image_path):
                                try:
                                    os.remove(existing_message.image_path)
                                    logger.info(
                                        "Удалён старый файл изображения перед force-backfill: msg_db_id=%d path=%s",
                                        msg_db_id,
                                        existing_message.image_path,
                                    )
                                except OSError as exc:
                                    logger.warning(
                                        "Не удалось удалить старый файл изображения: msg_db_id=%d path=%s error=%s",
                                        msg_db_id,
                                        existing_message.image_path,
                                        exc,
                                    )

                            gk_db.reset_message_image_processing(msg_db_id)

                        count += 1

                        if has_image and msg_db_id:
                            image_path = await self._image_processor.download_image(
                                client=self._client,
                                message=message,
                                group_id=gid,
                            )
                            if image_path:
                                gk_db.update_message_image_path(msg_db_id, image_path)
                                gk_db.enqueue_image(msg_db_id, image_path)
                    except Exception as exc:
                        logger.warning(
                            "Ошибка сохранения при backfill: msg=%d error=%s",
                            message.id, exc,
                        )

                    if inspected_count % 100 == 0:
                        self._log_backfill_progress(
                            gid=gid,
                            title=title,
                            inspected_count=inspected_count,
                            saved_count=count,
                            skipped_existing_count=skipped_existing_count,
                            skipped_action_count=skipped_action_count,
                            skipped_bot_count=skipped_bot_count,
                        )
                        await asyncio.sleep(0)

                    # Rate limit: пауза каждые 100 сохранённых сообщений
                    if count > 0 and count % 100 == 0:
                        await asyncio.sleep(1.0)

                total_collected += count
                logger.info(
                    "Backfill завершён для группы %d (%s): просмотрено=%d сохранено=%d пропущено=%d "
                    "(existing=%d service=%d bots=%d)",
                    gid,
                    title,
                    inspected_count,
                    count,
                    skipped_existing_count + skipped_action_count + skipped_bot_count,
                    skipped_existing_count,
                    skipped_action_count,
                    skipped_bot_count,
                )
            except Exception as exc:
                logger.error(
                    "Ошибка backfill для группы %d: %s",
                    gid, exc,
                    exc_info=True,
                )

        return total_collected

    async def sync_missed_messages(
        self,
        group_id: Optional[int] = None,
    ) -> int:
        """
        Добрать сообщения, пропущенные с прошлого запуска daemon.

        Логика опирается на максимальный `telegram_message_id`, уже сохранённый в БД
        для каждой группы. Если для группы ещё нет ни одного сообщения, историческая
        догрузка не выполняется — для первичного наполнения нужно использовать backfill.

        Args:
            group_id: Конкретная группа (None — все группы).

        Returns:
            Число догруженных сообщений.
        """
        target_groups = self._groups
        if group_id is not None:
            target_groups = [g for g in self._groups if g["id"] == group_id]

        if not target_groups:
            logger.warning("Нет групп для добора пропущенных сообщений")
            return 0

        total_collected = 0

        for group_info in target_groups:
            gid = group_info["id"]
            title = group_info.get("title", "")
            latest_message_id = gk_db.get_latest_telegram_message_id(gid)

            if not latest_message_id:
                logger.info(
                    "Добор пропущенных сообщений пропущен: group=%d title=%s reason=нет локальной контрольной точки",
                    gid,
                    title,
                )
                continue

            logger.info(
                "Добор пропущенных сообщений: group=%d title=%s after_tg_msg_id=%d",
                gid,
                title,
                latest_message_id,
            )

            try:
                entity = await self._client.get_entity(gid)
                count = 0

                async for message in self._client.iter_messages(
                    entity,
                    min_id=latest_message_id,
                    reverse=True,
                ):
                    if message.action:
                        continue

                    existing_message = gk_db.get_message_by_telegram_id(gid, message.id)
                    if existing_message:
                        continue

                    sender = await message.get_sender()
                    if sender and getattr(sender, "bot", False):
                        continue

                    sender_id = getattr(sender, "id", 0) if sender else 0
                    sender_name = self._get_sender_name(sender)
                    text = message.text or ""
                    caption = message.message if message.media and not message.text else None

                    if caption and text and caption == text:
                        caption = None

                    has_image = self._message_has_image(message)
                    reply_to_id = None
                    if message.reply_to:
                        reply_to_id = message.reply_to.reply_to_msg_id

                    msg_obj = GroupMessage(
                        telegram_message_id=message.id,
                        group_id=gid,
                        group_title=title,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        message_text=text[:MAX_MESSAGE_TEXT_LENGTH],
                        caption=caption[:MAX_MESSAGE_TEXT_LENGTH] if caption else None,
                        has_image=has_image,
                        reply_to_message_id=reply_to_id,
                        message_date=int(message.date.timestamp()) if message.date else int(time.time()),
                    )

                    await self._classify_message_question(msg_obj)

                    try:
                        msg_db_id = gk_db.store_message(msg_obj)
                        logger.info(
                            "Добор: сообщение сохранено: group=%d msg_tg=%d db_id=%d sender=%s has_image=%s message_ts=%s",
                            gid,
                            message.id,
                            msg_db_id,
                            sender_name,
                            has_image,
                            self._format_message_timestamp(msg_obj.message_date),
                        )
                        count += 1

                        if has_image and msg_db_id:
                            image_path = await self._image_processor.download_image(
                                client=self._client,
                                message=message,
                                group_id=gid,
                            )
                            if image_path:
                                gk_db.update_message_image_path(msg_db_id, image_path)
                                gk_db.enqueue_image(msg_db_id, image_path)
                    except Exception as exc:
                        logger.warning(
                            "Ошибка сохранения при доборе пропущенных сообщений: group=%d msg=%d error=%s",
                            gid,
                            message.id,
                            exc,
                        )

                    if count % 100 == 0 and count > 0:
                        logger.info(
                            "Добор пропущенных сообщений: группа %d — собрано %d сообщений...",
                            gid,
                            count,
                        )
                        await asyncio.sleep(1.0)

                total_collected += count
                logger.info(
                    "Добор пропущенных сообщений завершён: group=%d title=%s collected=%d",
                    gid,
                    title,
                    count,
                )
            except Exception as exc:
                logger.error(
                    "Ошибка добора пропущенных сообщений для группы %d: %s",
                    gid,
                    exc,
                    exc_info=True,
                )

        return total_collected

    async def _classify_message_question(self, msg_obj: GroupMessage) -> None:
        """Классифицировать новое сообщение как вопрос и сохранить метаданные в объекте."""
        text = (msg_obj.message_text or msg_obj.caption or "").strip()
        if not text:
            return

        if "?" in text:
            msg_obj.is_question = True
            msg_obj.question_confidence = 1.0
            msg_obj.question_reason = "Явный вопросительный знак в сообщении"
            msg_obj.question_model_used = "rule:question_mark"
            msg_obj.question_detected_at = int(time.time())
            return

        try:
            result = await self._question_classifier.classify(text)
            msg_obj.is_question = result.is_question
            msg_obj.question_confidence = result.confidence
            msg_obj.question_reason = result.reason
            msg_obj.question_model_used = result.model_used
            msg_obj.question_detected_at = result.detected_at
        except Exception as exc:
            logger.warning(
                "Ошибка классификации сообщения как вопроса: group=%d msg_tg=%d error=%s",
                msg_obj.group_id,
                msg_obj.telegram_message_id,
                exc,
            )

    def stop(self) -> None:
        """Послать сигнал остановки."""
        self._stop_event.set()

    @staticmethod
    def _log_backfill_progress(
        gid: int,
        title: str,
        inspected_count: int,
        saved_count: int,
        skipped_existing_count: int,
        skipped_action_count: int,
        skipped_bot_count: int,
        interrupted: bool = False,
    ) -> None:
        """Записать в лог прогресс backfill по текущей группе."""
        skipped_total = (
            skipped_existing_count
            + skipped_action_count
            + skipped_bot_count
        )
        status = "прерван" if interrupted else "progress"
        logger.info(
            "Backfill %s: группа %d (%s) — просмотрено=%d сохранено=%d пропущено=%d "
            "(existing=%d service=%d bots=%d)",
            status,
            gid,
            title,
            inspected_count,
            saved_count,
            skipped_total,
            skipped_existing_count,
            skipped_action_count,
            skipped_bot_count,
        )

    @staticmethod
    def _format_message_timestamp(message_date: int) -> str:
        """Преобразовать UNIX timestamp сообщения в строку для логов."""
        if not message_date:
            return "unknown"
        return datetime.fromtimestamp(message_date).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _get_chat_id(event) -> int:
        """Извлечь chat_id из события Telethon."""
        chat = event.chat
        if chat:
            chat_id = getattr(chat, "id", 0)
            # Для супергрупп/каналов Telethon возвращает положительный ID,
            # но в config мы храним отрицательный — конвертируем
            if chat_id > 0:
                # Проверим, есть ли атрибут megagroup (супергруппа)
                if getattr(chat, "megagroup", False) or getattr(chat, "broadcast", False):
                    return -int(f"100{chat_id}")
            return -chat_id if chat_id > 0 else chat_id
        return 0

    @staticmethod
    def _get_sender_name(sender) -> str:
        """Извлечь читаемое имя отправителя."""
        if not sender:
            return ""
        first = getattr(sender, "first_name", "") or ""
        last = getattr(sender, "last_name", "") or ""
        name = f"{first} {last}".strip()
        if not name:
            name = getattr(sender, "username", "") or ""
        return name[:255]

    @staticmethod
    def _message_has_image(message) -> bool:
        """Проверить, содержит ли сообщение изображение."""
        if not message.media:
            return False

        # Telethon: MessageMediaPhoto
        try:
            from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

            if isinstance(message.media, MessageMediaPhoto):
                return True
            if isinstance(message.media, MessageMediaDocument):
                doc = message.media.document
                if doc and doc.mime_type:
                    return doc.mime_type in SUPPORTED_IMAGE_MIME_TYPES
        except ImportError:
            pass

        return False


# ---------------------------------------------------------------------------
# Управление группами (CLI)
# ---------------------------------------------------------------------------

async def manage_groups_interactive(client) -> None:
    """
    Интерактивный CLI для управления списком отслеживаемых групп.

    Args:
        client: Подключённый TelegramClient.
    """
    print("\n=== Управление группами Group Knowledge ===\n")

    while True:
        groups = load_groups_config()
        available_groups = await _get_available_groups(client)
        configured_ids = {g["id"] for g in groups}

        if groups:
            print("Текущие отслеживаемые группы:")
            for i, g in enumerate(groups, 1):
                print(f"  {i}. {g.get('title', 'Без названия')} (ID: {g['id']})")
        else:
            print("Список групп пуст.")

        print("\nДействия:")
        print("  1. Показать доступные группы/супергруппы")
        print("  2. Добавить группы из списка")
        print("  3. Добавить группу по ID")
        print("  4. Удалить группу")
        print("  5. Обновить список групп")
        print("  6. Выход")

        choice = input("\nВыберите действие (1-6): ").strip()

        if choice == "1":
            _print_available_groups(available_groups, configured_ids)
        elif choice == "2":
            _add_groups_from_selection(groups, available_groups)
        elif choice == "3":
            await _add_group_interactive(client, groups)
        elif choice == "4":
            _remove_group_interactive(groups)
        elif choice == "5":
            print("Список доступных групп будет обновлён...")
            continue
        elif choice == "6":
            print("Выход из управления группами.")
            break
        else:
            print("Неизвестное действие.")


async def _get_available_groups(client) -> List[Dict[str, Any]]:
    """Получить список всех доступных групп и супергрупп аккаунта."""
    try:
        dialogs = await client.get_dialogs()
        groups_and_supergroups = []

        for dialog in dialogs:
            entity = dialog.entity
            is_group = getattr(entity, "megagroup", False) or (
                hasattr(entity, "participants_count")
                and not getattr(entity, "broadcast", False)
            )
            if is_group:
                # Для Telethon: получить «правильный» ID
                from telethon.utils import get_peer_id

                peer_id = get_peer_id(entity)
                title = getattr(entity, "title", "Без названия")
                participants = getattr(entity, "participants_count", "?")
                groups_and_supergroups.append({
                    "id": peer_id,
                    "title": title,
                    "participants": participants,
                })
        return groups_and_supergroups
    except Exception as exc:
        print(f"Ошибка получения списка групп: {exc}")
        return []


def _print_available_groups(
    available_groups: List[Dict[str, Any]],
    configured_ids: Optional[set] = None,
) -> None:
    """Вывести список доступных групп с отметками уже выбранных."""
    configured_ids = configured_ids or set()
    if available_groups:
        print(f"\nНайдено {len(available_groups)} групп/супергрупп:\n")
        for i, g in enumerate(available_groups, 1):
            mark = "[x]" if g["id"] in configured_ids else "[ ]"
            print(
                f"  {i}. {mark} {g['title']} "
                f"(ID: {g['id']}, участников: {g['participants']})"
            )
    else:
        print("Группы не найдены.")


def _parse_selection_numbers(raw: str, max_index: int) -> List[int]:
    """Распарсить выбор номеров вида '1,2,5-7'."""
    if not raw.strip():
        return []

    result = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_raw, end_raw = chunk.split("-", 1)
            start = int(start_raw.strip())
            end = int(end_raw.strip())
            if start > end:
                raise ValueError("Некорректный диапазон")
            for idx in range(start, end + 1):
                if idx < 1 or idx > max_index:
                    raise ValueError("Номер вне диапазона")
                result.add(idx)
        else:
            idx = int(chunk)
            if idx < 1 or idx > max_index:
                raise ValueError("Номер вне диапазона")
            result.add(idx)
    return sorted(result)


def _add_groups_from_selection(
    groups: List[Dict[str, Any]],
    available_groups: List[Dict[str, Any]],
) -> None:
    """Добавить одну или несколько групп из списка доступных."""
    if not available_groups:
        print("Нет доступных групп для выбора.")
        return

    configured_ids = {g["id"] for g in groups}
    _print_available_groups(available_groups, configured_ids)
    raw = input(
        "\nВведите номера групп для добавления "
        "(например: 1,3 или 2-5): "
    ).strip()

    try:
        selected_numbers = _parse_selection_numbers(raw, len(available_groups))
    except ValueError as exc:
        print(f"Ошибка выбора: {exc}")
        return

    if not selected_numbers:
        print("Ничего не выбрано.")
        return

    added_count = 0
    for number in selected_numbers:
        selected_group = available_groups[number - 1]
        if selected_group["id"] in configured_ids:
            continue
        groups.append({
            "id": selected_group["id"],
            "title": selected_group["title"],
        })
        configured_ids.add(selected_group["id"])
        added_count += 1

    if added_count == 0:
        print("Все выбранные группы уже добавлены.")
        return

    save_groups_config(groups)
    print(f"Добавлено групп: {added_count}")


async def _add_group_interactive(
    client, groups: List[Dict[str, Any]]
) -> None:
    """Добавить группу по ID."""
    raw = input("\nВведите ID группы (например, -1001234567890): ").strip()
    try:
        group_id = int(raw)
    except ValueError:
        print("Некорректный ID.")
        return

    # Проверить, не добавлена ли уже
    if any(g["id"] == group_id for g in groups):
        print("Эта группа уже в списке.")
        return

    # Попробовать получить название
    title = raw
    try:
        entity = await client.get_entity(group_id)
        title = getattr(entity, "title", str(group_id))
        print(f"Найдена группа: {title}")
    except Exception:
        title_input = input("Не удалось найти группу. Введите название вручную: ").strip()
        if title_input:
            title = title_input

    groups.append({"id": group_id, "title": title})
    save_groups_config(groups)
    print(f"Группа «{title}» добавлена.")


def _remove_group_interactive(groups: List[Dict[str, Any]]) -> None:
    """Удалить группу из списка."""
    if not groups:
        print("Список групп пуст.")
        return

    raw = input("Введите номер группы для удаления: ").strip()
    try:
        idx = int(raw) - 1
    except ValueError:
        print("Некорректный номер.")
        return

    if idx < 0 or idx >= len(groups):
        print("Номер вне диапазона.")
        return

    removed = groups.pop(idx)
    save_groups_config(groups)
    print(f"Группа «{removed.get('title', '')}» удалена.")
