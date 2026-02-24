"""
rag_service.py — сервис базы знаний (RAG) для AI-маршрутизации.

Отвечает за:
- приём и парсинг документов,
- разбиение на чанки,
- хранение чанков в БД,
- retrieval релевантных фрагментов,
- кэширование ответов.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import asyncio
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import src.common.database as database

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings
from src.sbs_helper_telegram_bot.ai_router.prompts import build_rag_prompt, build_rag_summary_prompt

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-zа-яё0-9]{3,}", re.IGNORECASE)
_SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx", ".md", ".html", ".htm"}
_RAG_CHUNK_SCAN_LIMIT = 3000
_RAG_SUMMARY_SCAN_LIMIT = 3000
_RAG_SUMMARY_SCORE_WEIGHT = 0.35


@dataclass
class CachedAnswer:
    """Элемент TTL-кэша ответа RAG."""

    answer: str
    expires_at: float


class RagKnowledgeService:
    """Сервис работы с базой знаний RAG."""

    def __init__(self, cache_ttl_seconds: int = ai_settings.AI_RAG_CACHE_TTL_SECONDS):
        self._cache_ttl_seconds = cache_ttl_seconds
        self._answer_cache: Dict[str, CachedAnswer] = {}

    @staticmethod
    def is_supported_file(filename: str) -> bool:
        """Проверить поддерживаемое расширение файла."""
        lower_name = (filename or "").lower()
        return any(lower_name.endswith(ext) for ext in _SUPPORTED_EXTENSIONS)

    def ingest_document_from_bytes(
        self,
        filename: str,
        payload: bytes,
        uploaded_by: int,
        source_type: str = "telegram",
        source_url: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Загрузить документ в базу знаний.

        Args:
            filename: Имя файла.
            payload: Байтовое содержимое файла.
            uploaded_by: Telegram ID администратора.
            source_type: Тип источника.
            source_url: URL источника (если применимо).

        Returns:
            Статистика загрузки документа.
        """
        if not filename:
            raise ValueError("Пустое имя файла")

        if not self.is_supported_file(filename):
            raise ValueError("Неподдерживаемый формат файла")

        max_bytes = ai_settings.AI_RAG_MAX_FILE_SIZE_MB * 1024 * 1024
        if len(payload) > max_bytes:
            raise ValueError("Файл слишком большой")

        content_hash = hashlib.sha256(payload).hexdigest()

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT id, status FROM rag_documents
                    WHERE content_hash = %s
                    LIMIT 1
                    """,
                    (content_hash,),
                )
                existing = cursor.fetchone()
                if existing:
                    existing_id = int(existing["id"])
                    existing_status = str(existing.get("status") or "")

                    if existing_status != "active":
                        cursor.execute(
                            """
                            UPDATE rag_documents
                            SET
                                filename = %s,
                                source_type = %s,
                                source_url = %s,
                                uploaded_by = %s,
                                status = 'active',
                                updated_at = NOW()
                            WHERE id = %s
                            """,
                            (filename, source_type, source_url, uploaded_by, existing_id),
                        )
                        self._bump_corpus_version(
                            cursor,
                            f"reactivate:{existing_id}:{uploaded_by}:{filename}",
                        )
                        self._clear_expired_cache()
                        logger.info(
                            "RAG ingest reactivated existing document: file=%s document_id=%s old_status=%s uploaded_by=%s",
                            filename,
                            existing_id,
                            existing_status,
                            uploaded_by,
                        )
                        return {
                            "document_id": existing_id,
                            "chunks_count": 0,
                            "is_duplicate": 1,
                            "reactivated": 1,
                        }

                    return {
                        "document_id": existing_id,
                        "chunks_count": 0,
                        "is_duplicate": 1,
                        "reactivated": 0,
                    }

        if self._is_html_file(filename):
            chunks = self._split_html_payload(payload)
        else:
            extracted_text = self._extract_text(filename, payload)
            chunks = self._split_text(extracted_text)

        if not chunks:
            raise ValueError("В документе не найден полезный текст")

        limited_chunks = chunks[: ai_settings.AI_RAG_MAX_CHUNKS_PER_DOC]
        summary_text, summary_model_name = self._generate_document_summary(
            filename,
            limited_chunks,
            user_id=uploaded_by,
        )

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO rag_documents
                        (filename, source_type, source_url, uploaded_by, status, content_hash, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'active', %s, NOW(), NOW())
                    """,
                    (filename, source_type, source_url, uploaded_by, content_hash),
                )
                document_id = int(cursor.lastrowid)

                for idx, chunk in enumerate(limited_chunks):
                    cursor.execute(
                        """
                        INSERT INTO rag_chunks
                            (document_id, chunk_index, chunk_text, created_at)
                        VALUES (%s, %s, %s, NOW())
                        """,
                        (document_id, idx, chunk),
                    )

                self._upsert_document_summary(
                    cursor=cursor,
                    document_id=document_id,
                    summary_text=summary_text,
                    model_name=summary_model_name,
                )
                self._bump_corpus_version(cursor, f"upload:{filename}")

        self._clear_expired_cache()
        logger.info(
            "RAG ingest success: file=%s document_id=%s chunks=%s uploaded_by=%s",
            filename,
            document_id,
            len(limited_chunks),
            uploaded_by,
        )

        return {
            "document_id": document_id,
            "chunks_count": len(limited_chunks),
            "is_duplicate": 0,
        }

    def _generate_document_summary(
        self,
        filename: str,
        chunks: List[str],
        user_id: Optional[int] = None,
    ) -> Tuple[str, Optional[str]]:
        """Сгенерировать summary документа с fallback на extractive-режим."""
        fallback_summary = self._build_fallback_summary(chunks)
        if not ai_settings.AI_RAG_SUMMARY_ENABLED:
            return fallback_summary, None

        excerpt = self._build_summary_excerpt(chunks)
        if not excerpt:
            return fallback_summary, None

        try:
            running_loop = asyncio.get_running_loop()
            if running_loop and running_loop.is_running():
                return fallback_summary, None
        except RuntimeError:
            pass

        try:
            from src.sbs_helper_telegram_bot.ai_router.llm_provider import get_provider

            provider = get_provider()
            system_prompt = build_rag_summary_prompt(
                document_name=filename,
                document_excerpt=excerpt,
                max_summary_chars=ai_settings.AI_RAG_SUMMARY_MAX_CHARS,
            )

            async def _request_summary() -> str:
                return await provider.chat(
                    messages=[{"role": "user", "content": "Сформируй summary документа."}],
                    system_prompt=system_prompt,
                    user_id=user_id,
                    purpose="rag_summary",
                )

            raw_summary = asyncio.run(_request_summary())
            normalized_summary = self._normalize_summary_text(raw_summary)
            if normalized_summary:
                return normalized_summary, provider.get_model_name(purpose="response")
        except Exception as exc:
            logger.warning("Не удалось сгенерировать AI-summary для %s: %s", filename, exc)

        return fallback_summary, None

    @staticmethod
    def _build_summary_excerpt(chunks: List[str]) -> str:
        """Собрать ограниченный по длине фрагмент документа для суммаризации."""
        if not chunks:
            return ""

        max_chars = max(500, int(ai_settings.AI_RAG_SUMMARY_INPUT_MAX_CHARS))
        collected: List[str] = []
        current_len = 0

        for chunk in chunks:
            normalized_chunk = (chunk or "").strip()
            if not normalized_chunk:
                continue

            remaining = max_chars - current_len
            if remaining <= 0:
                break

            piece = normalized_chunk[:remaining]
            if piece:
                collected.append(piece)
                current_len += len(piece)

        return "\n\n".join(collected).strip()

    @staticmethod
    def _build_fallback_summary(chunks: List[str]) -> str:
        """Сформировать детерминированный fallback-summary из первых предложений документа."""
        excerpt = RagKnowledgeService._build_summary_excerpt(chunks)
        if not excerpt:
            return "Краткое summary недоступно: в документе не найден информативный текст."

        sentence_parts = re.split(r"(?<=[.!?])\s+", excerpt)
        selected = [part.strip() for part in sentence_parts if part.strip()][:8]
        if not selected:
            selected = [excerpt[: ai_settings.AI_RAG_SUMMARY_MAX_CHARS].strip()]

        fallback_text = " ".join(selected).strip()
        max_chars = max(200, int(ai_settings.AI_RAG_SUMMARY_MAX_CHARS))
        return fallback_text[:max_chars].strip()

    @staticmethod
    def _normalize_summary_text(summary_text: str) -> str:
        """Нормализовать итоговый текст summary перед сохранением."""
        normalized = re.sub(r"\s+", " ", (summary_text or "").strip())
        if not normalized:
            return ""
        max_chars = max(200, int(ai_settings.AI_RAG_SUMMARY_MAX_CHARS))
        return normalized[:max_chars].strip()

    @staticmethod
    def _upsert_document_summary(cursor, document_id: int, summary_text: str, model_name: Optional[str]) -> None:
        """Создать или обновить summary документа в rag_document_summaries."""
        safe_summary = (summary_text or "").strip()
        if not safe_summary:
            return

        cursor.execute(
            """
            INSERT INTO rag_document_summaries (document_id, summary_text, model_name, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                summary_text = VALUES(summary_text),
                model_name = VALUES(model_name),
                updated_at = NOW()
            """,
            (document_id, safe_summary, model_name),
        )

    def list_documents(self, status: Optional[str] = None, limit: int = 20) -> List[Dict[str, object]]:
        """
        Получить список документов базы знаний.

        Args:
            status: Фильтр по статусу (active/archived/deleted) или None.
            limit: Максимальное число документов.

        Returns:
            Список документов с агрегированной статистикой.
        """
        safe_limit = max(1, min(limit, 200))
        statuses = {"active", "archived", "deleted"}

        query = """
            SELECT
                d.id,
                d.filename,
                d.source_type,
                d.source_url,
                d.uploaded_by,
                d.status,
                d.created_at,
                d.updated_at,
                COUNT(c.id) AS chunks_count
            FROM rag_documents d
            LEFT JOIN rag_chunks c ON c.document_id = d.id
        """
        params: List[object] = []

        if status and status in statuses:
            query += " WHERE d.status = %s"
            params.append(status)

        query += " GROUP BY d.id ORDER BY d.id DESC LIMIT %s"
        params.append(safe_limit)

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall() or []

        return rows

    def list_documents_by_source(
        self,
        source_type: str,
        source_url_prefix: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        """
        Получить документы по типу источника и префиксу source_url.

        Args:
            source_type: Тип источника (например, filesystem).
            source_url_prefix: Префикс source_url для фильтрации.

        Returns:
            Список документов с базовыми метаданными.
        """
        normalized_source_type = (source_type or "").strip()
        if not normalized_source_type:
            raise ValueError("Пустой source_type")

        query = """
            SELECT
                id,
                filename,
                source_type,
                source_url,
                uploaded_by,
                status,
                content_hash,
                created_at,
                updated_at
            FROM rag_documents
            WHERE source_type = %s
        """
        params: List[object] = [normalized_source_type]

        normalized_prefix = (source_url_prefix or "").strip()
        if normalized_prefix:
            query += " AND source_url LIKE %s"
            params.append(f"{normalized_prefix}%")

        query += " ORDER BY id DESC"

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, tuple(params))
                return cursor.fetchall() or []

    def get_document(self, document_id: int) -> Optional[Dict[str, object]]:
        """
        Получить детальную информацию по документу.

        Args:
            document_id: Идентификатор документа.

        Returns:
            Словарь с полями документа или None.
        """
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        d.id,
                        d.filename,
                        d.source_type,
                        d.source_url,
                        d.uploaded_by,
                        d.status,
                        d.content_hash,
                        d.created_at,
                        d.updated_at,
                        COUNT(c.id) AS chunks_count
                    FROM rag_documents d
                    LEFT JOIN rag_chunks c ON c.document_id = d.id
                    WHERE d.id = %s
                    GROUP BY d.id
                    LIMIT 1
                    """,
                    (document_id,),
                )
                return cursor.fetchone()

    def set_document_status(self, document_id: int, new_status: str, updated_by: int) -> bool:
        """
        Изменить статус документа (архивация/восстановление/мягкое удаление).

        Args:
            document_id: Идентификатор документа.
            new_status: Новый статус (active/archived/deleted).
            updated_by: ID администратора, выполняющего действие.

        Returns:
            True при успешном изменении, False если документ не найден.
        """
        allowed_statuses = {"active", "archived", "deleted"}
        if new_status not in allowed_statuses:
            raise ValueError("Некорректный статус документа")

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT status, filename FROM rag_documents WHERE id = %s LIMIT 1",
                    (document_id,),
                )
                existing = cursor.fetchone()
                if not existing:
                    return False

                old_status = str(existing.get("status", ""))
                filename = str(existing.get("filename", "document"))

                if old_status == new_status:
                    return True

                cursor.execute(
                    """
                    UPDATE rag_documents
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_status, document_id),
                )

                if old_status == "active" or new_status == "active":
                    self._bump_corpus_version(
                        cursor,
                        f"status:{document_id}:{old_status}->{new_status}:{updated_by}:{filename}",
                    )

        self._clear_expired_cache()
        logger.info(
            "RAG document status changed: document_id=%s old=%s new=%s by=%s",
            document_id,
            old_status,
            new_status,
            updated_by,
        )
        return True

    def delete_document(self, document_id: int, updated_by: int, hard_delete: bool = False) -> bool:
        """
        Удалить документ из базы знаний.

        Args:
            document_id: Идентификатор документа.
            updated_by: ID администратора.
            hard_delete: True для физического удаления, иначе soft-delete.

        Returns:
            True если действие выполнено, иначе False.
        """
        if not hard_delete:
            return self.set_document_status(document_id, "deleted", updated_by)

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT status, filename FROM rag_documents WHERE id = %s LIMIT 1",
                    (document_id,),
                )
                existing = cursor.fetchone()
                if not existing:
                    return False

                old_status = str(existing.get("status", ""))
                filename = str(existing.get("filename", "document"))

                cursor.execute("DELETE FROM rag_documents WHERE id = %s", (document_id,))
                if old_status == "active":
                    self._bump_corpus_version(
                        cursor,
                        f"hard_delete:{document_id}:{updated_by}:{filename}",
                    )

        self._clear_expired_cache()
        logger.info(
            "RAG document deleted: document_id=%s hard_delete=%s by=%s",
            document_id,
            hard_delete,
            updated_by,
        )
        return True

    async def answer_question(
        self,
        question: str,
        user_id: int,
    ) -> Optional[str]:
        """
        Ответить на вопрос пользователя на основе документов.

        Args:
            question: Текст вопроса.
            user_id: Telegram ID пользователя.

        Returns:
            Ответ LLM или None, если релевантных данных нет.
        """
        normalized_question = (question or "").strip()
        if len(normalized_question) < 3:
            return None

        corpus_version = self._get_corpus_version()
        cache_key = f"{corpus_version}:{normalized_question.lower()}"
        cached = self._answer_cache.get(cache_key)
        now = time.time()
        if cached and cached.expires_at > now:
            return cached.answer

        chunks, summary_blocks = self._retrieve_context_for_question(
            normalized_question,
            limit=ai_settings.AI_RAG_TOP_K,
        )
        if not chunks:
            return None

        from src.sbs_helper_telegram_bot.ai_router.llm_provider import get_provider

        context_blocks: List[str] = []
        total_chars = 0
        max_chars = ai_settings.AI_RAG_MAX_CONTEXT_CHARS

        for index, (_, source, chunk_text, _) in enumerate(chunks, start=1):
            block = f"[Блок {index} | {source}]\n{chunk_text}"
            if total_chars + len(block) > max_chars:
                break
            context_blocks.append(block)
            total_chars += len(block)

        provider = get_provider()
        answer = await provider.chat(
            messages=[{"role": "user", "content": normalized_question}],
            system_prompt=build_rag_prompt(context_blocks, summary_blocks=summary_blocks),
            user_id=user_id,
            purpose="rag_answer",
        )

        self._answer_cache[cache_key] = CachedAnswer(
            answer=answer,
            expires_at=now + self._cache_ttl_seconds,
        )
        self._clear_expired_cache()

        self._log_query(
            user_id=user_id,
            query=normalized_question,
            cache_hit=False,
            chunks_count=len(context_blocks),
        )

        return answer

    def _retrieve_context_for_question(self, question: str, limit: int) -> Tuple[List[Tuple[float, str, str, int]], List[str]]:
        """Собрать релевантные чанки и summary-блоки для RAG-ответа."""
        tokens = self._tokenize(question)
        if not tokens:
            return [], []

        prefilter_docs = self._prefilter_documents_by_summary(
            question_tokens=tokens,
            limit=ai_settings.AI_RAG_PREFILTER_TOP_DOCS,
        )
        prefilter_doc_ids = [doc_id for doc_id, _, _, _ in prefilter_docs]
        summary_scores = {doc_id: score for doc_id, _, _, score in prefilter_docs}

        chunks = self._search_relevant_chunks(
            question,
            limit=limit,
            prefiltered_doc_ids=prefilter_doc_ids or None,
            summary_scores=summary_scores,
        )
        summary_blocks = self._build_summary_blocks(prefilter_docs)
        return chunks, summary_blocks

    def _extract_text(self, filename: str, payload: bytes) -> str:
        """Извлечь текст из поддерживаемого формата документа."""
        lower_name = filename.lower()

        if lower_name.endswith(".txt") or lower_name.endswith(".md"):
            return self._decode_text_payload(payload)

        if lower_name.endswith(".html") or lower_name.endswith(".htm"):
            return self._extract_html_text(payload)

        if lower_name.endswith(".pdf"):
            return self._extract_pdf_text(payload)

        if lower_name.endswith(".docx"):
            return self._extract_docx_text(payload)

        raise ValueError("Неподдерживаемый формат файла")

    @staticmethod
    def _is_html_file(filename: str) -> bool:
        """Проверить, относится ли имя файла к HTML-формату."""
        lower_name = (filename or "").lower()
        return lower_name.endswith(".html") or lower_name.endswith(".htm")

    @staticmethod
    def _decode_text_payload(payload: bytes) -> str:
        """Декодировать текстовый файл с fallback по кодировкам."""
        for encoding in ("utf-8", "cp1251", "latin-1"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="ignore")

    @staticmethod
    def _extract_pdf_text(payload: bytes) -> str:
        """Извлечь текст из PDF документа."""
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise ValueError("Для PDF требуется пакет pypdf") from exc

        reader = PdfReader(io.BytesIO(payload))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    @staticmethod
    def _extract_docx_text(payload: bytes) -> str:
        """Извлечь текст из DOCX документа."""
        try:
            from docx import Document
        except Exception as exc:
            raise ValueError("Для DOCX требуется пакет python-docx") from exc

        doc = Document(io.BytesIO(payload))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)

    @staticmethod
    def _extract_html_text(payload: bytes) -> str:
        """Извлечь текст из HTML документа."""
        raw_html = RagKnowledgeService._decode_text_payload(payload)

        no_script = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.IGNORECASE)
        no_style = re.sub(r"<style[\s\S]*?</style>", " ", no_script, flags=re.IGNORECASE)
        no_tags = re.sub(r"<[^>]+>", " ", no_style)
        compact = re.sub(r"[ \t\r\f\v]+", " ", no_tags)
        compact = re.sub(r"\n\s*\n+", "\n", compact)
        return compact.strip()

    def _split_html_payload(self, payload: bytes) -> List[str]:
        """Разбить HTML-документ на чанки с приоритетом по заголовкам."""
        if not ai_settings.is_rag_html_splitter_enabled():
            logger.info("HTMLHeaderTextSplitter отключен через bot_settings, используется fallback")
            return self._split_text(self._extract_html_text(payload))

        raw_html = self._decode_text_payload(payload)
        header_chunks = self._split_html_with_header_splitter(raw_html)
        if header_chunks:
            return header_chunks

        logger.info("HTMLHeaderTextSplitter недоступен или не дал чанков, включен fallback")
        return self._split_text(self._extract_html_text(payload))

    def _split_html_with_header_splitter(self, raw_html: str) -> List[str]:
        """Попытаться разбить HTML через HTMLHeaderTextSplitter с переносом заголовков в текст."""
        normalized_html = (raw_html or "").strip()
        if not normalized_html:
            return []

        try:
            splitter_cls = self._get_html_header_splitter_class()
            splitter = splitter_cls(
                headers_to_split_on=[
                    ("h1", "h1"),
                    ("h2", "h2"),
                    ("h3", "h3"),
                    ("h4", "h4"),
                    ("h5", "h5"),
                    ("h6", "h6"),
                ]
            )
            documents = splitter.split_text(normalized_html)
        except Exception as exc:
            logger.warning("Не удалось применить HTMLHeaderTextSplitter: %s", exc)
            return []

        chunks: List[str] = []
        header_keys = ("h1", "h2", "h3", "h4", "h5", "h6")

        for doc in documents or []:
            page_content = str(getattr(doc, "page_content", "") or "").strip()
            metadata = getattr(doc, "metadata", {}) or {}
            metadata_values = [
                str(metadata.get(key, "")).strip() for key in header_keys if str(metadata.get(key, "")).strip()
            ]

            if not page_content and not metadata_values:
                continue

            combined_block = "\n".join(metadata_values + [page_content]).strip()
            if not combined_block:
                continue

            chunks.extend(self._split_text(combined_block))

        return [chunk for chunk in chunks if chunk.strip()]

    @staticmethod
    def _get_html_header_splitter_class():
        """Получить класс HTMLHeaderTextSplitter из доступного пространства имён."""
        if not RagKnowledgeService._is_langchain_splitter_supported():
            raise RuntimeError("LangChain splitter отключен для текущей версии Python")

        import warnings

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from langchain_text_splitters import HTMLHeaderTextSplitter
            return HTMLHeaderTextSplitter
        except Exception:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from langchain.text_splitter import HTMLHeaderTextSplitter
            return HTMLHeaderTextSplitter

    @staticmethod
    def _is_langchain_splitter_supported() -> bool:
        """Проверить, можно ли безопасно использовать LangChain splitters в текущем Python."""
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from langchain_text_splitters import HTMLHeaderTextSplitter  # noqa: F401
            return True
        except Exception:
            pass
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from langchain.text_splitter import HTMLHeaderTextSplitter  # noqa: F401
            return True
        except Exception:
            logger.info(
                "LangChain splitters недоступны на Python %s.%s: используется fallback chunking",
                sys.version_info.major,
                sys.version_info.minor,
            )
            return False

    @staticmethod
    def _split_text(text: str) -> List[str]:
        """Разбить текст на чанки; при наличии langchain использует его splitter."""
        cleaned = (text or "").strip()
        if not cleaned:
            return []

        if RagKnowledgeService._is_langchain_splitter_supported():
            try:
                from langchain.text_splitter import RecursiveCharacterTextSplitter

                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=ai_settings.AI_RAG_CHUNK_SIZE,
                    chunk_overlap=ai_settings.AI_RAG_CHUNK_OVERLAP,
                    separators=["\n\n", "\n", ". ", " ", ""],
                )
                chunks = splitter.split_text(cleaned)
                return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
            except Exception:
                pass

        chunk_size = ai_settings.AI_RAG_CHUNK_SIZE
        overlap = ai_settings.AI_RAG_CHUNK_OVERLAP
        chunks: List[str] = []
        start = 0
        text_len = len(cleaned)

        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunk = cleaned[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= text_len:
                break
            start = max(end - overlap, start + 1)

        return chunks

    def _search_relevant_chunks(
        self,
        question: str,
        limit: int,
        prefiltered_doc_ids: Optional[List[int]] = None,
        summary_scores: Optional[Dict[int, float]] = None,
    ) -> List[Tuple[float, str, str, int]]:
        """Найти релевантные чанки в БД по гибридному lexical scoring."""
        tokens = self._tokenize(question)
        if not tokens:
            return []

        safe_limit = max(1, limit)
        summary_scores = summary_scores or {}

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if prefiltered_doc_ids:
                    placeholders = ",".join(["%s"] * len(prefiltered_doc_ids))
                    cursor.execute(
                        f"""
                        SELECT c.chunk_text, d.filename, d.id AS document_id
                        FROM rag_chunks c
                        JOIN rag_documents d ON d.id = c.document_id
                        WHERE d.status = 'active' AND d.id IN ({placeholders})
                        ORDER BY c.id DESC
                        LIMIT %s
                        """,
                        tuple(prefiltered_doc_ids) + (_RAG_CHUNK_SCAN_LIMIT,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT c.chunk_text, d.filename, d.id AS document_id
                        FROM rag_chunks c
                        JOIN rag_documents d ON d.id = c.document_id
                        WHERE d.status = 'active'
                        ORDER BY c.id DESC
                        LIMIT %s
                        """,
                        (_RAG_CHUNK_SCAN_LIMIT,),
                    )
                rows = cursor.fetchall() or []

        scored: List[Tuple[float, str, str, int]] = []

        for row in rows:
            chunk_text = row.get("chunk_text") or ""
            source = row.get("filename") or "document"
            document_id = int(row.get("document_id") or 0)
            chunk_score = self._score_chunk(chunk_text, tokens)
            summary_score = summary_scores.get(document_id, 0.0)
            score = chunk_score + self._summary_score_bonus(summary_score)
            if score > 0:
                scored.append((score, source, chunk_text, document_id))

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[:safe_limit]

    def _prefilter_documents_by_summary(
        self,
        question_tokens: List[str],
        limit: int,
    ) -> List[Tuple[int, str, str, float]]:
        """Отобрать релевантные документы по таблице summary перед поиском чанков."""
        if not question_tokens:
            return []

        safe_limit = max(1, min(limit, 100))
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT s.document_id, s.summary_text, d.filename
                    FROM rag_document_summaries s
                    JOIN rag_documents d ON d.id = s.document_id
                    WHERE d.status = 'active'
                    ORDER BY s.updated_at DESC
                    LIMIT %s
                    """,
                    (_RAG_SUMMARY_SCAN_LIMIT,),
                )
                rows = cursor.fetchall() or []

        scored_docs: List[Tuple[int, str, str, float]] = []
        for row in rows:
            document_id = int(row.get("document_id") or 0)
            filename = str(row.get("filename") or "document")
            summary_text = str(row.get("summary_text") or "").strip()
            if not document_id or not summary_text:
                continue
            score = self._score_chunk(summary_text, question_tokens)
            if score <= 0:
                continue
            scored_docs.append((document_id, filename, summary_text, score))

        scored_docs.sort(key=lambda item: item[3], reverse=True)
        return scored_docs[:safe_limit]

    @staticmethod
    def _build_summary_blocks(prefilter_docs: List[Tuple[int, str, str, float]]) -> List[str]:
        """Собрать summary-блоки для системного RAG-промпта."""
        max_docs = max(0, int(ai_settings.AI_RAG_PROMPT_SUMMARY_DOCS))
        if max_docs <= 0:
            return []

        summary_blocks: List[str] = []
        for _, filename, summary_text, _ in prefilter_docs[:max_docs]:
            safe_summary = summary_text.strip()
            if not safe_summary:
                continue
            summary_blocks.append(f"[Summary | {filename}]\n{safe_summary}")
        return summary_blocks

    @staticmethod
    def _summary_score_bonus(summary_score: float) -> float:
        """Рассчитать бонус чанку на основе релевантности summary документа."""
        if summary_score <= 0:
            return 0.0
        return min(summary_score, 2.0) * _RAG_SUMMARY_SCORE_WEIGHT

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Токенизировать текст для lexical retrieval."""
        return _TOKEN_RE.findall((text or "").lower())

    @staticmethod
    def _score_chunk(chunk_text: str, question_tokens: List[str]) -> float:
        """Оценить релевантность чанка по вхождению токенов запроса."""
        low_chunk = (chunk_text or "").lower()
        if not low_chunk:
            return 0.0

        unique_tokens = set(question_tokens)
        matches = sum(1 for token in unique_tokens if token in low_chunk)
        if matches == 0:
            return 0.0

        token_coverage = matches / max(len(unique_tokens), 1)
        density_bonus = min(matches / 10.0, 0.3)
        return token_coverage + density_bonus

    @staticmethod
    def _get_corpus_version() -> int:
        """Получить текущую версию корпуса базы знаний."""
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("SELECT COALESCE(MAX(id), 0) AS version_id FROM rag_corpus_version")
                row = cursor.fetchone() or {"version_id": 0}
                return int(row.get("version_id", 0))

    @staticmethod
    def _bump_corpus_version(cursor, reason: str) -> None:
        """Увеличить версию корпуса для инвалидации кэша и retrieval-состояния."""
        cursor.execute(
            """
            INSERT INTO rag_corpus_version (reason, created_at)
            VALUES (%s, NOW())
            """,
            (reason[:255],),
        )

    def _clear_expired_cache(self) -> None:
        """Очистить протухшие элементы кэша."""
        now = time.time()
        expired = [key for key, val in self._answer_cache.items() if val.expires_at <= now]
        for key in expired:
            self._answer_cache.pop(key, None)

    @staticmethod
    def _log_query(user_id: int, query: str, cache_hit: bool, chunks_count: int) -> None:
        """Записать факт запроса к базе знаний в БД."""
        try:
            with database.get_db_connection() as conn:
                with database.get_cursor(conn) as cursor:
                    cursor.execute(
                        """
                        INSERT INTO rag_query_log (user_id, query_text, cache_hit, chunks_count, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        """,
                        (user_id, query[:1000], 1 if cache_hit else 0, chunks_count),
                    )
        except Exception as exc:
            logger.warning("Не удалось записать rag_query_log: %s", exc)


_rag_service_instance: Optional[RagKnowledgeService] = None


def get_rag_service() -> RagKnowledgeService:
    """Получить singleton-экземпляр RAG-сервиса."""
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RagKnowledgeService()
    return _rag_service_instance


def reset_rag_service() -> None:
    """Сбросить singleton-экземпляр RAG-сервиса (для тестов)."""
    global _rag_service_instance
    _rag_service_instance = None
