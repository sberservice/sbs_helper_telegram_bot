"""
rag_admin_bot_part.py — админ-обработчики загрузки документов в RAG.
"""

import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from src.common.telegram_user import check_if_user_admin
from src.core.ai.rag_service import get_rag_service

logger = logging.getLogger(__name__)

_RAG_COMMAND_HELP = (
    "Команды RAG:\n"
    "#rag list [active|archived|deleted|all] [limit]\n"
    "#rag info <id>\n"
    "#rag archive <id>\n"
    "#rag restore <id>\n"
    "#rag delete <id>\n"
    "#rag purge <id>\n"
    "#rag help"
)


def _extract_extension(filename: Optional[str]) -> str:
    """Получить расширение файла в нижнем регистре."""
    if not filename or "." not in filename:
        return ""
    return f".{filename.rsplit('.', 1)[-1].lower()}"


async def handle_rag_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Принять документ от администратора и загрузить в RAG-базу знаний.

    Для активации загрузки файл должен быть отправлен с подписью `#rag`.
    """
    if not update.message or not update.message.document:
        return

    caption = (update.message.caption or "").strip().lower()
    if not caption.startswith("#rag"):
        return

    user_id = update.effective_user.id if update.effective_user else 0
    if not check_if_user_admin(user_id):
        await update.message.reply_text(
            "⛔ У вас нет прав администратора для загрузки документов RAG.",
        )
        return

    document = update.message.document
    filename = document.file_name or "unknown"
    extension = _extract_extension(filename)

    rag_service = get_rag_service()
    if not rag_service.is_supported_file(filename):
        await update.message.reply_text(
            "⚠️ Неподдерживаемый формат. Поддерживаются: PDF, DOCX, TXT, MD, HTML.",
        )
        logger.info("RAG upload rejected: unsupported format user=%s file=%s ext=%s", user_id, filename, extension)
        return

    try:
        placeholder = await update.message.reply_text(
            "⏳ Загружаю документ в базу знаний...",
        )

        tg_file = await context.bot.get_file(document.file_id)
        payload = bytes(await tg_file.download_as_bytearray())

        result = await rag_service.ingest_document_from_bytes(
            filename=filename,
            payload=payload,
            uploaded_by=user_id,
            source_type="telegram",
            upsert_vectors=False,
        )

        if result.get("is_duplicate"):
            await placeholder.edit_text(
                "ℹ️ Документ уже загружен ранее и активен в базе знаний.",
            )
            return

        await placeholder.edit_text(
            f"✅ Документ загружен: {filename}\n"
            f"ID: {result['document_id']}\n"
            f"Чанков: {result['chunks_count']}\n\n"
            "Теперь пользователи могут задавать вопросы по содержимому.",
        )
    except Exception as exc:
        logger.error("RAG upload failed: user=%s file=%s error=%s", user_id, filename, exc)
        await update.message.reply_text(
            "❌ Не удалось загрузить документ в базу знаний. Проверьте формат файла и попробуйте снова.",
        )


def _parse_document_id(value: str) -> Optional[int]:
    """Безопасно распарсить числовой ID документа."""
    try:
        doc_id = int(value)
        if doc_id <= 0:
            return None
        return doc_id
    except (TypeError, ValueError):
        return None


def _format_documents_list(items: list[dict]) -> str:
    """Сформировать человекочитаемый список документов."""
    if not items:
        return "Список документов пуст."

    lines = ["📚 Документы RAG:"]
    for item in items:
        lines.append(
            f"- ID {item['id']} | {item['status']} | {item['filename']} | "
            f"чанков: {item['chunks_count']}"
        )
    return "\n".join(lines)


def _format_document_info(item: dict) -> str:
    """Сформировать детальную карточку документа."""
    source_url = item.get("source_url") or "-"
    return (
        "📄 Карточка документа:\n"
        f"ID: {item['id']}\n"
        f"Файл: {item['filename']}\n"
        f"Статус: {item['status']}\n"
        f"Источник: {item['source_type']}\n"
        f"URL: {source_url}\n"
        f"Загрузил: {item['uploaded_by']}\n"
        f"Чанков: {item['chunks_count']}\n"
        f"Создан: {item['created_at']}\n"
        f"Обновлён: {item['updated_at']}"
    )


async def handle_rag_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать текстовые админ-команды CRUD для RAG-документов."""
    del context

    if not update.message or not update.message.text:
        return

    raw_text = update.message.text.strip()
    if not raw_text.lower().startswith("#rag"):
        return

    user_id = update.effective_user.id if update.effective_user else 0
    if not check_if_user_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав администратора для управления RAG.")
        return

    parts = raw_text.split()
    if len(parts) == 1:
        await update.message.reply_text(_RAG_COMMAND_HELP)
        return

    action = parts[1].lower()
    rag_service = get_rag_service()

    try:
        if action == "help":
            await update.message.reply_text(_RAG_COMMAND_HELP)
            return

        if action == "list":
            status = None
            limit = 20

            if len(parts) >= 3:
                candidate = parts[2].lower()
                if candidate != "all":
                    status = candidate
            if len(parts) >= 4:
                parsed_limit = _parse_document_id(parts[3])
                if parsed_limit:
                    limit = min(parsed_limit, 100)

            documents = rag_service.list_documents(status=status, limit=limit)
            await update.message.reply_text(_format_documents_list(documents))
            return

        if action == "info":
            if len(parts) < 3:
                await update.message.reply_text("⚠️ Используйте: #rag info <id>")
                return
            doc_id = _parse_document_id(parts[2])
            if not doc_id:
                await update.message.reply_text("⚠️ Некорректный ID документа.")
                return

            document = rag_service.get_document(doc_id)
            if not document:
                await update.message.reply_text("⚠️ Документ не найден.")
                return

            await update.message.reply_text(_format_document_info(document))
            return

        if action in {"archive", "restore", "delete", "purge"}:
            if len(parts) < 3:
                await update.message.reply_text(f"⚠️ Используйте: #rag {action} <id>")
                return

            doc_id = _parse_document_id(parts[2])
            if not doc_id:
                await update.message.reply_text("⚠️ Некорректный ID документа.")
                return

            if action == "archive":
                changed = rag_service.set_document_status(doc_id, "archived", updated_by=user_id)
                await update.message.reply_text(
                    "✅ Документ архивирован." if changed else "⚠️ Документ не найден."
                )
                return

            if action == "restore":
                changed = rag_service.set_document_status(doc_id, "active", updated_by=user_id)
                await update.message.reply_text(
                    "✅ Документ восстановлен в active." if changed else "⚠️ Документ не найден."
                )
                return

            if action == "delete":
                changed = rag_service.delete_document(doc_id, updated_by=user_id, hard_delete=False)
                await update.message.reply_text(
                    "✅ Документ помечен как deleted." if changed else "⚠️ Документ не найден."
                )
                return

            changed = rag_service.delete_document(doc_id, updated_by=user_id, hard_delete=True)
            await update.message.reply_text(
                "✅ Документ удалён физически." if changed else "⚠️ Документ не найден."
            )
            return

        await update.message.reply_text(
            "⚠️ Неизвестная команда.\n" + _RAG_COMMAND_HELP
        )
    except Exception as exc:
        logger.error("RAG admin command failed: user=%s text=%s error=%s", user_id, raw_text, exc)
        await update.message.reply_text("❌ Ошибка выполнения RAG-команды.")
