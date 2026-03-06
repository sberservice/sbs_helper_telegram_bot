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

from config import ai_settings
from src.group_knowledge import database as gk_db
from src.group_knowledge.image_processor import ImageProcessor
from src.group_knowledge.models import GroupMessage
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


def load_groups_config() -> List[Dict[str, Any]]:
    """
    Загрузить конфигурацию отслеживаемых групп из JSON.

    Returns:
        Список групп [{id, title}, ...].
    """
    if not GK_GROUPS_CONFIG_PATH.exists():
        logger.warning("Файл конфигурации групп не найден: %s", GK_GROUPS_CONFIG_PATH)
        return []

    try:
        with open(GK_GROUPS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("groups", [])
    except (json.JSONDecodeError, IOError) as exc:
        logger.error("Ошибка чтения конфигурации групп: %s", exc)
        return []


def save_groups_config(groups: List[Dict[str, Any]]) -> None:
    """
    Сохранить конфигурацию групп в JSON.

    Args:
        groups: Список групп [{id, title}, ...].
    """
    GK_GROUPS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"groups": groups}
    with open(GK_GROUPS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logger.info("Конфигурация групп сохранена: %d групп", len(groups))


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
        self._groups = groups if groups is not None else load_groups_config()
        self._group_ids = {g["id"] for g in self._groups}
        self._group_titles = {g["id"]: g.get("title", "") for g in self._groups}
        self._stop_event = asyncio.Event()

    @property
    def group_ids(self) -> set:
        """Множество отслеживаемых group_id."""
        return self._group_ids

    async def handle_new_message(self, event) -> None:
        """
        Обработать новое сообщение из группы.

        Args:
            event: Telethon NewMessage event.
        """
        message = event.message

        # Пропустить служебные сообщения
        if not message or message.action:
            return

        # Извлечь chat_id
        chat_id = self._get_chat_id(event)
        if chat_id not in self._group_ids:
            return

        # Пропустить слишком старые сообщения (при реконнекте)
        if message.date:
            msg_age = time.time() - message.date.timestamp()
            if msg_age > MAX_MESSAGE_AGE_SECONDS:
                logger.debug(
                    "Пропущено старое сообщение: group=%d msg=%d age=%ds",
                    chat_id, message.id, int(msg_age),
                )
                return

        # Пропустить сообщения от ботов
        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            return

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

        # Сохранить в БД
        try:
            msg_db_id = gk_db.store_message(msg_obj)
            logger.info(
                "Сообщение сохранено: group=%d msg_tg=%d db_id=%d sender=%s has_image=%s",
                chat_id, message.id, msg_db_id, sender_name, has_image,
            )
        except Exception as exc:
            logger.error(
                "Ошибка сохранения сообщения: group=%d msg=%d error=%s",
                chat_id, message.id, exc,
                exc_info=True,
            )
            return

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
            gid = group_info["id"]
            title = group_info.get("title", "")
            logger.info(
                "Backfill: группа %d (%s), дней=%d, force=%s",
                gid, title, days, force,
            )

            try:
                entity = await self._client.get_entity(gid)
                count = 0

                async for message in self._client.iter_messages(
                    entity,
                    offset_date=None,
                    reverse=False,
                ):
                    if message.date and message.date.timestamp() < cutoff_date.timestamp():
                        break

                    if message.action:
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
                        message_date=int(message.date.timestamp()) if message.date else 0,
                    )

                    try:
                        existing_message = gk_db.get_message_by_telegram_id(gid, message.id)
                        if existing_message and not force:
                            continue

                        msg_db_id = gk_db.store_message(msg_obj)

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

                    # Rate limit: пауза каждые 100 сообщений
                    if count % 100 == 0:
                        logger.info("Backfill: группа %d — собрано %d сообщений...", gid, count)
                        await asyncio.sleep(1.0)

                total_collected += count
                logger.info(
                    "Backfill завершён для группы %d (%s): %d сообщений",
                    gid, title, count,
                )
            except Exception as exc:
                logger.error(
                    "Ошибка backfill для группы %d: %s",
                    gid, exc,
                    exc_info=True,
                )

        return total_collected

    def stop(self) -> None:
        """Послать сигнал остановки."""
        self._stop_event.set()

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
