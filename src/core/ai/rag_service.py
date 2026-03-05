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
import json
import logging
import re
import asyncio
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, TypeVar

import src.common.database as database

from config import ai_settings
from src.core.ai.formatters import (
    AI_PROGRESS_STAGE_RAG_CACHE_HIT,
    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED,
    AI_PROGRESS_STAGE_RAG_FALLBACK_STARTED,
    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED,
)
from src.core.ai.prompts import (
    build_hyde_prompt,
    build_rag_fallback_prompt,
    build_rag_prompt,
    build_rag_summary_prompt,
    build_spellcheck_prompt,
)
from src.core.ai.vector_search import (
    LocalEmbeddingProvider,
    LocalVectorIndex,
)

logger = logging.getLogger(__name__)

try:
    from rank_bm25 import BM25Okapi
except Exception:
    BM25Okapi = None

try:
    from symspellpy import SymSpell, Verbosity as _SymSpellVerbosity  # type: ignore[import-untyped]
except Exception:
    SymSpell = None  # type: ignore[misc,assignment]
    _SymSpellVerbosity = None  # type: ignore[misc,assignment]

_TOKEN_RE = re.compile(r"\d+(?:[\.,]\d+)+|[a-zа-яё0-9]+", re.IGNORECASE)
_SHORT_ALNUM_TOKEN_RE = re.compile(r"(?:[a-zа-яё]\d|\d[a-zа-яё])", re.IGNORECASE)

# Regex для удаления markdown code fences из JSON-ответа LLM.
_JSON_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
# Regex для извлечения первого JSON-объекта из текста.
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)
_CYRILLIC_TOKEN_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_HASHTAG_WORD_RE = re.compile(r"(?<!\S)#[a-zа-яё0-9_]+", re.IGNORECASE)
_SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx", ".md", ".html", ".htm"}

# =============================================
# Стоп-слова для русскоязычного lexical retrieval
# =============================================
# Высокочастотные функциональные слова, не несущие предметной нагрузки.
# Удаляются из query-токенов перед lexical scoring, чтобы BM25 IDF
# не завышал score документов с одинаковым шаблонным началом
# (например, «что такое X» vs «что такое Y»).
_RU_STOPWORDS: frozenset[str] = frozenset({
    # Местоимения и частицы
    "что", "это", "как", "так", "его", "все", "она", "они",
    "был", "уже", "тот", "или", "ещё", "еще", "нет", "более",
    "какой", "какая", "какое", "каком", "какие", "каких",
    "такое", "такой", "такая", "такие", "таких",
    "который", "которая", "которое", "которые",
    "этот", "этого", "этом", "этой",
    "свой", "своя", "свои", "своего",
    "можно", "нужно", "надо",
    "кто", "где", "когда", "зачем", "почему", "чего", "чем",
    "для", "при", "без", "под", "над", "между",
    "наша", "наш", "наше", "наши", "ваш", "ваша", "ваше", "ваши",
    # Союзы (≥3 символов, т.к. _TOKEN_RE ≥3)
    "чтобы", "если", "также", "тоже", 
})

# Термины, которые нельзя искажать лемматизацией/стеммингом
# и которые нужно сохранять даже при короткой длине токена.
_RAG_FIXED_QUERY_TERMS: frozenset[str] = frozenset({
    "осно", "усн", "псн", "енвд", "нпд", "сно",
    "фн", "ккт", "офд", "инн", "кпп","аусн",      # Автоматизированная УСН
    "егрип",     # ЕГРИП
    "егрюл",     # ЕГРЮЛ
    "енс",       # Единый налоговый счёт
    "есхн",      # ЕСХН
    "ип",        # Индивидуальный предприниматель
    "мрот",      # МРОТ
    "ндс",       # НДС
    "ндфл",      # НДФЛ
    "огрн",      # ОГРН
    "огрнип",    # ОГРНИП
    "оквэд",     # ОКВЭД
    "ооо",       # ООО
    "пфр",       # ПФР (до сих пор активно ищут)
    "снилс",     # СНИЛС
    "фнс",       # ФНС
    "фсс",       # ФСС
    "кбк",       # КБК
    "октмо",     # ОКТМО
    # === Новые — специально под ККТ, банковские терминалы, АРМ и банкоматы (22 шт.) ===
    "ффд",      # формат фискальных данных
    "54фз",     # 54-ФЗ (самый частый запрос)
    "фд",       # фискальный документ
    "фп",       # фискальный признак
    "фпд",      # фискальный признак документа
    "рн",       # регистрационный номер ККТ
    "зн",       # заводской номер
    "ккм",      # контрольно-кассовая машина (старое название, до сих пор ищут)
    "эклз",     # электронная контрольная лента защищённая (legacy, но запросы есть)
    "фнм",      # ФН-М (для маркировки)

    "pos",      # POS-терминал
    "пинпад",   # PIN-Pad (очень частый)
    "пин",      # PIN (в контексте пинпада)

    "арм",      # автоматизированное рабочее место
    "цто",      # центр технического обслуживания
    "то",       # техническое обслуживание

    "усо",      # устройство самообслуживания
    "атм",      # ATM / банкомат
    "банкомат", # банкомат (защищаем полностью)

    "эдо",      # электронный документооборот
    "укэп",     # усиленная квалифицированная ЭП (регистрация ККТ, договоры)
    "кэп",      # квалифицированная ЭП
    "эп",       # электронная подпись
})

# =============================================
# Паттерны типовых вопросительных конструкций
# =============================================
# Regex-паттерны «что такое X», «как работает X» и т.д., из которых
# извлекается предметная часть (X) для фокусировки lexical scoring.
_QUERY_STRIP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^\s*(?:что\s+(?:такое|значит|означает|представляет\s+собой))"
        r"\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:как\s+(?:работает|устроен|устроена|функционирует|действует|использовать|пользоваться))"
        r"\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:зачем\s+(?:нужен|нужна|нужно|нужны|используется|используют))"
        r"\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:для\s+чего\s+(?:нужен|нужна|нужно|нужны|используется|служит))"
        r"\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:в\s+чём\s+(?:разница|отличие|отличия|суть|смысл))"
        r"\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:чем\s+(?:отличается|является))"
        r"\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:расскажи|объясни|опиши)\s+(?:что\s+такое\s+|про\s+|о\s+)?"
        r"(.+)",
        re.IGNORECASE,
    ),
]
_RAG_CHUNK_SCAN_LIMIT = 6000 
_RAG_SUMMARY_SCAN_LIMIT = 6000
_RAG_EMBEDDING_UPSERT_BATCH_SIZE = 25
_RAG_EMBEDDING_UPSERT_MAX_RETRIES = 3
_RAG_EMBEDDING_RETRY_BASE_DELAY_SECONDS = 0.25
_MYSQL_RETRYABLE_ERRNOS = {1205, 1213}
_RAG_DB_OPERATION_MAX_RETRIES = 3
_RAG_DB_OPERATION_RETRY_BASE_DELAY_SECONDS = 0.25
_SPACES_RE = re.compile(r"\s+")
_RAG_SOURCE_TYPE_CERTIFICATION = "certification"
_RAG_CERTIFICATION_SOURCE_URL_PREFIX = "certification://question/"
_RAG_CERTIFICATION_FILENAME_PREFIX = "certification_q_"
_RAG_CATEGORY_CACHE_TTL_SECONDS = 300

TResult = TypeVar("TResult")


@dataclass
class CachedAnswer:
    """Элемент TTL-кэша ответа RAG."""

    answer: str
    expires_at: float
    is_fallback: bool = False


@dataclass
class RagAnswer:
    """Результат RAG-ответа с флагом fallback."""

    text: Optional[str]
    is_fallback: bool = False


class RagKnowledgeService:
    """Сервис работы с базой знаний RAG."""

    def __init__(self, cache_ttl_seconds: int = ai_settings.AI_RAG_CACHE_TTL_SECONDS):
        self._cache_ttl_seconds = cache_ttl_seconds
        self._answer_cache: Dict[str, CachedAnswer] = {}
        self._embedding_provider: Optional[LocalEmbeddingProvider] = None
        self._vector_index: Optional[LocalVectorIndex] = None
        self._summary_embedding_cache: Dict[int, List[float]] = {}
        self._summary_embedding_corpus_version: int = -1
        self._summary_vector_prefilter_source: str = "disabled"
        self._summary_vector_prefilter_hits: int = 0
        self._hyde_cache: Dict[str, Tuple[str, float]] = {}
        self._ru_morph_analyzer: Optional[object] = None
        self._ru_stemmer: Optional[object] = None
        self._normalized_token_cache: Dict[str, str] = {}
        self._normalization_dependency_warning_logged: bool = False
        self._document_signals_table_warning_logged: bool = False
        self._certification_categories_cache: List[Tuple[str, str]] = []
        self._certification_categories_cache_expires_at: float = 0.0
        # Spell-correction state
        self._spellcheck_sym: Optional[object] = None  # SymSpell instance
        self._spellcheck_vocab_size: int = 0
        self._spellcheck_vocab_ready: bool = False
        self._spellcheck_llm_cache: Dict[str, Tuple[str, List[Tuple[str, str]], float]] = {}

    def _get_cached_hyde_text(self, question: str) -> Optional[str]:
        """Получить HyDE-текст из кэша, если он не истёк.

        Возвращает ``None``, если запись отсутствует или TTL истёк.
        Очищает до 20 просроченных записей за вызов.
        """
        now = time.time()
        cached = self._hyde_cache.get(question)
        if cached is not None:
            hyde_text, expires_at = cached
            if expires_at > now:
                return hyde_text
            del self._hyde_cache[question]

        # Ленивая очистка просроченных записей
        expired_keys = [
            k for k, (_, exp) in self._hyde_cache.items() if exp <= now
        ]
        for key in expired_keys[:20]:
            self._hyde_cache.pop(key, None)

        return None

    def _cache_hyde_text(self, question: str, hyde_text: str) -> None:
        """Сохранить HyDE-текст в кэш с TTL."""
        ttl = max(1, int(ai_settings.AI_RAG_HYDE_CACHE_TTL_SECONDS))
        self._hyde_cache[question] = (hyde_text, time.time() + ttl)

    @staticmethod
    def is_supported_file(filename: str) -> bool:
        """Проверить поддерживаемое расширение файла."""
        lower_name = (filename or "").lower()
        return any(lower_name.endswith(ext) for ext in _SUPPORTED_EXTENSIONS)

    @classmethod
    def _resolve_text_slicer_name(cls) -> str:
        """Определить имя активного slicer-а для текстового chunking."""
        if not cls._is_langchain_splitter_supported():
            return "manual_window_slicer"

        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: F401

            return "RecursiveCharacterTextSplitter(langchain_text_splitters)"
        except Exception:
            try:
                from langchain.text_splitter import RecursiveCharacterTextSplitter  # noqa: F401

                return "RecursiveCharacterTextSplitter(langchain.text_splitter)"
            except Exception:
                return "manual_window_slicer"

    def get_chunking_diagnostics(self) -> Dict[str, object]:
        """Вернуть текущую диагностику стратегии чанкинга для runtime-логирования."""
        html_splitter_enabled = ai_settings.is_rag_html_splitter_enabled()
        langchain_supported = self._is_langchain_splitter_supported()

        return {
            "chunk_size": int(ai_settings.AI_RAG_CHUNK_SIZE),
            "chunk_overlap": int(ai_settings.AI_RAG_CHUNK_OVERLAP),
            "html_splitter_enabled": bool(html_splitter_enabled),
            "langchain_splitter_supported": bool(langchain_supported),
            "text_slicer": self._resolve_text_slicer_name(),
            "html_strategy": (
                "html_semantic_preserving_splitter_with_fallback"
                if html_splitter_enabled
                else "plain_text_fallback(html_splitter_disabled)"
            ),
            "plain_text_strategy": "extract_text_then_split_text",
        }

    def _log_chunking_strategy(
        self,
        *,
        file_name: str,
        file_format: str,
        strategy: str,
        chunks_count: int,
    ) -> None:
        """Записать в лог выбранную стратегию chunking для документа."""
        diagnostics = self.get_chunking_diagnostics()
        logger.info(
            "RAG chunking strategy: file=%s format=%s strategy=%s slicer=%s chunk_size=%s chunk_overlap=%s chunks=%s html_splitter_enabled=%s langchain_splitter_supported=%s",
            file_name,
            file_format,
            strategy,
            diagnostics.get("text_slicer"),
            diagnostics.get("chunk_size"),
            diagnostics.get("chunk_overlap"),
            chunks_count,
            diagnostics.get("html_splitter_enabled"),
            diagnostics.get("langchain_splitter_supported"),
        )

    def _execute_with_db_retry(self, operation_name: str, operation: Callable[[], TResult]) -> TResult:
        """Выполнить DB-операцию с retry для временных ошибок блокировок MySQL."""
        for attempt in range(1, _RAG_DB_OPERATION_MAX_RETRIES + 1):
            try:
                return operation()
            except Exception as exc:
                mysql_errno = getattr(exc, "errno", None)
                is_retryable = mysql_errno in _MYSQL_RETRYABLE_ERRNOS
                if not is_retryable or attempt >= _RAG_DB_OPERATION_MAX_RETRIES:
                    raise

                delay = _RAG_DB_OPERATION_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Повтор DB-операции после временной ошибки MySQL: operation=%s errno=%s attempt=%s/%s sleep=%.2fs",
                    operation_name,
                    mysql_errno,
                    attempt,
                    _RAG_DB_OPERATION_MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)

        raise RuntimeError(f"DB retry loop exhausted: {operation_name}")

    async def ingest_document_from_bytes(
        self,
        filename: str,
        payload: bytes,
        uploaded_by: int,
        source_type: str = "telegram",
        source_url: Optional[str] = None,
        upsert_vectors: bool = True,
        summary_model_scope: str = "default",
        preset_summary_text: Optional[str] = None,
        preset_summary_model_name: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Загрузить документ в базу знаний (async-версия).

        Offload-ит синхронные DB/IO-операции в thread executor,
        чтобы не блокировать event loop при вызове из async-контекста.

        Args:
            filename: Имя файла.
            payload: Байтовое содержимое файла.
            uploaded_by: Telegram ID администратора.
            source_type: Тип источника.
            source_url: URL источника (если применимо).
            upsert_vectors: Выполнять ли немедленный upsert векторных эмбеддингов.
            summary_model_scope: Контекст выбора модели summary (например, directory_ingest).
            preset_summary_text: Предустановленный summary (если требуется обойти LLM-суммаризацию).
            preset_summary_model_name: Имя модели/режима для предустановленного summary.

        Returns:
            Статистика загрузки документа.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.ingest_document_from_bytes_sync(
                filename=filename,
                payload=payload,
                uploaded_by=uploaded_by,
                source_type=source_type,
                source_url=source_url,
                upsert_vectors=upsert_vectors,
                summary_model_scope=summary_model_scope,
                preset_summary_text=preset_summary_text,
                preset_summary_model_name=preset_summary_model_name,
            ),
        )

    def ingest_document_from_bytes_sync(
        self,
        filename: str,
        payload: bytes,
        uploaded_by: int,
        source_type: str = "telegram",
        source_url: Optional[str] = None,
        upsert_vectors: bool = True,
        summary_model_scope: str = "default",
        preset_summary_text: Optional[str] = None,
        preset_summary_model_name: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Загрузить документ в базу знаний (синхронная версия).

        Используется скриптами и sync-кодом напрямую.
        Для async-контекста используйте ``ingest_document_from_bytes``.

        Args:
            filename: Имя файла.
            payload: Байтовое содержимое файла.
            uploaded_by: Telegram ID администратора.
            source_type: Тип источника.
            source_url: URL источника (если применимо).
            upsert_vectors: Выполнять ли немедленный upsert векторных эмбеддингов.
            summary_model_scope: Контекст выбора модели summary (например, directory_ingest).
            preset_summary_text: Предустановленный summary (если требуется обойти LLM-суммаризацию).
            preset_summary_model_name: Имя модели/режима для предустановленного summary.

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

        _reactivated_document_id: Optional[int] = None

        def _find_or_reactivate_existing_document() -> Optional[Dict[str, int]]:
            nonlocal _reactivated_document_id
            _reactivated_document_id = None
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
                    if not existing:
                        return None

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
                        _reactivated_document_id = existing_id
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

        existing_result = self._execute_with_db_retry(
            operation_name="ingest.find_or_reactivate_by_hash",
            operation=_find_or_reactivate_existing_document,
        )
        if existing_result:
            if _reactivated_document_id is not None:
                self._set_vector_document_status(_reactivated_document_id, "active")
                self._clear_expired_cache()
            return existing_result

        if self._is_html_file(filename):
            chunks = self._split_html_payload(payload, filename=filename)
        else:
            extracted_text = self._extract_text(filename, payload)
            chunks = self._split_text(extracted_text)
            self._log_chunking_strategy(
                file_name=filename,
                file_format="text",
                strategy="extract_text_then_split_text",
                chunks_count=len(chunks),
            )

        if not chunks:
            raise ValueError("В документе не найден полезный текст")

        limited_chunks = chunks[: ai_settings.AI_RAG_MAX_CHUNKS_PER_DOC]
        if (preset_summary_text or "").strip():
            summary_text = self._normalize_summary_text(str(preset_summary_text))
            summary_model_name = str(preset_summary_model_name or "certification_deterministic").strip() or None
        else:
            summary_text, summary_model_name = self._generate_document_summary(
                filename,
                limited_chunks,
                user_id=uploaded_by,
                summary_model_scope=summary_model_scope,
                source_type=source_type,
            )

        def _insert_document_and_chunks() -> Tuple[int, List[Dict[str, object]]]:
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
                    local_document_id = int(cursor.lastrowid)
                    local_inserted_vector_chunks: List[Dict[str, object]] = []

                    for idx, chunk in enumerate(limited_chunks):
                        cursor.execute(
                            """
                            INSERT INTO rag_chunks
                                (document_id, chunk_index, chunk_text, created_at)
                            VALUES (%s, %s, %s, NOW())
                            """,
                            (local_document_id, idx, chunk),
                        )
                        local_inserted_vector_chunks.append(
                            {
                                "document_id": local_document_id,
                                "chunk_index": idx,
                                "filename": filename,
                                "chunk_text": chunk,
                                "status": "active",
                            }
                        )

                    self._upsert_document_summary(
                        cursor=cursor,
                        document_id=local_document_id,
                        summary_text=summary_text,
                        model_name=summary_model_name,
                    )
                    self._bump_corpus_version(cursor, f"upload:{filename}")

            return local_document_id, local_inserted_vector_chunks

        document_id, inserted_vector_chunks = self._execute_with_db_retry(
            operation_name="ingest.insert_document_and_chunks",
            operation=_insert_document_and_chunks,
        )

        if upsert_vectors:
            self._upsert_vectors_for_chunks(inserted_vector_chunks)

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
        summary_model_scope: str = "default",
        source_type: str = "telegram",
    ) -> Tuple[str, Optional[str]]:
        """Сгенерировать summary документа с fallback на extractive-режим."""
        safe_source_type = str(source_type or "").strip().lower()
        if safe_source_type == _RAG_SOURCE_TYPE_CERTIFICATION:
            deterministic_summary = self._build_certification_deterministic_summary(chunks)
            if deterministic_summary:
                return deterministic_summary, "certification_deterministic"

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
            from src.core.ai.llm_provider import get_provider

            provider = get_provider()
            model_override: Optional[str] = None
            if summary_model_scope == "directory_ingest":
                model_override = ai_settings.get_directory_ingest_summary_model_override()
                if model_override is None and ai_settings.AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL:
                    logger.warning(
                        "Некорректное значение AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL=%s, используется модель ответов по умолчанию",
                        ai_settings.AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL,
                    )

            system_prompt = build_rag_summary_prompt(
                document_name=filename,
                document_excerpt=excerpt,
                max_summary_chars=ai_settings.AI_RAG_SUMMARY_MAX_CHARS,
            )

            async def _request_summary() -> str:
                return await provider.chat(
                    #Подумай, какие в нем могут быть отличия в сути от других подобных похожих документов, чтобы далее было проще найти именно этот документ.
                    messages=[{"role": "user", "content": "Сформируй summary документа. Подчеркни объект на который фокусируется документ. "}],
                    system_prompt=system_prompt,
                    user_id=user_id,
                    purpose="rag_summary",
                    model_override=model_override,
                )

            raw_summary = asyncio.run(_request_summary())
            normalized_summary = self._normalize_summary_text(raw_summary)
            if normalized_summary:
                if model_override:
                    return normalized_summary, ai_settings.normalize_deepseek_model(model_override)
                return normalized_summary, provider.get_model_name(purpose="rag_summary")
        except Exception as exc:
            logger.warning("Не удалось сгенерировать AI-summary для %s: %s", filename, exc)

        return fallback_summary, None

    @staticmethod
    def _build_certification_deterministic_summary(chunks: List[str]) -> str:
        """Собрать детерминированный summary для короткой пары вопрос-ответ аттестации."""
        joined = "\n".join(str(chunk or "") for chunk in chunks)
        question_match = re.search(r"Вопрос:\s*\n(.+?)(?:\n\s*\n|\Z)", joined, re.DOTALL)
        answer_match = re.search(r"Правильный ответ:\s*(.+?)(?:\n\s*\n|\Z)", joined, re.DOTALL)
        explanation_match = re.search(r"Пояснение:\s*\n(.+?)(?:\n\s*\n|\Z)", joined, re.DOTALL)
        category_match = re.search(r"Категории:\s*(.+)", joined)

        question_text = re.sub(r"\s+", " ", (question_match.group(1) if question_match else "").strip())
        answer_text = re.sub(r"\s+", " ", (answer_match.group(1) if answer_match else "").strip())
        explanation_text = re.sub(r"\s+", " ", (explanation_match.group(1) if explanation_match else "").strip())
        category_text = re.sub(r"\s+", " ", (category_match.group(1) if category_match else "").strip())

        parts: List[str] = []
        if category_text:
            parts.append(f"Категория: {category_text}.")
        if question_text:
            parts.append(f"Вопрос: {question_text}")
        if answer_text:
            parts.append(f"Правильный ответ: {answer_text}")
        if explanation_text:
            parts.append(f"Пояснение: {explanation_text}")

        summary = " ".join(parts).strip()
        return RagKnowledgeService._normalize_summary_text(summary)

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

    def _upsert_document_summary(self, cursor, document_id: int, summary_text: str, model_name: Optional[str]) -> None:
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
        self._mark_summary_embedding_stale(cursor=cursor, document_id=document_id)

    @staticmethod
    def _mark_summary_embedding_stale(cursor, document_id: int) -> None:
        """Пометить summary-эмбеддинг документа как устаревший после обновления summary."""
        if document_id <= 0:
            return
        try:
            cursor.execute(
                """
                UPDATE rag_summary_embeddings
                SET embedding_status = 'stale', updated_at = NOW()
                WHERE document_id = %s
                """,
                (document_id,),
            )
        except Exception as exc:
            logger.warning("Не удалось пометить stale rag_summary_embeddings для document_id=%s: %s", document_id, exc)

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

    def sync_certification_questions_to_rag(
        self,
        uploaded_by: int,
        upsert_vectors: bool = False,
        force_update: bool = False,
    ) -> Dict[str, int]:
        """Синхронизировать пары вопрос-ответ аттестации в RAG-корпус."""
        stats = {
            "questions_total": 0,
            "ingested": 0,
            "updated": 0,
            "unchanged": 0,
            "purged": 0,
            "errors": 0,
        }

        questions = self._load_certification_questions_for_rag()
        stats["questions_total"] = len(questions)

        existing_docs = self.list_documents_by_source(
            source_type=_RAG_SOURCE_TYPE_CERTIFICATION,
            source_url_prefix=_RAG_CERTIFICATION_SOURCE_URL_PREFIX,
        )
        existing_by_source_url = {
            str(item.get("source_url") or ""): item
            for item in existing_docs
            if str(item.get("source_url") or "")
        }

        seen_source_urls: set[str] = set()

        for row in questions:
            source_url = self._build_certification_source_url(int(row.get("question_id") or 0))
            if not source_url:
                stats["errors"] += 1
                continue

            seen_source_urls.add(source_url)
            filename, payload, signal_data, deterministic_summary = self._build_certification_question_document_payload(row)
            payload_hash = hashlib.sha256(payload).hexdigest()

            existing = existing_by_source_url.get(source_url)
            existing_doc_id = int(existing.get("id") or 0) if existing else 0
            existing_hash = str(existing.get("content_hash") or "") if existing else ""

            try:
                if existing and existing_hash == payload_hash and not force_update:
                    self._upsert_document_signal(document_id=existing_doc_id, signal_data=signal_data)
                    stats["unchanged"] += 1
                    continue

                if existing_doc_id > 0:
                    self.delete_document(existing_doc_id, updated_by=uploaded_by, hard_delete=True)
                    stats["updated"] += 1

                ingest_result = self.ingest_document_from_bytes_sync(
                    filename=filename,
                    payload=payload,
                    uploaded_by=uploaded_by,
                    source_type=_RAG_SOURCE_TYPE_CERTIFICATION,
                    source_url=source_url,
                    upsert_vectors=upsert_vectors,
                    summary_model_scope="default",
                    preset_summary_text=deterministic_summary,
                    preset_summary_model_name="certification_deterministic",
                )
                new_doc_id = int(ingest_result.get("document_id") or 0)
                if new_doc_id > 0:
                    self._upsert_document_signal(document_id=new_doc_id, signal_data=signal_data)
                    if existing_doc_id <= 0:
                        stats["ingested"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.error(
                    "Ошибка синхронизации certification->RAG: question_id=%s source_url=%s error=%s",
                    row.get("question_id"),
                    source_url,
                    exc,
                )

        for source_url, existing in existing_by_source_url.items():
            if source_url in seen_source_urls:
                continue

            stale_doc_id = int(existing.get("id") or 0)
            if stale_doc_id <= 0:
                continue

            try:
                if self.delete_document(stale_doc_id, updated_by=uploaded_by, hard_delete=True):
                    stats["purged"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.error(
                    "Ошибка purge устаревшего certification RAG-документа: document_id=%s source_url=%s error=%s",
                    stale_doc_id,
                    source_url,
                    exc,
                )

        logger.info("Certification->RAG sync завершён: %s", stats)
        return stats

    @staticmethod
    def _build_certification_source_url(question_id: int) -> str:
        """Собрать стабильный source_url для сертификационного вопроса."""
        safe_question_id = int(question_id or 0)
        if safe_question_id <= 0:
            return ""
        return f"{_RAG_CERTIFICATION_SOURCE_URL_PREFIX}{safe_question_id}"

    def _load_certification_questions_for_rag(self) -> List[Dict[str, object]]:
        """Загрузить вопросы аттестации с категориями и текстом правильного ответа."""
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        q.id AS question_id,
                        q.question_text,
                        q.option_a,
                        q.option_b,
                        q.option_c,
                        q.option_d,
                        q.correct_option,
                        q.explanation,
                        q.difficulty,
                        q.relevance_date,
                        q.active,
                        q.updated_timestamp,
                        GROUP_CONCAT(DISTINCT c.name ORDER BY c.display_order SEPARATOR '||') AS category_names
                    FROM certification_questions q
                    LEFT JOIN certification_question_categories qc ON qc.question_id = q.id
                    LEFT JOIN certification_categories c ON c.id = qc.category_id
                    GROUP BY q.id
                    ORDER BY q.id ASC
                    """
                )
                return cursor.fetchall() or []

    @staticmethod
    def _resolve_correct_option_text(row: Dict[str, object]) -> str:
        """Получить текст правильного варианта на основе значения `correct_option`."""
        option_key = str(row.get("correct_option") or "").strip().upper()
        option_map = {
            "A": str(row.get("option_a") or "").strip(),
            "B": str(row.get("option_b") or "").strip(),
            "C": str(row.get("option_c") or "").strip(),
            "D": str(row.get("option_d") or "").strip(),
        }
        option_text = option_map.get(option_key, "")
        if not option_text:
            return ""
        return option_text

    def _build_certification_question_document_payload(
        self,
        row: Dict[str, object],
    ) -> Tuple[str, bytes, Dict[str, object], str]:
        """Сформировать markdown-документ для RAG из вопроса аттестации."""
        question_id = int(row.get("question_id") or 0)
        question_text = str(row.get("question_text") or "").strip()
        explanation = str(row.get("explanation") or "").strip()
        difficulty = str(row.get("difficulty") or "").strip()
        correct_option = str(row.get("correct_option") or "").strip().upper()
        category_names_raw = str(row.get("category_names") or "").strip()
        category_names = [name.strip() for name in category_names_raw.split("||") if name.strip()]
        category_names = list(dict.fromkeys(category_names))
        category_keys = [self._normalize_category_key(name) for name in category_names if name.strip()]
        category_keys = [key for key in category_keys if key]

        relevance_date_raw = row.get("relevance_date")
        relevance_date_text = str(relevance_date_raw) if relevance_date_raw is not None else ""

        active_flag = int(row.get("active") or 0) == 1
        is_outdated = False
        if relevance_date_text:
            try:
                parsed_relevance = time.strptime(relevance_date_text, "%Y-%m-%d")
                today = time.localtime()
                is_outdated = (parsed_relevance.tm_year, parsed_relevance.tm_yday) < (today.tm_year, today.tm_yday)
            except Exception:
                is_outdated = False

        correct_option_text = self._resolve_correct_option_text(row)
        categories_line = ", ".join(category_names) if category_names else "Без категории"

        content_lines = [
            f"Категория: {categories_line}",
            "",
            "Вопрос:",
            question_text,
            "",
            f"Правильный ответ: {correct_option_text or correct_option}",
        ]

        if explanation:
            content_lines.extend(["", "Пояснение:", explanation])

        payload = "\n".join(content_lines).strip().encode("utf-8")
        filename = f"certification_q_{question_id}.md"
        signal_data: Dict[str, object] = {
            "domain_key": _RAG_SOURCE_TYPE_CERTIFICATION,
            "question_id": question_id,
            "is_active": 1 if active_flag else 0,
            "is_outdated": 1 if is_outdated else 0,
            "relevance_date": relevance_date_text or None,
            "category_keys_json": json.dumps(category_keys, ensure_ascii=False),
            "category_labels_json": json.dumps(category_names, ensure_ascii=False),
        }
        deterministic_summary = self._normalize_summary_text(
            " ".join(
                part
                for part in [
                    f"Категория: {categories_line}." if categories_line else "",
                    f"Вопрос: {question_text}" if question_text else "",
                    f"Правильный ответ: {correct_option_text or correct_option}" if (correct_option_text or correct_option) else "",
                    f"Пояснение: {explanation}" if explanation else "",
                ]
                if part
            )
        )
        return filename, payload, signal_data, deterministic_summary

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

        def _update_status_in_db() -> Optional[Tuple[bool, str]]:
            """Обновить статус в MySQL. Возвращает (changed, old_status) или None."""
            with database.get_db_connection() as conn:
                with database.get_cursor(conn) as cursor:
                    cursor.execute(
                        "SELECT status, filename FROM rag_documents WHERE id = %s LIMIT 1",
                        (document_id,),
                    )
                    existing = cursor.fetchone()
                    if not existing:
                        return None

                    old_status = str(existing.get("status", ""))
                    filename = str(existing.get("filename", "document"))

                    if old_status == new_status:
                        return (False, old_status)

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

            return (True, old_status)

        result = self._execute_with_db_retry("set_document_status", _update_status_in_db)
        if result is None:
            return False

        changed, old_status = result
        if not changed:
            return True

        self._set_vector_document_status(document_id, new_status)
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

        def _delete_from_db() -> bool:
            """Удалить документ из MySQL. Возвращает True если удалён, False если не найден."""
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
            return True

        deleted = self._execute_with_db_retry("delete_document", _delete_from_db)
        if not deleted:
            return False

        self._delete_vector_document(document_id)
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
        on_progress: Optional[Callable[[str, Optional[Dict[str, Any]]], Awaitable[None]]] = None,
        category_hint: Optional[str] = None,
    ) -> RagAnswer:
        """
        Ответить на вопрос пользователя на основе документов.

        Основной RAG-ответ использует JSON Mode: LLM возвращает
        {"answer": "...", "question_answered": true/false}.
        Если question_answered=false и summary-fallback включён,
        выполняется дополнительный LLM-вызов по summary документов.

        Args:
            question: Текст вопроса.
            user_id: Telegram ID пользователя.
            on_progress: Опциональный callback прогресса.
            category_hint: Подсказка категории для ранжирования.

        Returns:
            RagAnswer с текстом ответа и флагом is_fallback.
        """
        async def _emit_progress(stage: str, payload: Optional[Dict[str, Any]] = None) -> None:
            """Безопасно отправить событие прогресса во внешний callback."""
            if on_progress is None:
                return
            try:
                await on_progress(stage, payload)
            except Exception as progress_exc:
                logger.warning(
                    "RAG progress callback failed: stage=%s user_id=%s error_type=%s error_repr=%r",
                    stage,
                    user_id,
                    type(progress_exc).__name__,
                    progress_exc,
                )

        normalized_question = (question or "").strip()
        if len(normalized_question) < 3:
            return RagAnswer(text=None)

        # --- Spell-correction: исправление опечаток перед retrieval ---
        spellcheck_source = "disabled"
        spellcheck_changes: List[Tuple[str, str]] = []
        spellcheck_llm_triggered = False

        if ai_settings.is_rag_spellcheck_enabled() and self._spellcheck_vocab_ready:
            # Corpus-based коррекция (синхронная, <1ms)
            corrected_q, corpus_changes, corpus_source = self._apply_spellcheck_to_question(
                normalized_question,
            )
            spellcheck_source = corpus_source
            spellcheck_changes = list(corpus_changes)

            if corpus_changes:
                normalized_question = corrected_q

            # LLM fallback: если corpus-based не справился с достаточной долей suspicious-токенов
            if ai_settings.is_rag_spellcheck_llm_fallback_enabled():
                original_tokens = _TOKEN_RE.findall((question or "").lower())
                uncorrected, suspicious_total = self._get_suspicious_uncorrected_count(
                    original_tokens, corpus_changes,
                )
                threshold = max(0.0, min(1.0, float(ai_settings.AI_RAG_SPELLCHECK_LLM_FALLBACK_THRESHOLD)))
                if suspicious_total > 0 and (uncorrected / suspicious_total) >= threshold:
                    spellcheck_llm_triggered = True
                    llm_corrected, llm_changes = await self._spellcheck_llm_fallback(
                        normalized_question,
                        user_id=user_id,
                    )
                    if llm_changes:
                        normalized_question = llm_corrected
                        spellcheck_changes.extend(llm_changes)
                        spellcheck_source = "corpus+llm" if corpus_changes else "llm"

        # Сохраняем метаданные spellcheck для передачи в retrieval
        self._last_spellcheck_source = spellcheck_source
        self._last_spellcheck_changes = spellcheck_changes
        self._last_spellcheck_llm_triggered = spellcheck_llm_triggered

        corpus_version = self._get_corpus_version()
        cache_key = f"{corpus_version}:{normalized_question.lower()}"
        cached = self._answer_cache.get(cache_key)
        now = time.time()
        if cached and cached.expires_at > now:
            ttl_remaining = max(0.0, cached.expires_at - now)
            logger.info(
                "RAG answer cache hit: user_id=%s corpus_version=%s question='%.120s' ttl_remaining_s=%.2f is_fallback=%s",
                user_id,
                corpus_version,
                normalized_question,
                ttl_remaining,
                cached.is_fallback,
            )
            await _emit_progress(
                AI_PROGRESS_STAGE_RAG_CACHE_HIT,
                {
                    "cache_key": cache_key,
                    "cache_ttl_remaining_seconds": ttl_remaining,
                },
            )
            return RagAnswer(text=cached.answer, is_fallback=cached.is_fallback)

        cache_miss_reason = "expired" if cached else "not_found"
        logger.info(
            "RAG answer cache miss: user_id=%s corpus_version=%s question='%.120s' reason=%s",
            user_id,
            corpus_version,
            normalized_question,
            cache_miss_reason,
        )

        await _emit_progress(AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED)

        # --- HyDE: генерация гипотетического документа для vector search ---
        hyde_text: Optional[str] = None
        if ai_settings.is_rag_hyde_enabled():
            hyde_text = self._get_cached_hyde_text(normalized_question)
            if hyde_text is not None:
                logger.info(
                    "HyDE cache hit: question='%.60s' hyde_len=%d",
                    normalized_question,
                    len(hyde_text),
                )
            else:
                try:
                    from src.core.ai.llm_provider import get_provider as _get_hyde_provider

                    hyde_provider = _get_hyde_provider()
                    hyde_max_chars = max(50, int(ai_settings.AI_RAG_HYDE_MAX_CHARS))
                    hyde_text = await hyde_provider.chat(
                        messages=[{"role": "user", "content": normalized_question}],
                        system_prompt=build_hyde_prompt(normalized_question, hyde_max_chars),
                        user_id=user_id,
                        purpose="response",
                    )
                    if hyde_text:
                        hyde_text = hyde_text.strip()[:hyde_max_chars]
                        self._cache_hyde_text(normalized_question, hyde_text)
                        logger.info(
                            "HyDE generated: question='%.60s' hyde_len=%d",
                            normalized_question,
                            len(hyde_text),
                        )
                    else:
                        hyde_text = None
                except Exception as hyde_exc:
                    logger.warning(
                        "HyDE generation failed, proceeding without HyDE: "
                        "question='%.60s' error_type=%s error=%r",
                        normalized_question,
                        type(hyde_exc).__name__,
                        hyde_exc,
                    )
                    hyde_text = None

        chunks, summary_blocks = await asyncio.to_thread(
            self._retrieve_context_for_question,
            normalized_question,
            limit=ai_settings.AI_RAG_TOP_K,
            category_hint=category_hint,
            hyde_text=hyde_text,
        )
        if not chunks:
            # Нет чанков — попробовать summary-fallback напрямую
            return await self._try_summary_fallback(
                normalized_question,
                user_id=user_id,
                hyde_text=hyde_text,
                cache_key=cache_key,
                now=now,
                _emit_progress=_emit_progress,
            )

        from src.core.ai.llm_provider import get_provider

        context_blocks: List[str] = []
        total_chars = 0
        max_chars = ai_settings.AI_RAG_MAX_CONTEXT_CHARS

        for index, chunk in enumerate(chunks, start=1):
            _, source, chunk_text, _document_id, _chunk_index = self._unpack_chunk_row(chunk)
            block = f"[Блок {index} | {source}]\n{chunk_text}"
            if total_chars + len(block) > max_chars:
                break
            context_blocks.append(block)
            total_chars += len(block)

        provider = get_provider()
        await _emit_progress(
            AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED,
            {
                "chunks_count": len(context_blocks),
                "summary_blocks_count": len(summary_blocks),
            },
        )
        raw_answer = await provider.chat(
            messages=[{"role": "user", "content": normalized_question}],
            system_prompt=build_rag_prompt(context_blocks, summary_blocks=summary_blocks),
            user_id=user_id,
            purpose="rag_answer",
            response_format={"type": "json_object"},
        )

        answer_text, question_answered = self._parse_rag_json_response(raw_answer)

        if not question_answered:
            logger.info(
                "RAG primary answer marked as not answered: user_id=%s question='%.120s' "
                "answer_preview='%.120s'",
                user_id,
                normalized_question,
                answer_text,
            )
            return await self._try_summary_fallback(
                normalized_question,
                user_id=user_id,
                hyde_text=hyde_text,
                cache_key=cache_key,
                now=now,
                _emit_progress=_emit_progress,
            )

        self._answer_cache[cache_key] = CachedAnswer(
            answer=answer_text,
            expires_at=now + self._cache_ttl_seconds,
            is_fallback=False,
        )
        self._clear_expired_cache()

        asyncio.create_task(
            asyncio.to_thread(
                self._log_query,
                user_id=user_id,
                query=normalized_question,
                cache_hit=False,
                chunks_count=len(context_blocks),
            )
        )

        return RagAnswer(text=answer_text, is_fallback=False)

    async def _try_summary_fallback(
        self,
        question: str,
        user_id: int,
        hyde_text: Optional[str],
        cache_key: str,
        now: float,
        _emit_progress: Callable[[str, Optional[Dict[str, Any]]], Awaitable[None]],
    ) -> RagAnswer:
        """Попытаться ответить пользователю на основе summary документов (fallback).

        Вызывается когда основной RAG-поиск по чанкам не дал ответа:
        либо чанки не найдены, либо LLM сообщила question_answered=false.

        Args:
            question: Нормализованный вопрос пользователя.
            user_id: Telegram ID пользователя.
            hyde_text: Опциональный HyDE-текст.
            cache_key: Ключ кэша RAG-ответа.
            now: Текущее время (time.time()).
            _emit_progress: Callback для прогресса.

        Returns:
            RagAnswer с fallback-ответом или пустым текстом.
        """
        if not ai_settings.AI_RAG_SUMMARY_FALLBACK_ENABLED:
            logger.info(
                "RAG summary fallback disabled: user_id=%s question='%.120s'",
                user_id,
                question,
            )
            return RagAnswer(text=None)

        await _emit_progress(
            AI_PROGRESS_STAGE_RAG_FALLBACK_STARTED,
            {"reason": "question_not_answered"},
        )

        fallback_blocks = await asyncio.to_thread(
            self._retrieve_summaries_for_fallback,
            question=question,
            hyde_text=hyde_text,
        )
        if not fallback_blocks:
            logger.info(
                "RAG summary fallback: no summaries found: user_id=%s question='%.120s'",
                user_id,
                question,
            )
            return RagAnswer(text=None)

        from src.core.ai.llm_provider import get_provider

        provider = get_provider()
        fallback_answer = await provider.chat(
            messages=[{"role": "user", "content": question}],
            system_prompt=build_rag_fallback_prompt(fallback_blocks),
            user_id=user_id,
            purpose="rag_fallback",
        )

        if not fallback_answer or not fallback_answer.strip():
            logger.warning(
                "RAG summary fallback: LLM returned empty answer: user_id=%s question='%.120s'",
                user_id,
                question,
            )
            return RagAnswer(text=None)

        fallback_answer = fallback_answer.strip()
        logger.info(
            "RAG summary fallback answer generated: user_id=%s question='%.120s' "
            "summary_blocks=%d answer_len=%d",
            user_id,
            question,
            len(fallback_blocks),
            len(fallback_answer),
        )

        fallback_cache_key = f"fallback:{cache_key}"
        self._answer_cache[fallback_cache_key] = CachedAnswer(
            answer=fallback_answer,
            expires_at=now + self._cache_ttl_seconds,
            is_fallback=True,
        )
        self._answer_cache[cache_key] = CachedAnswer(
            answer=fallback_answer,
            expires_at=now + self._cache_ttl_seconds,
            is_fallback=True,
        )
        self._clear_expired_cache()

        asyncio.create_task(
            asyncio.to_thread(
                self._log_query,
                user_id=user_id,
                query=question,
                cache_hit=False,
                chunks_count=0,
            )
        )

        return RagAnswer(text=fallback_answer, is_fallback=True)

    def _retrieve_context_for_question(
        self,
        question: str,
        limit: int,
        category_hint: Optional[str] = None,
        hyde_text: Optional[str] = None,
    ) -> Tuple[List[Tuple[float, str, str, int]], List[str]]:
        """Собрать релевантные чанки и summary-блоки для RAG-ответа."""
        retrieval_started_at = time.perf_counter()
        tokens = self._tokenize(question)
        if not tokens:
            return [], []

        # --- Query preprocessing: pattern stripping + stopword filtering ---
        stripped_question, pattern_stripped = self._strip_query_patterns(question)
        stripped_result_for_log = _SPACES_RE.sub(" ", str(stripped_question or "").strip())
        if len(stripped_result_for_log) > 160:
            stripped_result_for_log = f"{stripped_result_for_log[:159]}…"
        if pattern_stripped:
            retrieval_tokens = self._tokenize(stripped_question)
        else:
            retrieval_tokens = list(tokens)
        original_token_count = len(retrieval_tokens)
        retrieval_tokens = self._filter_stopwords(retrieval_tokens)
        stopwords_removed = original_token_count - len(retrieval_tokens)
        post_stopwords_result_for_log = " ".join(retrieval_tokens).strip()
        if len(post_stopwords_result_for_log) > 160:
            post_stopwords_result_for_log = f"{post_stopwords_result_for_log[:159]}…"
        # Если после preprocessing нет токенов — используем исходные
        if not retrieval_tokens:
            retrieval_tokens = tokens
            post_stopwords_result_for_log = " ".join(retrieval_tokens).strip()
            if len(post_stopwords_result_for_log) > 160:
                post_stopwords_result_for_log = f"{post_stopwords_result_for_log[:159]}…"

        # --- HyDE lexical augmentation: добавить уникальные HyDE-токены для BM25 ---
        hyde_augmented_count = 0
        if hyde_text and ai_settings.is_rag_hyde_lexical_enabled():
            pre_hyde_count = len(retrieval_tokens)
            retrieval_tokens = self._augment_tokens_with_hyde(retrieval_tokens, hyde_text)
            hyde_augmented_count = len(retrieval_tokens) - pre_hyde_count

        logger.info(
            "%s",
            self._build_query_preprocessing_log_table(
                original_tokens_count=len(tokens),
                retrieval_tokens_count=len(retrieval_tokens),
                stopwords_removed=stopwords_removed,
                pattern_stripped=pattern_stripped,
                hyde_status=f"{len(hyde_text)} chars" if hyde_text else "disabled",
                hyde_lexical_augmented=hyde_augmented_count,
                strip_result=stripped_result_for_log or "none",
                preprocess_result=post_stopwords_result_for_log or "none",
                spellcheck_source=getattr(self, "_last_spellcheck_source", "disabled"),
                spellcheck_corrections=len(getattr(self, "_last_spellcheck_changes", [])),
                spellcheck_changes=", ".join(
                    f"{orig}→{corr}"
                    for orig, corr in getattr(self, "_last_spellcheck_changes", [])
                )[:160] or "none",
            ),
        )

        prefilter_started_at = time.perf_counter()
        prefilter_docs, summary_vector_scores, summary_vector_source = self._prefilter_documents_by_summary(
            question=question,
            question_tokens=retrieval_tokens,
            limit=ai_settings.AI_RAG_PREFILTER_TOP_DOCS,
            category_hint=category_hint,
            hyde_text=hyde_text,
        )
        summary_vector_hits = int(self._summary_vector_prefilter_hits)
        prefilter_ms = (time.perf_counter() - prefilter_started_at) * 1000
        prefilter_doc_ids = [doc_id for doc_id, _, _, _ in prefilter_docs]
        base_prefilter_doc_ids = list(prefilter_doc_ids)
        summary_scores = {doc_id: score for doc_id, _, _, score in prefilter_docs}
        normalized_summary_scores = self._build_relative_summary_scores(summary_scores)
        fallback_doc_ids: List[int] = []
        fallback_docs_limit = max(0, int(ai_settings.AI_RAG_SUMMARY_PREFILTER_FALLBACK_DOCS))

        if prefilter_doc_ids and fallback_docs_limit > 0:
            fallback_doc_ids = self._get_fallback_active_document_ids(
                exclude_document_ids=list(prefilter_doc_ids),
                limit=fallback_docs_limit,
            )
            prefilter_doc_ids.extend(fallback_doc_ids)

        prefilter_scope_doc_ids = list(dict.fromkeys(prefilter_doc_ids))

        lexical_started_at = time.perf_counter()
        lexical_chunks, all_lexical_scores = self._search_relevant_chunks(
            question,
            limit=limit,
            prefiltered_doc_ids=prefilter_scope_doc_ids or None,
            summary_scores=summary_scores,
            normalized_summary_scores=normalized_summary_scores,
            override_tokens=retrieval_tokens,
        )
        lexical_ms = (time.perf_counter() - lexical_started_at) * 1000

        vector_started_at = time.perf_counter()
        vector_chunks = self._search_relevant_chunks_vector(
            question=question,
            prefiltered_doc_ids=prefilter_scope_doc_ids or None,
            hyde_text=hyde_text,
        )
        vector_ms = (time.perf_counter() - vector_started_at) * 1000

        merge_started_at = time.perf_counter()
        chunks = self._merge_retrieval_candidates(
            lexical_chunks=lexical_chunks,
            vector_chunks=vector_chunks,
            limit=limit,
            summary_scores=summary_scores,
            normalized_summary_scores=normalized_summary_scores,
            all_lexical_scores=all_lexical_scores,
        )
        effective_category_hint = self._resolve_effective_category_hint(question=question, category_hint=category_hint)
        chunks = self._apply_signal_adjustments_to_chunks(
            chunks=chunks,
            category_hint=effective_category_hint,
        )
        merge_ms = (time.perf_counter() - merge_started_at) * 1000
        mode = self._determine_retrieval_mode(
            lexical_chunks=lexical_chunks,
            vector_chunks=vector_chunks,
            selected_chunks=chunks,
        )
        selected_component_scores = self._build_selected_component_scores(
            lexical_chunks=lexical_chunks,
            vector_chunks=vector_chunks,
            all_lexical_scores=all_lexical_scores,
        )
        max_lexical_score = max(
            (float(self._unpack_chunk_row(c)[0]) for c in lexical_chunks),
            default=0.0,
        )
        lexical_weight = max(0.0, float(ai_settings.AI_RAG_VECTOR_LEXICAL_WEIGHT))
        vector_weight = max(0.0, float(ai_settings.AI_RAG_VECTOR_SEMANTIC_WEIGHT))
        lexical_scorer = ai_settings.get_rag_lexical_scorer()
        selected_unique_docs = len({int(self._unpack_chunk_row(chunk)[3]) for chunk in chunks})
        selected_top_docs = self._build_selected_top_docs_snapshot(chunks)
        top_source = self._format_log_source(str(self._unpack_chunk_row(chunks[0])[1]) if chunks else "none")
        summary_blocks_started_at = time.perf_counter()
        summary_blocks = self._build_summary_blocks(prefilter_docs)
        summary_blocks_ms = (time.perf_counter() - summary_blocks_started_at) * 1000
        retrieval_total_ms = (time.perf_counter() - retrieval_started_at) * 1000
        logger.info(
            "%s",
            self._build_retrieval_log_table(
                mode=mode,
                lexical_scorer=lexical_scorer,
                tokens_count=len(tokens),
                retrieval_tokens_count=len(retrieval_tokens),
                category_hint=effective_category_hint or "none",
                prefilter_docs_count=len(prefilter_docs),
                prefilter_scope_docs_count=len(prefilter_scope_doc_ids),
                fallback_docs_count=len(fallback_doc_ids),
                lexical_hits_count=len(lexical_chunks),
                vector_hits_count=len(vector_chunks),
                summary_vector_hits=summary_vector_hits,
                summary_vector_source=summary_vector_source,
                selected_count=len(chunks),
                selected_unique_docs=selected_unique_docs,
                selected_top_docs=selected_top_docs,
                top_source=top_source,
                retrieval_total_ms=retrieval_total_ms,
                prefilter_ms=prefilter_ms,
                lexical_ms=lexical_ms,
                vector_ms=vector_ms,
                merge_ms=merge_ms,
                summary_blocks_ms=summary_blocks_ms,
            ),
        )
        logger.info(
            "%s",
            self._build_priority_evidence_log_table(
                prefilter_snapshot=self._build_prefilter_priority_snapshot(prefilter_docs, summary_vector_scores),
                selected_snapshot=self._build_selected_priority_snapshot(
                    chunks,
                    summary_scores,
                    prefilter_scope_doc_ids=prefilter_scope_doc_ids,
                    base_prefilter_doc_ids=base_prefilter_doc_ids,
                    component_scores=selected_component_scores,
                    lexical_weight=lexical_weight,
                    vector_weight=vector_weight,
                    normalized_summary_scores=normalized_summary_scores,
                    max_lexical_score=max_lexical_score,
                ),
            ),
        )
        return chunks, summary_blocks

    @staticmethod
    def _format_log_source(source: str, max_length: int = 96) -> str:
        """Подготовить source к компактному человекочитаемому виду для логов."""
        compact = _SPACES_RE.sub(" ", str(source or "").strip())
        if not compact:
            return "none"

        if len(compact) <= max_length:
            return compact

        head_len = max(12, int(max_length * 0.65))
        tail_len = max(8, max_length - head_len - 1)
        return f"{compact[:head_len]}…{compact[-tail_len:]}"

    @staticmethod
    def _format_summary_excerpt(summary_text: str, max_length: int = 80) -> str:
        """Подготовить краткий excerpt из summary для диагностических логов."""
        compact = _SPACES_RE.sub(" ", str(summary_text or "").strip())
        if not compact:
            return "none"

        safe_length = max(16, int(max_length))
        if len(compact) <= safe_length:
            return compact
        return f"{compact[:safe_length - 1]}…"

    @classmethod
    def _build_retrieval_log_table(
        cls,
        *,
        mode: str,
        lexical_scorer: str,
        tokens_count: int,
        retrieval_tokens_count: int,
        category_hint: str,
        prefilter_docs_count: int,
        prefilter_scope_docs_count: int,
        fallback_docs_count: int,
        lexical_hits_count: int,
        vector_hits_count: int,
        summary_vector_hits: int,
        summary_vector_source: str,
        selected_count: int,
        selected_unique_docs: int,
        selected_top_docs: str,
        top_source: str,
        retrieval_total_ms: float,
        prefilter_ms: float,
        lexical_ms: float,
        vector_ms: float,
        merge_ms: float,
        summary_blocks_ms: float,
    ) -> str:
        """Собрать табличный диагностический лог retrieval для удобного чтения."""
        rows: List[Tuple[str, str]] = [
            ("mode", str(mode)),
            ("lexical_scorer", str(lexical_scorer)),
            ("tokens", str(tokens_count)),
            ("retrieval_tokens", str(retrieval_tokens_count)),
            ("category_hint", str(category_hint or "none")),
            ("prefilter_docs", str(prefilter_docs_count)),
            ("prefilter_scope_docs", str(prefilter_scope_docs_count)),
            ("fallback_docs", str(fallback_docs_count)),
            ("lexical_hits", str(lexical_hits_count)),
            ("vector_hits", str(vector_hits_count)),
            ("summary_vector_hits", str(summary_vector_hits)),
            ("summary_vector_source", str(summary_vector_source)),
            ("selected", str(selected_count)),
            ("selected_unique_docs", str(selected_unique_docs)),
            ("selected_top_docs", str(selected_top_docs)),
            ("top_source", cls._format_log_source(str(top_source), max_length=96)),
            ("timings_ms.total", f"{retrieval_total_ms:.2f}"),
            ("timings_ms.prefilter", f"{prefilter_ms:.2f}"),
            ("timings_ms.lexical", f"{lexical_ms:.2f}"),
            ("timings_ms.vector", f"{vector_ms:.2f}"),
            ("timings_ms.merge", f"{merge_ms:.2f}"),
            ("timings_ms.summary_blocks", f"{summary_blocks_ms:.2f}"),
        ]

        metric_width = max(len("metric"), *(len(metric) for metric, _ in rows))
        value_width = max(len("value"), *(len(value) for _, value in rows))
        separator = f"+-{'-' * metric_width}-+-{'-' * value_width}-+"
        table_lines = [
            "RAG retrieval:",
            separator,
            f"| {'metric'.ljust(metric_width)} | {'value'.ljust(value_width)} |",
            separator,
        ]
        table_lines.extend(
            f"| {metric.ljust(metric_width)} | {value.ljust(value_width)} |"
            for metric, value in rows
        )
        table_lines.append(separator)
        return "\n".join(table_lines)

        table_lines.append(separator)
        return "\n".join(table_lines)

    # =============================================
    # Spell-correction (автоисправление опечаток)
    # =============================================

    def _build_spellcheck_vocabulary(self) -> bool:
        """Построить словарь SymSpell из RAG-корпуса (summary + chunks).

        Словарь строится из токенов всех summary-текстов и чанков,
        плюс все защищённые термины из ``_RAG_FIXED_QUERY_TERMS``
        с высокой искусственной частотой.

        Returns:
            True, если словарь успешно построен.
        """
        if SymSpell is None:
            logger.warning("Spellcheck: symspellpy не установлен, словарь не будет построен")
            return False

        started_at = time.perf_counter()

        try:
            max_edit = max(1, int(ai_settings.AI_RAG_SPELLCHECK_MAX_EDIT_DISTANCE))
            sym = SymSpell(max_dictionary_edit_distance=max_edit, prefix_length=7)

            token_freq: Counter = Counter()

            # --- Собираем токены из summary ---
            try:
                with database.get_db_connection() as conn:
                    with database.get_cursor(conn) as cursor:
                        cursor.execute(
                            "SELECT s.summary_text FROM rag_document_summaries s "
                            "JOIN rag_documents d ON d.id = s.document_id "
                            "WHERE d.status = 'active' LIMIT 5000"
                        )
                        rows = cursor.fetchall() or []
                for row in rows:
                    text = str(row.get("summary_text") or "").strip()
                    if text:
                        raw_tokens = _TOKEN_RE.findall(text.lower())
                        for t in raw_tokens:
                            if len(t) >= 2:
                                token_freq[t] += 1
            except Exception:
                logger.warning("Spellcheck: ошибка загрузки summary для словаря", exc_info=True)

            # --- Собираем токены из чанков ---
            try:
                with database.get_db_connection() as conn:
                    with database.get_cursor(conn) as cursor:
                        cursor.execute(
                            "SELECT c.chunk_text FROM rag_chunks c "
                            "JOIN rag_documents d ON d.id = c.document_id "
                            "WHERE d.status = 'active' LIMIT 20000"
                        )
                        rows = cursor.fetchall() or []
                for row in rows:
                    text = str(row.get("chunk_text") or "").strip()
                    if text:
                        raw_tokens = _TOKEN_RE.findall(text.lower())
                        for t in raw_tokens:
                            if len(t) >= 2:
                                token_freq[t] += 1
            except Exception:
                logger.warning("Spellcheck: ошибка загрузки чанков для словаря", exc_info=True)

            # --- Добавляем защищённые термины с высокой частотой ---
            protected_freq = max(1000, max(token_freq.values()) * 10) if token_freq else 1000
            for term in _RAG_FIXED_QUERY_TERMS:
                token_freq[term] = max(token_freq.get(term, 0), protected_freq)

            if not token_freq:
                logger.warning("Spellcheck: словарь пуст, vocabulary не построен")
                return False

            # --- Загружаем частоты в SymSpell ---
            for token, freq in token_freq.items():
                sym.create_dictionary_entry(token, freq)

            self._spellcheck_sym = sym
            self._spellcheck_vocab_size = len(token_freq)
            self._spellcheck_vocab_ready = True

            duration_ms = int((time.perf_counter() - started_at) * 1000)
            logger.info(
                "Spellcheck vocabulary built: vocab_size=%d protected_terms=%d duration_ms=%d",
                self._spellcheck_vocab_size,
                len(_RAG_FIXED_QUERY_TERMS),
                duration_ms,
            )
            return True

        except Exception:
            logger.exception("Spellcheck: не удалось построить словарь")
            return False

    def _spellcheck_tokens(
        self,
        tokens: List[str],
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Исправить опечатки в списке токенов через corpus-based словарь.

        Защищённые термины (``_RAG_FIXED_QUERY_TERMS``), короткие токены,
        латинские и числовые токены пропускаются без изменений.

        Args:
            tokens: Список токенов для проверки.

        Returns:
            Кортеж (исправленные токены, список изменений [(original, corrected)]).
        """
        if not self._spellcheck_vocab_ready or self._spellcheck_sym is None:
            return tokens, []

        if _SymSpellVerbosity is None:
            return tokens, []

        min_length = max(2, int(ai_settings.AI_RAG_SPELLCHECK_MIN_TOKEN_LENGTH))
        max_edit = max(1, int(ai_settings.AI_RAG_SPELLCHECK_MAX_EDIT_DISTANCE))

        corrected_tokens: List[str] = []
        changes: List[Tuple[str, str]] = []

        for token in tokens:
            # Пропускаем защищённые термины
            if token in _RAG_FIXED_QUERY_TERMS:
                corrected_tokens.append(token)
                continue

            # Пропускаем короткие токены
            if len(token) < min_length:
                corrected_tokens.append(token)
                continue

            # Пропускаем нe-кириллические токены (латиница, числа)
            if not _CYRILLIC_TOKEN_RE.search(token):
                corrected_tokens.append(token)
                continue

            # Ищем коррекцию через SymSpell
            try:
                suggestions = self._spellcheck_sym.lookup(
                    token,
                    _SymSpellVerbosity.CLOSEST,
                    max_edit_distance=max_edit,
                )
            except Exception:
                corrected_tokens.append(token)
                continue

            if suggestions and suggestions[0].distance > 0:
                candidate = suggestions[0].term
                # Проверяем, что кандидат не искажает защищённый термин
                if candidate not in _RAG_FIXED_QUERY_TERMS or token in _RAG_FIXED_QUERY_TERMS:
                    corrected_tokens.append(candidate)
                    changes.append((token, candidate))
                else:
                    corrected_tokens.append(token)
            else:
                corrected_tokens.append(token)

        return corrected_tokens, changes

    def _get_suspicious_uncorrected_count(
        self,
        tokens: List[str],
        changes: List[Tuple[str, str]],
    ) -> Tuple[int, int]:
        """Подсчитать «подозрительные» токены которые не были исправлены.

        Подозрительный токен — кириллический, длина ≥ min_length,
        не в словаре и не в защищённых терминах.

        Returns:
            (suspicious_uncorrected_count, total_suspicious_count)
        """
        if not self._spellcheck_vocab_ready or self._spellcheck_sym is None:
            return 0, 0

        min_length = max(2, int(ai_settings.AI_RAG_SPELLCHECK_MIN_TOKEN_LENGTH))
        corrected_originals = {orig for orig, _ in changes}

        suspicious_total = 0
        suspicious_uncorrected = 0

        for token in tokens:
            if token in _RAG_FIXED_QUERY_TERMS:
                continue
            if len(token) < min_length:
                continue
            if not _CYRILLIC_TOKEN_RE.search(token):
                continue

            # Проверяем, есть ли токен в словаре
            try:
                suggestions = self._spellcheck_sym.lookup(
                    token,
                    _SymSpellVerbosity.CLOSEST,
                    max_edit_distance=0,
                )
                in_vocab = bool(suggestions)
            except Exception:
                in_vocab = False

            if not in_vocab:
                suspicious_total += 1
                if token not in corrected_originals:
                    suspicious_uncorrected += 1

        return suspicious_uncorrected, suspicious_total

    async def _spellcheck_llm_fallback(
        self,
        question: str,
        user_id: int,
    ) -> Tuple[str, List[Tuple[str, str]]]:
        """Исправить опечатки через LLM (dedicated call).

        Вызывается, когда corpus-based коррекция не справилась.
        Результаты кэшируются с TTL.

        Args:
            question: Исходный вопрос пользователя.
            user_id: Telegram ID пользователя.

        Returns:
            (исправленный текст, список изменений [(from, to)]).
        """
        cache_key = question.strip().lower()

        # --- Проверка кэша ---
        now = time.time()
        cached = self._spellcheck_llm_cache.get(cache_key)
        if cached is not None:
            cached_text, cached_changes, expires_at = cached
            if expires_at > now:
                logger.info(
                    "Spellcheck LLM cache hit: question='%.60s' changes=%d",
                    question,
                    len(cached_changes),
                )
                return cached_text, cached_changes

        # --- LLM вызов ---
        try:
            from src.core.ai.llm_provider import get_provider as _get_spell_provider

            provider = _get_spell_provider()
            max_chars = max(50, int(ai_settings.AI_RAG_SPELLCHECK_LLM_MAX_CHARS))
            truncated_question = question.strip()[:max_chars]
            protected_terms_list = sorted(_RAG_FIXED_QUERY_TERMS)

            prompt = build_spellcheck_prompt(truncated_question, protected_terms_list)
            raw_response = await provider.chat(
                messages=[{"role": "user", "content": truncated_question}],
                system_prompt=prompt,
                user_id=user_id,
                purpose="spell_correction",
                response_format={"type": "json_object"},
            )

            if not raw_response or not raw_response.strip():
                return question, []

            # --- Парсинг JSON-ответа ---
            response_text = raw_response.strip()
            # Удаляем code fence если есть
            fence_match = _JSON_CODE_FENCE_RE.match(response_text)
            if fence_match:
                response_text = fence_match.group(1).strip()

            parsed = json.loads(response_text)
            corrected = str(parsed.get("corrected") or question).strip()
            raw_changes = parsed.get("changes") or []

            changes: List[Tuple[str, str]] = []
            for change in raw_changes:
                if isinstance(change, dict):
                    from_val = str(change.get("from") or "").strip()
                    to_val = str(change.get("to") or "").strip()
                    if from_val and to_val and from_val != to_val:
                        changes.append((from_val, to_val))

            # --- Safety guard: проверяем, что LLM не изменил защищённые термины ---
            corrected_lower = corrected.lower()
            for term in _RAG_FIXED_QUERY_TERMS:
                if term in question.lower() and term not in corrected_lower:
                    logger.warning(
                        "Spellcheck LLM removed protected term '%s', reverting to original",
                        term,
                    )
                    return question, []

            # --- Кэширование ---
            ttl = max(30, int(ai_settings.AI_RAG_SPELLCHECK_LLM_CACHE_TTL_SECONDS))
            self._spellcheck_llm_cache[cache_key] = (corrected, changes, now + ttl)

            # Очистка просроченных записей (до 10 за вызов)
            expired_keys = [
                k for k, (_, _, exp) in list(self._spellcheck_llm_cache.items())[:50]
                if exp <= now
            ]
            for k in expired_keys[:10]:
                self._spellcheck_llm_cache.pop(k, None)

            logger.info(
                "Spellcheck LLM corrected: question='%.60s' corrected='%.60s' changes=%d",
                question,
                corrected,
                len(changes),
            )
            return corrected, changes

        except Exception as exc:
            logger.warning(
                "Spellcheck LLM fallback failed, returning original: "
                "question='%.60s' error_type=%s error=%r",
                question,
                type(exc).__name__,
                exc,
            )
            return question, []

    def _apply_spellcheck_to_question(
        self,
        question: str,
    ) -> Tuple[str, List[Tuple[str, str]], str]:
        """Применить corpus-based коррекцию к полной строке вопроса.

        Токенизирует вопрос, применяет ``_spellcheck_tokens``,
        реконструирует строку путём замены оригинальных подстрок.

        Args:
            question: Исходный вопрос.

        Returns:
            (corrected_question, changes, source) где source — ``corpus``
            или ``none``.
        """
        if not ai_settings.is_rag_spellcheck_enabled():
            return question, [], "disabled"

        if not self._spellcheck_vocab_ready:
            return question, [], "vocab_not_ready"

        original_tokens = _TOKEN_RE.findall((question or "").lower())
        if not original_tokens:
            return question, [], "none"

        _, changes = self._spellcheck_tokens(original_tokens)
        if not changes:
            return question, [], "none"

        # Реконструкция: заменяем подстроки в исходном вопросе
        corrected = question
        for orig, repl in changes:
            # Case-insensitive замена первого вхождения
            pattern = re.compile(re.escape(orig), re.IGNORECASE)
            corrected = pattern.sub(repl, corrected, count=1)

        return corrected, changes, "corpus"

    @classmethod
    def _build_query_preprocessing_log_table(
        cls,
        *,
        original_tokens_count: int,
        retrieval_tokens_count: int,
        stopwords_removed: int,
        pattern_stripped: bool,
        hyde_status: str,
        hyde_lexical_augmented: int,
        strip_result: str,
        preprocess_result: str,
        spellcheck_source: str = "disabled",
        spellcheck_corrections: int = 0,
        spellcheck_changes: str = "",
    ) -> str:
        """Собрать табличный диагностический лог этапа query preprocessing."""
        rows: List[Tuple[str, str]] = [
            ("original_tokens", str(original_tokens_count)),
            ("retrieval_tokens", str(retrieval_tokens_count)),
            ("stopwords_removed", str(stopwords_removed)),
            ("pattern_stripped", str(pattern_stripped)),
            ("spellcheck_source", str(spellcheck_source)),
            ("spellcheck_corrections", str(spellcheck_corrections)),
            ("spellcheck_changes", str(spellcheck_changes or "none")),
            ("hyde", str(hyde_status)),
            ("hyde_lexical_augmented", str(hyde_lexical_augmented)),
            ("strip_result", str(strip_result or "none")),
            ("preprocess_result", str(preprocess_result or "none")),
        ]

        metric_width = max(len("metric"), *(len(metric) for metric, _ in rows))
        value_width = max(len("value"), *(len(value) for _, value in rows))
        separator = f"+-{'-' * metric_width}-+-{'-' * value_width}-+"
        table_lines = [
            "RAG query preprocessing:",
            separator,
            f"| {'metric'.ljust(metric_width)} | {'value'.ljust(value_width)} |",
            separator,
        ]
        table_lines.extend(
            f"| {metric.ljust(metric_width)} | {value.ljust(value_width)} |"
            for metric, value in rows
        )
        table_lines.append(separator)
        return "\n".join(table_lines)

    @staticmethod
    def _build_priority_evidence_log_table(*, prefilter_snapshot: str, selected_snapshot: str) -> str:
        """Собрать единый многострочный лог `RAG priority evidence` из двух табличных секций."""
        return (
            "RAG priority evidence:\n"
            "prefilter_top:\n"
            f"{prefilter_snapshot}\n"
            "selected_top:\n"
            f"{selected_snapshot}"
        )

    @classmethod
    def _build_prefilter_priority_snapshot(
        cls,
        prefilter_docs: List[Tuple[int, str, str, float]],
        vector_scores: Optional[Dict[int, float]] = None,
        vector_weight: Optional[float] = None,
    ) -> str:
        """Сформировать табличный лог prefilter-документов с разложением итогового score."""
        if not prefilter_docs:
            return "(none)"

        vector_scores = vector_scores or {}
        effective_weight = max(
            0.0,
            float(
                ai_settings.AI_RAG_SUMMARY_VECTOR_WEIGHT if vector_weight is None else vector_weight
            ),
        )
        top_docs = prefilter_docs[:15]  # показать максимум 15 документов, чтобы не перегружать лог
        rows: List[Tuple[str, str, str, str, str, str, str, str]] = []
        for rank, (doc_id, filename, summary_text, score) in enumerate(top_docs, start=1):
            vec = float(vector_scores.get(doc_id, 0.0))
            weighted_vec = vec * effective_weight
            lexical_part = score - weighted_vec
            rows.append(
                (
                    str(rank),
                    str(doc_id),
                    f"{score:.3f}",
                    f"{lexical_part:.3f}",
                    f"{vec:.3f}",
                    f"{weighted_vec:.3f}",
                    cls._format_summary_excerpt(summary_text),
                    cls._format_log_source(filename),
                )
            )

        headers = ("rank", "doc", "summary", "lexical", "vec", "vec_w", "excerpt", "source")
        widths = [len(header) for header in headers]
        for row in rows:
            for index, value in enumerate(row):
                widths[index] = max(widths[index], len(value))

        separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
        table_lines = [separator]
        table_lines.append(
            "| " + " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)) + " |"
        )
        table_lines.append(separator)
        table_lines.extend(
            "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
            for row in rows
        )
        table_lines.append(separator)
        return "\n".join(table_lines)

    @classmethod
    def _build_selected_priority_snapshot(
        cls,
        chunks: List[Tuple[float, str, str, int]],
        summary_scores: Dict[int, float],
        prefilter_scope_doc_ids: Optional[List[int]] = None,
        base_prefilter_doc_ids: Optional[List[int]] = None,
        component_scores: Optional[Dict[Tuple[int, str], Tuple[float, float]]] = None,
        lexical_weight: Optional[float] = None,
        vector_weight: Optional[float] = None,
        normalized_summary_scores: Optional[Dict[int, float]] = None,
        max_lexical_score: Optional[float] = None,
    ) -> str:
        """Сформировать табличный лог финально выбранных чанков и вкладов summary-score."""
        if not chunks:
            return "(none)"

        prefilter_scope_set = {int(doc_id) for doc_id in (prefilter_scope_doc_ids or [])}
        base_prefilter_set = {int(doc_id) for doc_id in (base_prefilter_doc_ids or [])}
        component_scores = component_scores or {}
        effective_lexical_weight = max(
            0.0,
            float(ai_settings.AI_RAG_VECTOR_LEXICAL_WEIGHT if lexical_weight is None else lexical_weight),
        )
        effective_vector_weight = max(
            0.0,
            float(ai_settings.AI_RAG_VECTOR_SEMANTIC_WEIGHT if vector_weight is None else vector_weight),
        )
        effective_normalized_scores = (
            normalized_summary_scores
            if normalized_summary_scores is not None
            else cls._build_relative_summary_scores(summary_scores)
        )
        # -- вычисление max lexical для нормализации в диапазон 0..1 --
        if max_lexical_score is not None:
            effective_max_lexical = float(max_lexical_score)
        else:
            effective_max_lexical = 0.0
            for _lex, _vec in component_scores.values():
                if float(_lex) > effective_max_lexical:
                    effective_max_lexical = float(_lex)
        top_chunks = chunks[:10]  # показать максимум 10 чанков, чтобы не перегружать лог
        rows: List[Tuple[str, str, str, str, str, str, str, str, str, str, str, str, str]] = []
        for rank, chunk in enumerate(top_chunks, start=1):
            fused_score, source, chunk_text, document_id, chunk_index = cls._unpack_chunk_row(chunk)
            summary_score = float(summary_scores.get(document_id, 0.0))
            normalized_summary_score = float(effective_normalized_scores.get(document_id, 0.0))
            chunk_key = (int(document_id), str(chunk_text or "").strip())
            lexical_score, vector_score = component_scores.get(chunk_key, (0.0, 0.0))
            lexical_total = float(lexical_score)
            lexical_norm = (lexical_total / effective_max_lexical) if effective_max_lexical > 0 else 0.0
            lexical_bonus_full = cls._summary_score_bonus_from_normalized(normalized_summary_score)
            lexical_bonus = max(0.0, min(lexical_bonus_full, lexical_total))
            lexical_raw = max(0.0, lexical_total - lexical_bonus)
            hybrid_base = (lexical_norm * effective_lexical_weight) + (float(vector_score) * effective_vector_weight)
            summary_bonus = cls._summary_postrank_bonus_from_normalized(normalized_summary_score)
            if document_id in base_prefilter_set:
                origin = "prefilter"
            elif document_id in prefilter_scope_set:
                origin = "fallback"
            else:
                origin = "global"
            rows.append(
                (
                    str(rank),
                    str(document_id),
                    str(chunk_index),
                    f"{float(fused_score):.3f}",
                    f"{summary_score:.3f}",
                    origin,
                    f"{lexical_raw:.3f}",
                    f"{lexical_bonus:.3f}",
                    f"{lexical_total:.3f}",
                    f"{lexical_norm:.3f}",
                    f"({lexical_norm:.3f}*{effective_lexical_weight:.3f})+({float(vector_score):.3f}*{effective_vector_weight:.3f})={hybrid_base:.3f}",
                    f"{summary_bonus:.3f}",
                    cls._format_log_source(source),
                )
            )

        headers = (
            "rank",
            "doc",
            "chunk",
            "fused",
            "summary",
            "origin",
            "lex_raw",
            "lex_bonus",
            "lex_total",
            "lex_norm",
            "hybrid",
            "summary_bonus",
            "source",
        )
        widths = [len(header) for header in headers]
        for row in rows:
            for index, value in enumerate(row):
                widths[index] = max(widths[index], len(value))

        separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
        table_lines = [separator]
        table_lines.append(
            "| " + " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)) + " |"
        )
        table_lines.append(separator)
        table_lines.extend(
            "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
            for row in rows
        )
        table_lines.append(separator)
        return "\n".join(table_lines)

    @staticmethod
    def _build_selected_component_scores(
        lexical_chunks: List[Tuple[float, str, str, int]],
        vector_chunks: List[Tuple[float, str, str, int]],
        all_lexical_scores: Optional[Dict[Tuple[int, str], float]] = None,
    ) -> Dict[Tuple[int, str], Tuple[float, float]]:
        """Собрать lexical/vector score-компоненты для выбранных чанков по dedup-ключу merge.

        all_lexical_scores — словарь всех lexical-score, позволяющий подставить фактический
        lexical-score для vector-only чанков, а не дефолтный 0.
        """
        components: Dict[Tuple[int, str], Tuple[float, float]] = {}
        all_lexical_scores = all_lexical_scores or {}

        for chunk in lexical_chunks:
            lexical_score, _source, chunk_text, document_id, _chunk_index = RagKnowledgeService._unpack_chunk_row(chunk)
            key = (int(document_id), str(chunk_text or "").strip())
            current_lexical, current_vector = components.get(key, (0.0, 0.0))
            components[key] = (max(current_lexical, float(lexical_score)), current_vector)

        for chunk in vector_chunks:
            vector_score, _source, chunk_text, document_id, _chunk_index = RagKnowledgeService._unpack_chunk_row(chunk)
            key = (int(document_id), str(chunk_text or "").strip())
            current_lexical, current_vector = components.get(key, (0.0, 0.0))
            # для vector-only чанков подставляем фактический lexical-score из all_lexical_scores
            if current_lexical <= 0:
                actual_lexical = float(all_lexical_scores.get(key, 0.0))
                current_lexical = max(current_lexical, actual_lexical)
            components[key] = (current_lexical, max(current_vector, float(vector_score)))

        return components

    @staticmethod
    def _build_selected_top_docs_snapshot(
        chunks: List[Tuple[float, str, str, int]],
        max_docs: int = 5,
    ) -> str:
        """Сформировать compact snapshot top уникальных document_id по порядку ранжирования."""
        if not chunks:
            return "none"

        safe_limit = max(1, int(max_docs))
        ordered_unique_doc_ids: List[int] = []
        seen_doc_ids: set[int] = set()
        for chunk in chunks:
            _score, _source, _chunk_text, document_id, _chunk_index = RagKnowledgeService._unpack_chunk_row(chunk)
            doc_id = int(document_id)
            if doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)
            ordered_unique_doc_ids.append(doc_id)
            if len(ordered_unique_doc_ids) >= safe_limit:
                break

        if not ordered_unique_doc_ids:
            return "none"
        return ",".join(str(doc_id) for doc_id in ordered_unique_doc_ids)

    def _search_relevant_chunks_vector(
        self,
        question: str,
        prefiltered_doc_ids: Optional[List[int]],
        hyde_text: Optional[str] = None,
    ) -> List[Tuple[float, str, str, int, int]]:
        """Найти релевантные чанки через локальный векторный индекс."""
        if not self._is_vector_search_enabled():
            return []

        embedding_provider = self._get_embedding_provider()
        vector_index = self._get_vector_index()
        if embedding_provider is None or vector_index is None:
            return []

        embed_text = hyde_text if hyde_text else question
        query_vectors = embedding_provider.encode_texts([embed_text])
        if not query_vectors:
            return []

        candidates = vector_index.search(
            query_vector=query_vectors[0],
            limit=max(1, int(ai_settings.AI_RAG_VECTOR_TOP_K)),
            allowed_document_ids=prefiltered_doc_ids,
        )
        return [(item.score, item.source, item.chunk_text, item.document_id, item.chunk_index) for item in candidates]

    def _merge_retrieval_candidates(
        self,
        lexical_chunks: List[Tuple[float, str, str, int]],
        vector_chunks: List[Tuple[float, str, str, int]],
        limit: int,
        summary_scores: Optional[Dict[int, float]] = None,
        normalized_summary_scores: Optional[Dict[int, float]] = None,
        all_lexical_scores: Optional[Dict[Tuple[int, str], float]] = None,
    ) -> List[Tuple[float, str, str, int, int]]:
        """Объединить lexical и vector кандидаты в единый ранжированный список.

        all_lexical_scores — словарь (doc_id, chunk_text.strip()) → lexical score для ВСЕХ
        оценённых чанков (не только top-K), чтобы vector-only чанки получали фактический
        lexical-score вместо дефолтного 0.
        """
        safe_limit = max(1, limit)
        summary_scores = summary_scores or {}
        normalized_summary_scores = normalized_summary_scores or {}
        all_lexical_scores = all_lexical_scores or {}

        if not vector_chunks:
            return lexical_chunks[:safe_limit]

        if not ai_settings.AI_RAG_HYBRID_ENABLED:
            return vector_chunks[:safe_limit]

        lexical_weight = max(0.0, float(ai_settings.AI_RAG_VECTOR_LEXICAL_WEIGHT))
        vector_weight = max(0.0, float(ai_settings.AI_RAG_VECTOR_SEMANTIC_WEIGHT))

        merged: Dict[Tuple[int, int, str], Dict[str, object]] = {}

        for chunk in lexical_chunks:
            score, source, chunk_text, document_id, chunk_index = self._unpack_chunk_row(chunk)
            key = self._chunk_merge_key(document_id=document_id, chunk_text=chunk_text, chunk_index=chunk_index)
            merged[key] = {
                "lexical_score": float(score),
                "vector_score": 0.0,
                "source": source,
                "chunk_text": chunk_text,
                "document_id": document_id,
                "chunk_index": int(chunk_index),
            }

        for chunk in vector_chunks:
            score, source, chunk_text, document_id, chunk_index = self._unpack_chunk_row(chunk)
            key = self._chunk_merge_key(document_id=document_id, chunk_text=chunk_text, chunk_index=chunk_index)
            row = merged.get(key)
            if row is None:
                # vector-only чанк: подставляем фактический lexical-score из all_lexical_scores
                lookup_key = (int(document_id), str(chunk_text or "").strip())
                actual_lexical = float(all_lexical_scores.get(lookup_key, 0.0))
                row = {
                    "lexical_score": actual_lexical,
                    "vector_score": 0.0,
                    "source": source,
                    "chunk_text": chunk_text,
                    "document_id": document_id,
                    "chunk_index": int(chunk_index),
                }
                merged[key] = row
            row["vector_score"] = max(float(row.get("vector_score") or 0.0), float(score))

        # -- нормализация lexical-score в диапазон 0..1 (min-max) --
        max_lexical = 0.0
        for row in merged.values():
            lex = float(row.get("lexical_score") or 0.0)
            if lex > max_lexical:
                max_lexical = lex

        ranked: List[Tuple[float, str, str, int, int]] = []
        for row in merged.values():
            lexical_score = float(row.get("lexical_score") or 0.0)
            normalized_lexical = (lexical_score / max_lexical) if max_lexical > 0 else 0.0
            vector_score = float(row.get("vector_score") or 0.0)
            document_id = int(row.get("document_id") or 0)
            chunk_index = int(row.get("chunk_index") or 0)
            summary_score = float(summary_scores.get(document_id, 0.0))
            normalized_summary_score = normalized_summary_scores.get(document_id)
            fused_score = (normalized_lexical * lexical_weight) + (vector_score * vector_weight)
            if normalized_summary_score is None:
                fused_score += self._summary_postrank_bonus(summary_score)
            else:
                fused_score += self._summary_postrank_bonus_from_normalized(float(normalized_summary_score))
            if fused_score <= 0:
                continue
            ranked.append(
                (
                    fused_score,
                    str(row.get("source") or "document"),
                    str(row.get("chunk_text") or ""),
                    int(row.get("document_id") or 0),
                    chunk_index,
                )
            )

        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[:safe_limit]

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

    def _split_html_payload(self, payload: bytes, filename: str = "document.html") -> List[str]:
        """Разбить HTML-документ на чанки с приоритетом по заголовкам."""
        if not ai_settings.is_rag_html_splitter_enabled():
            logger.info("HTML splitter отключен через bot_settings, используется fallback")
            chunks = self._split_text(self._extract_html_text(payload))
            self._log_chunking_strategy(
                file_name=filename,
                file_format="html",
                strategy="plain_text_fallback(html_splitter_disabled)",
                chunks_count=len(chunks),
            )
            return chunks

        raw_html = self._decode_text_payload(payload)
        semantic_chunks = self._split_html_with_semantic_preserving_splitter(raw_html)
        if semantic_chunks:
            self._log_chunking_strategy(
                file_name=filename,
                file_format="html",
                strategy="html_semantic_preserving_splitter",
                chunks_count=len(semantic_chunks),
            )
            return semantic_chunks

        logger.info("HTMLSemanticPreservingSplitter/HTMLHeaderTextSplitter недоступны или не дали чанков, включен fallback")
        chunks = self._split_text(self._extract_html_text(payload))
        self._log_chunking_strategy(
            file_name=filename,
            file_format="html",
            strategy="plain_text_fallback(html_splitter_empty_or_unavailable)",
            chunks_count=len(chunks),
        )
        return chunks

    def _split_html_with_semantic_preserving_splitter(self, raw_html: str) -> List[str]:
        """Попытаться разбить HTML через semantic-preserving splitter с переносом заголовков в текст."""
        normalized_html = (raw_html or "").strip()
        if not normalized_html:
            return []

        try:
            splitter_cls = self._get_html_splitter_class()
            splitter = self._build_html_splitter(splitter_cls)
            documents = splitter.split_text(normalized_html)
        except Exception as exc:
            logger.warning("Не удалось применить HTML splitter: %s", exc)
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
    def _build_html_splitter(splitter_cls):
        """Построить HTML splitter с совместимыми параметрами конструктора."""
        headers_to_split_on = [
            ("h1", "h1"),
            ("h2", "h2"),
            ("h3", "h3"),
            ("h4", "h4"),
            ("h5", "h5"),
            ("h6", "h6"),
        ]
        try:
            return splitter_cls(
                headers_to_split_on=headers_to_split_on,
                max_chunk_size=ai_settings.AI_RAG_CHUNK_SIZE,
                chunk_overlap=ai_settings.AI_RAG_CHUNK_OVERLAP,
            )
        except TypeError:
            return splitter_cls(headers_to_split_on=headers_to_split_on)

    @staticmethod
    def _get_html_splitter_class():
        """Получить приоритетный HTML splitter: semantic-preserving, затем header splitter."""
        if not RagKnowledgeService._is_langchain_splitter_supported():
            raise RuntimeError("LangChain splitter отключен для текущей версии Python")

        import warnings

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from langchain_text_splitters import HTMLSemanticPreservingSplitter

            return HTMLSemanticPreservingSplitter
        except Exception:
            pass

        return RagKnowledgeService._get_html_header_splitter_class()

    @staticmethod
    def _get_html_header_splitter_class():
        """Получить fallback-класс HTMLHeaderTextSplitter из доступного пространства имён."""
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
                from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: F401
            return True
        except Exception:
            pass
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from langchain.text_splitter import RecursiveCharacterTextSplitter  # noqa: F401
            return True
        except Exception:
            pass
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from langchain_text_splitters import HTMLSemanticPreservingSplitter  # noqa: F401
            return True
        except Exception:
            pass
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

    # =============================================
    # Защита аббревиатур при splitting
    # =============================================
    # Регулярное выражение для распространённых русскоязычных аббревиатур
    # вида «т.д.», «т.п.», «г.», «т.е.», «тыс.», «руб.» и подобных.
    # При splitting точки внутри аббревиатур заменяются на плейсхолдер,
    # чтобы сплиттер не разрезал текст посередине выражения.
    _RU_ABBREVIATION_RE = re.compile(
        r"\b(?:"
        r"т\.\s*д|т\.\s*п|т\.\s*е|т\.\s*к|т\.\s*н|т\.\s*о"
        r"|д\.\s*р|н\.\s*э|н\.\s*э\.\s*л"
        r"|пр\.\s*(?=[а-яА-ЯёЁ])|др\.\s*(?=[а-яА-ЯёЁ])"
        r"|им\.\s*(?=[а-яА-ЯёЁ])|ул\.\s*(?=[а-яА-ЯёЁ])"
        r"|обл|тыс|руб|коп|млн|млрд|кв|стр|корп|каб"
        r"|гг?|вв?|чч?|мм?|сс?|кг|км|мин|сек|час"
        r"|ООО|ОАО|ЗАО|ПАО|АО|ИП|ИНН|СНИЛС|ОГРН"
        r"|НДС|ФНС|ФСС|ПФР|СФР|ЕНП|ЕНС"
        r"|ККТ|ОФД|ФН|ФД|ФП|СНО|БСО|ЗН|РН"
        r"|стр\.\s*(?=[0-9])|корп\.\s*(?=[0-9])"
        r")\.",
        re.IGNORECASE,
    )
    _ABBREVIATION_PLACEHOLDER = "\u2060"  # Zero-width non-breaking space

    # Русскоязычные сепараторы для RecursiveCharacterTextSplitter.
    # Порядок: от крупных структурных единиц к мелким.
    _RU_SEPARATORS: List[str] = [
        "\n\n",      # Граница абзацев
        "\n",        # Перевод строки
        ". ",        # Конец предложения (после защиты аббревиатур)
        "! ",        # Восклицание
        "? ",        # Вопрос
        "; ",        # Точка с запятой
        ", ",        # Запятая
        "— ",        # Начало прямой речи / тире
        " ",         # Граница слов
        "",          # Крайний случай — посимвольно
    ]

    @classmethod
    def _protect_abbreviations(cls, text: str) -> str:
        """Заменить точки внутри русскоязычных аббревиатур на плейсхолдер.

        Предотвращает разрезание текста посередине выражений типа
        «т.д.», «т.п.», «г.», «тыс.» и аналогичных сокращений.
        """
        def _replace_dots(match: re.Match) -> str:
            return match.group(0).replace(".", cls._ABBREVIATION_PLACEHOLDER)
        return cls._RU_ABBREVIATION_RE.sub(_replace_dots, text)

    @classmethod
    def _restore_abbreviations(cls, text: str) -> str:
        """Восстановить точки в аббревиатурах после splitting."""
        return text.replace(cls._ABBREVIATION_PLACEHOLDER, ".")

    @staticmethod
    def _split_text(text: str) -> List[str]:
        """Разбить текст на чанки; при наличии langchain использует его splitter.

        Для русскоязычных текстов используется расширенный набор сепараторов
        и защита аббревиатур от разрезания.
        """
        cleaned = (text or "").strip()
        if not cleaned:
            return []

        # Защита аббревиатур перед splitting
        protected = RagKnowledgeService._protect_abbreviations(cleaned)

        if RagKnowledgeService._is_langchain_splitter_supported():
            try:
                try:
                    from langchain_text_splitters import RecursiveCharacterTextSplitter
                except Exception:
                    from langchain.text_splitter import RecursiveCharacterTextSplitter

                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=ai_settings.AI_RAG_CHUNK_SIZE,
                    chunk_overlap=ai_settings.AI_RAG_CHUNK_OVERLAP,
                    separators=RagKnowledgeService._RU_SEPARATORS,
                )
                chunks = splitter.split_text(protected)
                return [
                    RagKnowledgeService._restore_abbreviations(chunk.strip())
                    for chunk in chunks
                    if chunk and chunk.strip()
                ]
            except Exception:
                pass

        # Manual window slicer с учётом границ предложений
        chunk_size = ai_settings.AI_RAG_CHUNK_SIZE
        overlap = ai_settings.AI_RAG_CHUNK_OVERLAP
        chunks: List[str] = []
        start = 0
        text_len = len(protected)
        # Регулярное выражение для поиска границ предложений
        _sentence_boundary_re = re.compile(r"[.!?]\s+", re.MULTILINE)

        while start < text_len:
            end = min(start + chunk_size, text_len)
            # Если не конец текста, пытаемся найти ближайшую границу предложения
            if end < text_len:
                window = protected[start:end]
                # Ищем последнюю границу предложения в окне
                last_boundary = None
                for match in _sentence_boundary_re.finditer(window):
                    boundary_pos = match.end()
                    # Граница должна быть не слишком близко к началу (мин. 20% чанка)
                    if boundary_pos >= chunk_size * 0.2:
                        last_boundary = boundary_pos
                if last_boundary is not None:
                    end = start + last_boundary

            chunk = protected[start:end].strip()
            if chunk:
                chunks.append(RagKnowledgeService._restore_abbreviations(chunk))
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
        normalized_summary_scores: Optional[Dict[int, float]] = None,
        override_tokens: Optional[List[str]] = None,
    ) -> Tuple[List[Tuple[float, str, str, int, int]], Dict[Tuple[int, str], float]]:
        """Найти релевантные чанки в БД по гибридному lexical scoring.

        Возвращает кортеж (top_k_chunks, all_lexical_scores), где all_lexical_scores — словарь
        (document_id, chunk_text.strip()) → score для всех оценённых чанков (не только top-K).
        Это позволяет merge-этапу использовать фактический lexical-score для vector-only чанков.
        """
        tokens = override_tokens if override_tokens is not None else self._tokenize(question)
        if not tokens:
            return [], {}

        lexical_scorer = ai_settings.get_rag_lexical_scorer()

        safe_limit = max(1, limit)
        summary_scores = summary_scores or {}
        normalized_summary_scores = normalized_summary_scores or {}

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if prefiltered_doc_ids:
                    placeholders = ",".join(["%s"] * len(prefiltered_doc_ids))
                    cursor.execute(
                        f"""
                        SELECT c.chunk_text, c.chunk_index, d.filename, d.id AS document_id
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
                        SELECT c.chunk_text, c.chunk_index, d.filename, d.id AS document_id
                        FROM rag_chunks c
                        JOIN rag_documents d ON d.id = c.document_id
                        WHERE d.status = 'active'
                        ORDER BY c.id DESC
                        LIMIT %s
                        """,
                        (_RAG_CHUNK_SCAN_LIMIT,),
                    )
                rows = cursor.fetchall() or []

        scored: List[Tuple[float, str, str, int, int]] = []
        all_lexical_scores: Dict[Tuple[int, str], float] = {}

        bm25_scores: List[float] = []
        if lexical_scorer == "bm25":
            chunk_tokens_corpus = [self._tokenize(str(row.get("chunk_text") or "")) for row in rows]
            bm25_scores = self._score_corpus_bm25(chunk_tokens_corpus, tokens)

        for index, row in enumerate(rows):
            chunk_text = row.get("chunk_text") or ""
            chunk_index = int(row.get("chunk_index") or 0)
            source = row.get("filename") or "document"
            document_id = int(row.get("document_id") or 0)
            if lexical_scorer == "bm25":
                chunk_score = float(bm25_scores[index]) if index < len(bm25_scores) else 0.0
            else:
                chunk_score = self._score_chunk(chunk_text, tokens)
            summary_score = summary_scores.get(document_id, 0.0)
            normalized_summary_score = normalized_summary_scores.get(document_id)
            if normalized_summary_score is None:
                summary_bonus = self._summary_score_bonus(summary_score)
            else:
                summary_bonus = self._summary_score_bonus_from_normalized(float(normalized_summary_score))
            score = chunk_score + summary_bonus
            # сохраняем score для всех чанков для использования при merge
            chunk_key = (int(document_id), str(chunk_text or "").strip())
            existing = all_lexical_scores.get(chunk_key, 0.0)
            if score > existing:
                all_lexical_scores[chunk_key] = score
            if score > 0:
                scored.append((score, source, chunk_text, document_id, chunk_index))

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[:safe_limit], all_lexical_scores

    @staticmethod
    def _unpack_chunk_row(chunk: Tuple[object, ...]) -> Tuple[float, str, str, int, int]:
        """Нормализовать запись чанка к формату (score, source, text, document_id, chunk_index)."""
        if len(chunk) >= 5:
            score, source, chunk_text, document_id, chunk_index = chunk[:5] 
            return (
                float(score or 0.0),
                str(source or "document"),
                str(chunk_text or ""),
                int(document_id or 0),
                int(chunk_index or 0),
            )

        if len(chunk) == 4:
            score, source, chunk_text, document_id = chunk
            return (
                float(score or 0.0),
                str(source or "document"),
                str(chunk_text or ""),
                int(document_id or 0),
                0,
            )

        raise ValueError("Некорректный формат чанка для retrieval")

    @staticmethod
    def _chunk_merge_key(document_id: int, chunk_text: str, chunk_index: int) -> Tuple[int, int, str]:
        """Собрать dedup-ключ merge с приоритетом chunk_index при его наличии."""
        safe_doc_id = int(document_id or 0)
        safe_chunk_index = int(chunk_index or 0)
        normalized_text = str(chunk_text or "").strip()
        if safe_chunk_index > 0:
            return safe_doc_id, safe_chunk_index, ""
        return safe_doc_id, 0, normalized_text

    def _prefilter_documents_by_summary(
        self,
        question: str,
        question_tokens: List[str],
        limit: int,
        category_hint: Optional[str] = None,
        hyde_text: Optional[str] = None,
    ) -> Tuple[List[Tuple[int, str, str, float]], Dict[int, float], str]:
        """Отобрать релевантные документы по таблице summary перед поиском чанков.

        Returns:
            (список ранжированных документов, словарь vector-similarity по document_id, источник vector-score)
        """
        if not question_tokens:
            self._summary_vector_prefilter_source = "disabled"
            self._summary_vector_prefilter_hits = 0
            return [], {}, self._summary_vector_prefilter_source

        safe_limit = max(1, min(limit, 100))
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT s.document_id, s.summary_text, d.filename, d.source_type
                    FROM rag_document_summaries s
                    JOIN rag_documents d ON d.id = s.document_id
                    WHERE d.status = 'active'
                    ORDER BY s.updated_at DESC
                    LIMIT %s
                    """,
                    (_RAG_SUMMARY_SCAN_LIMIT,),
                )
                rows = cursor.fetchall() or []

        summaries_for_vector: List[Tuple[int, str]] = []
        valid_rows: List[Tuple[int, str, str, str]] = []
        for row in rows:
            document_id = int(row.get("document_id") or 0)
            filename = str(row.get("filename") or "document")
            summary_text = str(row.get("summary_text") or "").strip()
            source_type = str(row.get("source_type") or "").strip().lower()
            if not document_id or not summary_text:
                continue
            valid_rows.append((document_id, filename, summary_text, source_type))
            summaries_for_vector.append((document_id, summary_text))

        vector_scores = self._search_summary_vector_scores_from_collection(
            question=question,
            document_ids=[doc_id for doc_id, _, _, _ in valid_rows],
            limit=max(safe_limit, len(valid_rows)),
            hyde_text=hyde_text,
        )
        vector_source = "collection"
        if not vector_scores:
            vector_scores = self._compute_summary_vector_scores(
                question=question,
                summaries=summaries_for_vector,
                hyde_text=hyde_text,
            )
            vector_source = "fallback"
        self._summary_vector_prefilter_source = vector_source
        self._summary_vector_prefilter_hits = len(vector_scores)

        vector_weight = max(0.0, float(ai_settings.AI_RAG_SUMMARY_VECTOR_WEIGHT))
        lexical_scorer = ai_settings.get_rag_lexical_scorer()
        summary_bm25_scores: Dict[int, float] = {}
        if lexical_scorer == "bm25":
            summary_corpus_tokens = [self._tokenize(summary_text) for _, _, summary_text, _ in valid_rows]
            # IDF dampening: подавить query-токены, встречающиеся почти во всех summary
            dampened_tokens, dampening_diagnostics = self._dampen_common_query_tokens(
                question_tokens,
                summary_corpus_tokens,
                return_diagnostics=True,
            )
            self._log_idf_dampening_effect(
                stage="summary_prefilter",
                question=question,
                diagnostics=dampening_diagnostics,
            )
            corpus_scores = self._score_corpus_bm25(summary_corpus_tokens, dampened_tokens)
            for index, (document_id, _, _, _) in enumerate(valid_rows):
                summary_bm25_scores[document_id] = float(corpus_scores[index]) if index < len(corpus_scores) else 0.0

        source_types_by_doc_id: Dict[int, str] = {
            document_id: source_type
            for document_id, _, _, source_type in valid_rows
        }

        token_weight = max(0.0, float(ai_settings.AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT))

        scored_docs: List[Tuple[int, str, str, float]] = []
        for document_id, filename, summary_text, _ in valid_rows:
            if lexical_scorer == "bm25":
                lexical_score = summary_bm25_scores.get(document_id, 0.0) * token_weight
                lexical_score += self._score_summary_phrase_match(
                    summary_text=summary_text,
                    question_tokens=question_tokens,
                    question=question,
                )
            else:
                lexical_score = self._score_summary_text(
                    summary_text=summary_text,
                    question_tokens=question_tokens,
                    question=question,
                )
            vec_score = float(vector_scores.get(document_id, 0.0))
            score = lexical_score + (vec_score * vector_weight)
            if score <= 0:
                continue
            scored_docs.append((document_id, filename, summary_text, score))

        effective_category_hint = self._resolve_effective_category_hint(question=question, category_hint=category_hint)
        scored_docs = self._apply_signal_adjustments_to_prefilter_docs(
            docs=scored_docs,
            category_hint=effective_category_hint,
        )
        scored_docs.sort(key=lambda item: item[3], reverse=True)

        if not ai_settings.AI_RAG_PREFILTER_EXCLUDE_CERTIFICATION_FROM_COUNT:
            return scored_docs[:safe_limit], vector_scores, vector_source

        counted_docs: List[Tuple[int, str, str, float]] = []
        non_counted_docs: List[Tuple[int, str, str, float]] = []
        non_counted_limit = safe_limit

        for doc in scored_docs:
            document_id = int(doc[0])
            source_type = source_types_by_doc_id.get(document_id, "")
            if source_type == _RAG_SOURCE_TYPE_CERTIFICATION:
                if len(non_counted_docs) < non_counted_limit:
                    non_counted_docs.append(doc)
                continue

            if len(counted_docs) < safe_limit:
                counted_docs.append(doc)

            if len(counted_docs) >= safe_limit and len(non_counted_docs) >= non_counted_limit:
                break

        merged_docs = counted_docs + non_counted_docs
        merged_docs.sort(key=lambda item: item[3], reverse=True)
        return merged_docs, vector_scores, vector_source

    def _upsert_document_signal(self, document_id: int, signal_data: Dict[str, object]) -> None:
        """Сохранить сигналы документа для дополнительного ранжирования retrieval."""
        safe_document_id = int(document_id or 0)
        if safe_document_id <= 0:
            return

        try:
            with database.get_db_connection() as conn:
                with database.get_cursor(conn) as cursor:
                    cursor.execute(
                        """
                        INSERT INTO rag_document_signals
                            (
                                document_id,
                                domain_key,
                                question_id,
                                category_keys_json,
                                category_labels_json,
                                is_active,
                                is_outdated,
                                relevance_date,
                                updated_at
                            )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON DUPLICATE KEY UPDATE
                            domain_key = VALUES(domain_key),
                            question_id = VALUES(question_id),
                            category_keys_json = VALUES(category_keys_json),
                            category_labels_json = VALUES(category_labels_json),
                            is_active = VALUES(is_active),
                            is_outdated = VALUES(is_outdated),
                            relevance_date = VALUES(relevance_date),
                            updated_at = NOW()
                        """,
                        (
                            safe_document_id,
                            str(signal_data.get("domain_key") or "")[:64],
                            int(signal_data.get("question_id") or 0) or None,
                            str(signal_data.get("category_keys_json") or "[]"),
                            str(signal_data.get("category_labels_json") or "[]"),
                            int(signal_data.get("is_active") or 0),
                            int(signal_data.get("is_outdated") or 0),
                            signal_data.get("relevance_date"),
                        ),
                    )
        except Exception as exc:
            if not self._document_signals_table_warning_logged:
                logger.warning("Таблица rag_document_signals недоступна: %s", exc)
                self._document_signals_table_warning_logged = True

    def _load_document_signals(self, document_ids: List[int]) -> Dict[int, Dict[str, object]]:
        """Загрузить сигналы ранжирования по списку document_id."""
        normalized_ids = [int(doc_id) for doc_id in document_ids if int(doc_id) > 0]
        if not normalized_ids:
            return {}

        placeholders = ",".join(["%s"] * len(normalized_ids))
        query = f"""
            SELECT
                document_id,
                domain_key,
                question_id,
                category_keys_json,
                category_labels_json,
                is_active,
                is_outdated,
                relevance_date
            FROM rag_document_signals
            WHERE document_id IN ({placeholders})
        """

        try:
            with database.get_db_connection() as conn:
                with database.get_cursor(conn) as cursor:
                    cursor.execute(query, tuple(normalized_ids))
                    rows = cursor.fetchall() or []
        except Exception as exc:
            if not self._document_signals_table_warning_logged:
                logger.warning("Не удалось загрузить сигналы rag_document_signals: %s", exc)
                self._document_signals_table_warning_logged = True
            return {}

        signals: Dict[int, Dict[str, object]] = {}
        for row in rows:
            document_id = int(row.get("document_id") or 0)
            if document_id <= 0:
                continue

            category_keys: List[str] = []
            category_labels: List[str] = []
            try:
                raw_keys = row.get("category_keys_json")
                if raw_keys:
                    parsed_keys = json.loads(str(raw_keys))
                    if isinstance(parsed_keys, list):
                        category_keys = [self._normalize_category_key(str(key)) for key in parsed_keys if str(key).strip()]
            except Exception:
                category_keys = []

            try:
                raw_labels = row.get("category_labels_json")
                if raw_labels:
                    parsed_labels = json.loads(str(raw_labels))
                    if isinstance(parsed_labels, list):
                        category_labels = [str(label).strip() for label in parsed_labels if str(label).strip()]
            except Exception:
                category_labels = []

            signals[document_id] = {
                "domain_key": str(row.get("domain_key") or "").strip(),
                "question_id": int(row.get("question_id") or 0),
                "is_active": int(row.get("is_active") or 0) == 1,
                "is_outdated": int(row.get("is_outdated") or 0) == 1,
                "relevance_date": row.get("relevance_date"),
                "category_keys": [key for key in category_keys if key],
                "category_labels": category_labels,
            }

        return signals

    def _resolve_effective_category_hint(self, question: str, category_hint: Optional[str]) -> str:
        """Определить эффективную категорию: явный hint или авто-детект из текста вопроса."""
        explicit_hint = self._normalize_category_key(category_hint or "")
        if explicit_hint:
            logger.info(
                "RAG category hint resolved: source=explicit value=%s",
                explicit_hint,
            )
            return explicit_hint

        normalized_question = self._normalize_category_key(question)
        if not normalized_question:
            return ""

        now = time.time()
        if now >= self._certification_categories_cache_expires_at:
            self._certification_categories_cache = self._load_certification_category_aliases()
            self._certification_categories_cache_expires_at = now + _RAG_CATEGORY_CACHE_TTL_SECONDS

        best_match = ""
        best_score = 0
        question_tokens = set(self._tokenize(question))
        for category_key, label in self._certification_categories_cache:
            if not category_key:
                continue

            score = 0
            if category_key in normalized_question:
                score += 5

            label_tokens = set(self._tokenize(label))
            if label_tokens and question_tokens:
                score += len(label_tokens & question_tokens)

            if score > best_score:
                best_score = score
                best_match = category_key

        resolved = best_match if best_score > 0 else ""
        logger.info(
            "RAG category hint resolved: source=auto value=%s score=%s",
            resolved or "none",
            best_score,
        )
        return resolved

    def _load_certification_category_aliases(self) -> List[Tuple[str, str]]:
        """Загрузить список категорий аттестации для авто-детекта category-hint."""
        try:
            with database.get_db_connection() as conn:
                with database.get_cursor(conn) as cursor:
                    cursor.execute(
                        """
                        SELECT name
                        FROM certification_categories
                        ORDER BY display_order ASC, id ASC
                        """
                    )
                    rows = cursor.fetchall() or []
        except Exception:
            return []

        aliases: List[Tuple[str, str]] = []
        for row in rows:
            label = str(row.get("name") or "").strip()
            key = self._normalize_category_key(label)
            if key:
                aliases.append((key, label))
        return aliases

    @staticmethod
    def _normalize_category_key(value: str) -> str:
        """Нормализовать имя категории для устойчивого сравнения."""
        normalized = _SPACES_RE.sub(" ", str(value or "").strip().lower())
        return normalized

    def _calculate_signal_score_delta(self, signal: Dict[str, object], category_hint: str) -> float:
        """Вычислить корректировку score на основе category/freshness сигналов документа."""
        delta = 0.0
        safe_hint = self._normalize_category_key(category_hint)
        category_boost = max(0.0, float(ai_settings.AI_RAG_CERTIFICATION_CATEGORY_BOOST))
        stale_penalty = max(0.0, float(ai_settings.AI_RAG_CERTIFICATION_STALE_PENALTY))

        if safe_hint:
            category_keys = [
                self._normalize_category_key(key)
                for key in (signal.get("category_keys") or [])
                if str(key).strip()
            ]
            if safe_hint in category_keys:
                delta += category_boost

        is_outdated = bool(signal.get("is_outdated"))
        is_active = bool(signal.get("is_active"))
        if is_outdated or (not is_active):
            delta -= stale_penalty

        return delta

    def _apply_signal_adjustments_to_prefilter_docs(
        self,
        docs: List[Tuple[int, str, str, float]],
        category_hint: str,
    ) -> List[Tuple[int, str, str, float]]:
        """Применить category/freshness корректировки к prefilter-документам."""
        if not docs:
            return docs

        doc_ids = [int(doc_id) for doc_id, _, _, _ in docs]
        signals = self._load_document_signals(doc_ids)
        if not signals:
            return docs

        adjusted: List[Tuple[int, str, str, float]] = []
        boosted_doc_ids: List[int] = []
        penalized_doc_ids: List[int] = []
        for document_id, filename, summary_text, score in docs:
            signal = signals.get(int(document_id))
            delta = self._calculate_signal_score_delta(signal or {}, category_hint) if signal else 0.0
            adjusted_score = max(0.0, float(score) + delta)
            if adjusted_score <= 0:
                continue
            adjusted.append((document_id, filename, summary_text, adjusted_score))
            if delta > 0:
                boosted_doc_ids.append(int(document_id))
            elif delta < 0:
                penalized_doc_ids.append(int(document_id))

        logger.info(
            "RAG category hint usage: stage=prefilter hint=%s docs_total=%s boosted_docs=%s penalized_docs=%s boosted_doc_ids=%s penalized_doc_ids=%s",
            (self._normalize_category_key(category_hint) or "none"),
            len(docs),
            len(boosted_doc_ids),
            len(penalized_doc_ids),
            boosted_doc_ids[:20],
            penalized_doc_ids[:20],
        )

        return adjusted

    def _apply_signal_adjustments_to_chunks(
        self,
        chunks: List[Tuple[float, str, str, int, int]],
        category_hint: str,
    ) -> List[Tuple[float, str, str, int, int]]:
        """Применить category/freshness корректировки к финальному списку чанков."""
        if not chunks:
            return chunks

        doc_ids = [int(self._unpack_chunk_row(chunk)[3]) for chunk in chunks]
        signals = self._load_document_signals(doc_ids)
        if not signals:
            return chunks

        adjusted: List[Tuple[float, str, str, int, int]] = []
        boosted_doc_ids: List[int] = []
        penalized_doc_ids: List[int] = []
        for chunk in chunks:
            score, source, chunk_text, document_id, chunk_index = self._unpack_chunk_row(chunk)
            signal = signals.get(document_id)
            delta = self._calculate_signal_score_delta(signal or {}, category_hint) if signal else 0.0
            adjusted_score = max(0.0, float(score) + delta)
            if adjusted_score <= 0:
                continue
            adjusted.append((adjusted_score, source, chunk_text, document_id, chunk_index))
            if delta > 0:
                boosted_doc_ids.append(int(document_id))
            elif delta < 0:
                penalized_doc_ids.append(int(document_id))

        adjusted.sort(key=lambda item: item[0], reverse=True)
        logger.info(
            "RAG category hint usage: stage=final_chunks hint=%s chunks_total=%s boosted_docs=%s penalized_docs=%s boosted_doc_ids=%s penalized_doc_ids=%s",
            (self._normalize_category_key(category_hint) or "none"),
            len(chunks),
            len(set(boosted_doc_ids)),
            len(set(penalized_doc_ids)),
            list(dict.fromkeys(boosted_doc_ids))[:20],
            list(dict.fromkeys(penalized_doc_ids))[:20],
        )
        return adjusted

    def _search_summary_vector_scores_from_collection(
        self,
        question: str,
        document_ids: List[int],
        limit: int,
        hyde_text: Optional[str] = None,
    ) -> Dict[int, float]:
        """Получить summary vector-score из отдельной Qdrant-коллекции по списку document_id."""
        if not ai_settings.is_rag_summary_vector_enabled() or not self._is_vector_search_enabled():
            return {}

        embedding_provider = self._get_embedding_provider()
        vector_index = self._get_vector_index()
        if embedding_provider is None or vector_index is None:
            return {}

        embed_text = hyde_text if hyde_text else question
        query_vectors = embedding_provider.encode_texts([embed_text])
        if not query_vectors:
            return {}

        candidates = vector_index.search_summaries(
            query_vector=query_vectors[0],
            limit=max(1, int(limit), int(ai_settings.get_rag_summary_vector_top_k())),
            allowed_document_ids=document_ids,
        )
        if not candidates:
            return {}

        scores: Dict[int, float] = {}
        for candidate in candidates:
            safe_doc_id = int(candidate.document_id or 0)
            if safe_doc_id <= 0:
                continue
            safe_score = max(0.0, float(candidate.score or 0.0))
            scores[safe_doc_id] = max(safe_score, scores.get(safe_doc_id, 0.0))

        return scores

    @staticmethod
    def _build_summary_blocks(prefilter_docs: List[Tuple[int, str, str, float]]) -> List[str]:
        """Собрать summary-блоки для системного RAG-промпта."""
        max_docs = max(0, int(ai_settings.AI_RAG_PROMPT_SUMMARY_DOCS))
        if max_docs <= 0:
            return []

        summary_blocks: List[str] = []
        exclude_certification = bool(ai_settings.AI_RAG_PROMPT_SUMMARIES_EXCLUDE_CERTIFICATION)
        for _, filename, summary_text, _ in prefilter_docs:
            if exclude_certification and str(filename or "").strip().lower().startswith(_RAG_CERTIFICATION_FILENAME_PREFIX):
                continue
            safe_summary = summary_text.strip()
            if not safe_summary:
                continue
            summary_blocks.append(f"[Summary | {filename}]\n{safe_summary}")
            if len(summary_blocks) >= max_docs:
                break
        return summary_blocks

    @staticmethod
    def _parse_rag_json_response(raw: str) -> Tuple[str, bool]:
        """Разобрать JSON-ответ RAG LLM.

        Ожидаемый формат: {"answer": "...", "question_answered": true/false}

        При невозможности разбора — fallback к исходному тексту с question_answered=True.

        Args:
            raw: Сырой ответ LLM.

        Returns:
            (текст ответа, question_answered).
        """
        text = (raw or "").strip()
        if not text:
            return "", True

        # Шаг 1: удалить markdown code fences (```json ... ```)
        # Используем .match() вместо .search(), чтобы избежать ложного срабатывания
        # на code fences внутри поля "answer" JSON-объекта.
        fence_match = _JSON_CODE_FENCE_RE.match(text)
        if fence_match:
            text = fence_match.group(1).strip()

        # Шаг 2: попытка полного json.loads
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                answer = str(parsed.get("answer", "")).strip()
                question_answered = parsed.get("question_answered", True)
                if isinstance(question_answered, str):
                    question_answered = question_answered.lower() not in {"false", "0", "no", "нет"}
                return answer or raw.strip(), bool(question_answered)
        except (json.JSONDecodeError, ValueError):
            pass

        # Шаг 3: попытка найти первый JSON-объект в тексте
        obj_match = _JSON_OBJECT_RE.search(text)
        if obj_match:
            try:
                parsed = json.loads(obj_match.group(0))
                if isinstance(parsed, dict):
                    answer = str(parsed.get("answer", "")).strip()
                    question_answered = parsed.get("question_answered", True)
                    if isinstance(question_answered, str):
                        question_answered = question_answered.lower() not in {"false", "0", "no", "нет"}
                    return answer or raw.strip(), bool(question_answered)
            except (json.JSONDecodeError, ValueError):
                pass

        # Шаг 4: graceful fallback — вернуть исходный текст как ответ
        logger.warning(
            "RAG JSON parse failed, using raw text as answer: raw_len=%d raw_preview='%.120s'",
            len(raw),
            raw,
        )
        return raw.strip(), True

    def _retrieve_summaries_for_fallback(
        self,
        question: str,
        hyde_text: Optional[str] = None,
    ) -> List[str]:
        """Получить ранжированные summary-блоки для fallback-ответа.

        Выполняет независимый поиск по summary документов (BM25 + vector),
        возвращает отформатированные summary-блоки для fallback-промпта.

        Args:
            question: Вопрос пользователя.
            hyde_text: Опциональный HyDE-текст для vector scoring.

        Returns:
            Список строк-блоков формата "[Summary | filename]\\n{text}".
        """
        fallback_started_at = time.perf_counter()
        tokens = self._tokenize(question)
        if not tokens:
            return []

        stripped_question, pattern_stripped = self._strip_query_patterns(question)
        if pattern_stripped:
            retrieval_tokens = self._tokenize(stripped_question)
        else:
            retrieval_tokens = list(tokens)
        retrieval_tokens = self._filter_stopwords(retrieval_tokens) or list(tokens)

        if hyde_text and ai_settings.is_rag_hyde_lexical_enabled():
            retrieval_tokens = self._augment_tokens_with_hyde(retrieval_tokens, hyde_text)

        # Получить все активные summary из БД
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT s.document_id, s.summary_text, d.filename, d.source_type
                    FROM rag_document_summaries s
                    JOIN rag_documents d ON d.id = s.document_id
                    WHERE d.status = 'active'
                    ORDER BY s.updated_at DESC
                    LIMIT %s
                    """,
                    (_RAG_SUMMARY_SCAN_LIMIT,),
                )
                rows = cursor.fetchall() or []

        valid_rows: List[Tuple[int, str, str, str]] = []
        summaries_for_vector: List[Tuple[int, str]] = []
        for row in rows:
            document_id = int(row.get("document_id") or 0)
            filename = str(row.get("filename") or "document")
            summary_text = str(row.get("summary_text") or "").strip()
            source_type = str(row.get("source_type") or "").strip().lower()
            if not document_id or not summary_text:
                continue
            valid_rows.append((document_id, filename, summary_text, source_type))
            summaries_for_vector.append((document_id, summary_text))

        if not valid_rows:
            return []

        # Vector scoring
        vector_scores = self._search_summary_vector_scores_from_collection(
            question=question,
            document_ids=[doc_id for doc_id, _, _, _ in valid_rows],
            limit=len(valid_rows),
            hyde_text=hyde_text,
        )
        if not vector_scores:
            vector_scores = self._compute_summary_vector_scores(
                question=question,
                summaries=summaries_for_vector,
                hyde_text=hyde_text,
            )

        vector_weight = max(0.0, float(ai_settings.AI_RAG_SUMMARY_VECTOR_WEIGHT))
        lexical_scorer = ai_settings.get_rag_lexical_scorer()
        token_weight = max(0.0, float(ai_settings.AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT))

        # BM25 scoring
        summary_bm25_scores: Dict[int, float] = {}
        if lexical_scorer == "bm25":
            summary_corpus_tokens = [self._tokenize(summary_text) for _, _, summary_text, _ in valid_rows]
            dampened_tokens, dampening_diagnostics = self._dampen_common_query_tokens(
                retrieval_tokens,
                summary_corpus_tokens,
                return_diagnostics=True,
            )
            self._log_idf_dampening_effect(
                stage="summary_fallback",
                question=question,
                diagnostics=dampening_diagnostics,
            )
            corpus_scores = self._score_corpus_bm25(summary_corpus_tokens, dampened_tokens)
            for index, (document_id, _, _, _) in enumerate(valid_rows):
                summary_bm25_scores[document_id] = float(corpus_scores[index]) if index < len(corpus_scores) else 0.0

        # Score and rank
        scored_docs: List[Tuple[int, str, str, float]] = []
        for document_id, filename, summary_text, _ in valid_rows:
            if lexical_scorer == "bm25":
                lexical_score = summary_bm25_scores.get(document_id, 0.0) * token_weight
                lexical_score += self._score_summary_phrase_match(
                    summary_text=summary_text,
                    question_tokens=retrieval_tokens,
                    question=question,
                )
            else:
                lexical_score = self._score_summary_text(
                    summary_text=summary_text,
                    question_tokens=retrieval_tokens,
                    question=question,
                )
            vec_score = float(vector_scores.get(document_id, 0.0))
            score = lexical_score + (vec_score * vector_weight)
            if score <= 0:
                continue
            scored_docs.append((document_id, filename, summary_text, score))

        scored_docs.sort(key=lambda item: item[3], reverse=True)

        # Собрать summary-блоки с ограничениями
        max_docs = max(1, int(ai_settings.AI_RAG_SUMMARY_FALLBACK_TOP_DOCS))
        max_chars = max(500, int(ai_settings.AI_RAG_SUMMARY_FALLBACK_MAX_CONTEXT_CHARS))
        summary_blocks: List[str] = []
        total_chars = 0

        for _, filename, summary_text, _ in scored_docs:
            safe_summary = summary_text.strip()
            if not safe_summary:
                continue
            block = f"[Summary | {filename}]\n{safe_summary}"
            if total_chars + len(block) > max_chars:
                break
            summary_blocks.append(block)
            total_chars += len(block)
            if len(summary_blocks) >= max_docs:
                break

        fallback_ms = (time.perf_counter() - fallback_started_at) * 1000
        logger.info(
            "RAG summary fallback retrieval: valid_summaries=%d scored_docs=%d "
            "selected_blocks=%d total_chars=%d elapsed_ms=%.1f",
            len(valid_rows),
            len(scored_docs),
            len(summary_blocks),
            total_chars,
            fallback_ms,
        )
        return summary_blocks

    @staticmethod
    def _summary_score_bonus(summary_score: float) -> float:
        """Рассчитать бонус чанку на основе релевантности summary документа."""
        normalized_summary_score = RagKnowledgeService._normalize_summary_score(summary_score)
        return RagKnowledgeService._summary_score_bonus_from_normalized(normalized_summary_score)

    @staticmethod
    def _summary_score_bonus_from_normalized(normalized_summary_score: float) -> float:
        """Рассчитать бонус чанку из нормализованного summary-score (0..1)."""
        safe_score = max(0.0, min(1.0, float(normalized_summary_score or 0.0)))
        if safe_score <= 0:
            return 0.0

        bonus_weight = max(0.0, float(ai_settings.AI_RAG_SUMMARY_BONUS_WEIGHT))
        return safe_score * bonus_weight

    @staticmethod
    def _summary_postrank_bonus(summary_score: float) -> float:
        """Рассчитать пост-бонус документа при финальном hybrid-ранжировании."""
        normalized_summary_score = RagKnowledgeService._normalize_summary_score(summary_score)
        return RagKnowledgeService._summary_postrank_bonus_from_normalized(normalized_summary_score)

    @staticmethod
    def _summary_postrank_bonus_from_normalized(normalized_summary_score: float) -> float:
        """Рассчитать пост-бонус документа из нормализованного summary-score (0..1)."""
        safe_score = max(0.0, min(1.0, float(normalized_summary_score or 0.0)))
        if safe_score <= 0:
            return 0.0

        postrank_weight = max(0.0, float(ai_settings.AI_RAG_SUMMARY_POSTRANK_WEIGHT))
        return safe_score * postrank_weight

    @staticmethod
    def _normalize_summary_score(summary_score: float) -> float:
        """Нормализовать summary-score документа в диапазон 0..1 по верхней границе cap."""
        if summary_score <= 0:
            return 0.0

        score_cap = max(0.0, float(ai_settings.AI_RAG_SUMMARY_SCORE_CAP))
        if score_cap <= 0:
            return 0.0

        return min(summary_score, score_cap) / score_cap

    @staticmethod
    def _build_relative_summary_scores(summary_scores: Dict[int, float]) -> Dict[int, float]:
        """Нормализовать summary-score документов в текущем пуле retrieval по min-max в диапазон 0..1."""
        if not summary_scores:
            return {}

        cleaned_scores: Dict[int, float] = {}
        for document_id, score in summary_scores.items():
            safe_doc_id = int(document_id or 0)
            safe_score = max(0.0, float(score or 0.0))
            if safe_doc_id <= 0 or safe_score <= 0:
                continue
            cleaned_scores[safe_doc_id] = safe_score

        if not cleaned_scores:
            return {}

        min_score = min(cleaned_scores.values())
        max_score = max(cleaned_scores.values())
        if max_score <= min_score:
            return {doc_id: 1.0 for doc_id in cleaned_scores}

        denominator = max_score - min_score
        normalized_scores: Dict[int, float] = {}
        for doc_id, score in cleaned_scores.items():
            normalized = (score - min_score) / denominator
            normalized_scores[doc_id] = max(0.0, min(1.0, normalized))

        return normalized_scores

    def _score_summary_text(self, summary_text: str, question_tokens: List[str], question: str) -> float:
        """Оценить релевантность summary по фразовому и токенному совпадению.

        Фразовый матч использует word-boundary regex, чтобы 'X5' не
        совпадало внутри 'VX520'.
        """
        low_summary = self._normalize_for_phrase_match(summary_text)
        if not low_summary:
            return 0.0

        token_weight = max(0.0, float(ai_settings.AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT))
        token_score = self._score_chunk(summary_text, question_tokens)
        phrase_score = self._score_summary_phrase_match(
            summary_text=summary_text,
            question_tokens=question_tokens,
            question=question,
        )

        return (token_score * token_weight) + phrase_score

    def _score_summary_phrase_match(self, summary_text: str, question_tokens: List[str], question: str) -> float:
        """Оценить фразовое совпадение вопроса и summary (с учётом word-boundary)."""
        low_summary = self._normalize_for_phrase_match(summary_text)
        if not low_summary:
            return 0.0

        phrase_weight = max(0.0, float(ai_settings.AI_RAG_SUMMARY_MATCH_PHRASE_WEIGHT))
        phrase_score = 0.0

        normalized_question = self._normalize_for_phrase_match(question)
        normalized_token_phrase = self._normalize_for_phrase_match(" ".join(question_tokens))

        if len(normalized_question) >= 2 and self._word_boundary_match(normalized_question, low_summary):
            phrase_score = 1.0
        elif normalized_token_phrase and self._word_boundary_match(normalized_token_phrase, low_summary):
            phrase_score = 0.8

        return phrase_score * phrase_weight

    @staticmethod
    def _normalize_for_phrase_match(text: str) -> str:
        """Нормализовать текст для фразового матчингa без учёта регистра и лишних пробелов."""
        normalized = _SPACES_RE.sub(" ", (text or "").lower())
        return normalized.strip()

    @staticmethod
    def _word_boundary_match(phrase: str, text: str) -> bool:
        """Проверить наличие фразы в тексте по word-boundary (\\b).

        Используется вместо оператора ``in``, чтобы ``'x5'`` не
        совпадало внутри ``'vx520'``.
        """
        if not phrase or not text:
            return False
        try:
            return bool(re.search(r"\b" + re.escape(phrase) + r"\b", text, re.IGNORECASE))
        except re.error:
            return phrase in text

    def _compute_summary_vector_scores(
        self,
        question: str,
        summaries: List[Tuple[int, str]],
        hyde_text: Optional[str] = None,
    ) -> Dict[int, float]:
        """Вычислить семантическое сходство вопроса и каждого summary через эмбеддинги.

        Результат — словарь {document_id: cosine_similarity}.  Если
        embedding-провайдер недоступен, возвращается пустой словарь
        (graceful degradation).
        """
        if not summaries:
            return {}

        embedding_provider = self._get_embedding_provider()
        if embedding_provider is None:
            return {}

        corpus_version = self._get_corpus_version()
        if corpus_version != self._summary_embedding_corpus_version:
            self._summary_embedding_cache.clear()
            self._summary_embedding_corpus_version = corpus_version

        embed_text = hyde_text if hyde_text else question
        question_vectors = embedding_provider.encode_texts([embed_text])
        if not question_vectors:
            return {}
        q_vec = question_vectors[0]

        uncached_ids: List[int] = []
        uncached_texts: List[str] = []
        for doc_id, summary_text in summaries:
            if doc_id not in self._summary_embedding_cache:
                uncached_ids.append(doc_id)
                uncached_texts.append(summary_text)

        if uncached_texts:
            new_vectors = embedding_provider.encode_texts(uncached_texts)
            for idx, doc_id in enumerate(uncached_ids):
                if idx < len(new_vectors):
                    self._summary_embedding_cache[doc_id] = new_vectors[idx]

        scores: Dict[int, float] = {}
        for doc_id, _ in summaries:
            s_vec = self._summary_embedding_cache.get(doc_id)
            if s_vec is None:
                continue
            similarity = self._cosine_dot(q_vec, s_vec)
            scores[doc_id] = max(0.0, similarity)

        return scores

    @staticmethod
    def _cosine_dot(vec_a: List[float], vec_b: List[float]) -> float:
        """Вычислить скалярное произведение (≈cosine similarity для L2-нормированных)."""
        return sum(a * b for a, b in zip(vec_a, vec_b))

    @staticmethod
    def _get_fallback_active_document_ids(
        exclude_document_ids: List[int],
        limit: int,
    ) -> List[int]:
        """Получить fallback-список активных документов для сохранения recall."""
        safe_limit = max(0, min(int(limit), 100))
        if safe_limit <= 0:
            return []

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if exclude_document_ids:
                    placeholders = ",".join(["%s"] * len(exclude_document_ids))
                    cursor.execute(
                        f"""
                        SELECT id
                        FROM rag_documents
                        WHERE status = 'active' AND id NOT IN ({placeholders})
                        ORDER BY updated_at DESC, id DESC
                        LIMIT %s
                        """,
                        tuple(exclude_document_ids) + (safe_limit,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id
                        FROM rag_documents
                        WHERE status = 'active'
                        ORDER BY updated_at DESC, id DESC
                        LIMIT %s
                        """,
                        (safe_limit,),
                    )
                rows = cursor.fetchall() or []

        fallback_ids: List[int] = []
        for row in rows:
            document_id = int(row.get("id") or 0)
            if document_id > 0:
                fallback_ids.append(document_id)
        return fallback_ids

    def _determine_retrieval_mode(
        self,
        lexical_chunks: List[Tuple[float, str, str, int]],
        vector_chunks: List[Tuple[float, str, str, int]],
        selected_chunks: List[Tuple[float, str, str, int]],
    ) -> str:
        """Определить режим retrieval для диагностического логирования."""
        if not selected_chunks:
            return "lexical_only"

        has_lexical = len(lexical_chunks) > 0
        has_vector = len(vector_chunks) > 0

        if has_lexical and has_vector and ai_settings.AI_RAG_HYBRID_ENABLED:
            return "hybrid"

        if has_vector and (not ai_settings.AI_RAG_HYBRID_ENABLED or not has_lexical):
            return "vector_only"

        if has_lexical and not has_vector and ai_settings.AI_RAG_HYBRID_ENABLED and self._is_vector_search_enabled():
            return "lexical_fallback"

        return "lexical_only"

    def _is_vector_search_enabled(self) -> bool:
        """Проверить, включён ли векторный retrieval через конфигурацию."""
        return bool(ai_settings.AI_RAG_VECTOR_ENABLED)

    def _get_embedding_provider(self) -> Optional[LocalEmbeddingProvider]:
        """Получить lazy-singleton провайдера локальных эмбеддингов."""
        if not self._is_vector_search_enabled():
            return None

        if self._embedding_provider is None:
            self._embedding_provider = LocalEmbeddingProvider()

        if not self._embedding_provider.is_ready():
            return None
        return self._embedding_provider

    def _get_vector_index(self) -> Optional[LocalVectorIndex]:
        """Получить lazy-singleton локального векторного индекса."""
        if not self._is_vector_search_enabled():
            return None

        if self._vector_index is None:
            self._vector_index = LocalVectorIndex()

        if not self._vector_index.is_ready():
            return None

        return self._vector_index

    def _upsert_vectors_for_chunks(self, chunks: List[Dict[str, object]]) -> int:
        """Записать эмбеддинги чанков в локальный векторный индекс."""
        if not chunks or not self._is_vector_search_enabled():
            return 0

        embedding_provider = self._get_embedding_provider()
        vector_index = self._get_vector_index()
        if embedding_provider is None or vector_index is None:
            return 0

        texts = [str(chunk.get("chunk_text") or "") for chunk in chunks]
        embeddings = embedding_provider.encode_texts(texts)
        if not embeddings:
            self._record_chunk_embedding_metadata(
                chunks=chunks,
                embeddings=[],
                status="failed",
                error_message="embedding_unavailable",
            )
            return 0

        upsert_started_at = time.perf_counter()
        upserted = vector_index.upsert_chunks(chunks=chunks, embeddings=embeddings)
        upsert_duration_ms = (time.perf_counter() - upsert_started_at) * 1000
        if upserted > 0:
            self._record_chunk_embedding_metadata(
                chunks=chunks,
                embeddings=embeddings,
                status="ready",
                error_message=None,
            )
        else:
            self._record_chunk_embedding_metadata(
                chunks=chunks,
                embeddings=[],
                status="failed",
                error_message="vector_upsert_failed",
            )
        if upserted > 0:
            logger.info("RAG vector upsert: chunks=%s duration_ms=%.2f", upserted, upsert_duration_ms)
        return upserted

    def _upsert_vectors_for_summaries(self, summaries: List[Dict[str, object]]) -> int:
        """Записать эмбеддинги summary-документов в отдельную vector-коллекцию."""
        if not summaries or not self._is_vector_search_enabled() or not ai_settings.is_rag_summary_vector_enabled():
            return 0

        embedding_provider = self._get_embedding_provider()
        vector_index = self._get_vector_index()
        if embedding_provider is None or vector_index is None:
            return 0

        texts = [str(summary.get("summary_text") or "") for summary in summaries]
        embeddings = embedding_provider.encode_texts(texts)
        if not embeddings:
            self._record_summary_embedding_metadata(
                summaries=summaries,
                embeddings=[],
                status="failed",
                error_message="embedding_unavailable",
            )
            return 0

        upsert_started_at = time.perf_counter()
        upserted = vector_index.upsert_summaries(summaries=summaries, embeddings=embeddings)
        upsert_duration_ms = (time.perf_counter() - upsert_started_at) * 1000

        if upserted > 0:
            self._record_summary_embedding_metadata(
                summaries=summaries,
                embeddings=embeddings,
                status="ready",
                error_message=None,
            )
        else:
            self._record_summary_embedding_metadata(
                summaries=summaries,
                embeddings=[],
                status="failed",
                error_message="vector_upsert_failed",
            )

        if upserted > 0:
            logger.info("RAG summary vector upsert: documents=%s duration_ms=%.2f", upserted, upsert_duration_ms)
        return upserted

    def _record_chunk_embedding_metadata(
        self,
        chunks: List[Dict[str, object]],
        embeddings: List[List[float]],
        status: str,
        error_message: Optional[str],
    ) -> None:
        """Сохранить технические метаданные векторной индексации чанков в БД."""
        if not chunks:
            return

        safe_status = status if status in {"ready", "failed", "stale"} else "failed"
        model_name = str(ai_settings.AI_RAG_VECTOR_EMBEDDING_MODEL or "unknown")[:128]
        vector_dim = len(embeddings[0]) if embeddings else 0
        safe_error = (error_message or "")[:255] or None

        query = """
            INSERT INTO rag_chunk_embeddings
                (document_id, chunk_index, embedding_model, embedding_dim, embedding_hash, embedding_status, error_message, embedded_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                embedding_dim = VALUES(embedding_dim),
                embedding_hash = VALUES(embedding_hash),
                embedding_status = VALUES(embedding_status),
                error_message = VALUES(error_message),
                embedded_at = NOW(),
                updated_at = NOW()
        """

        params: List[Tuple[int, int, str, int, str, str, Optional[str]]] = []
        for index, chunk in enumerate(chunks):
            document_id = int(chunk.get("document_id") or 0)
            chunk_index = int(chunk.get("chunk_index") or 0)
            if document_id <= 0:
                continue

            if embeddings and index < len(embeddings):
                vector = embeddings[index]
                vector_hash = hashlib.sha256(
                    ",".join(f"{float(value):.6f}" for value in vector).encode("utf-8")
                ).hexdigest()
            else:
                vector_hash = hashlib.sha256(
                    str(chunk.get("chunk_text") or "").encode("utf-8")
                ).hexdigest()

            params.append(
                (
                    document_id,
                    chunk_index,
                    model_name,
                    vector_dim,
                    vector_hash,
                    safe_status,
                    safe_error,
                )
            )

        if not params:
            return

        try:
            for batch_start in range(0, len(params), _RAG_EMBEDDING_UPSERT_BATCH_SIZE):
                batch = params[batch_start : batch_start + _RAG_EMBEDDING_UPSERT_BATCH_SIZE]
                for attempt in range(1, _RAG_EMBEDDING_UPSERT_MAX_RETRIES + 1):
                    try:
                        with database.get_db_connection() as conn:
                            with database.get_cursor(conn) as cursor:
                                cursor.executemany(query, batch)
                        break
                    except Exception as exc:
                        mysql_errno = getattr(exc, "errno", None)
                        is_retryable = mysql_errno in _MYSQL_RETRYABLE_ERRNOS
                        if not is_retryable or attempt >= _RAG_EMBEDDING_UPSERT_MAX_RETRIES:
                            raise

                        delay = _RAG_EMBEDDING_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                        logger.warning(
                            "Повтор сохранения rag_chunk_embeddings после временной ошибки БД: errno=%s attempt=%s/%s batch_size=%s sleep=%.2fs",
                            mysql_errno,
                            attempt,
                            _RAG_EMBEDDING_UPSERT_MAX_RETRIES,
                            len(batch),
                            delay,
                        )
                        time.sleep(delay)
        except Exception as exc:
            logger.warning("Не удалось сохранить rag_chunk_embeddings: %s", exc)

    def _record_summary_embedding_metadata(
        self,
        summaries: List[Dict[str, object]],
        embeddings: List[List[float]],
        status: str,
        error_message: Optional[str],
    ) -> None:
        """Сохранить технические метаданные векторной индексации summary документов в БД."""
        if not summaries:
            return

        safe_status = status if status in {"ready", "failed", "stale"} else "failed"
        model_name = str(ai_settings.AI_RAG_VECTOR_EMBEDDING_MODEL or "unknown")[:128]
        vector_dim = len(embeddings[0]) if embeddings else 0
        safe_error = (error_message or "")[:255] or None

        query = """
            INSERT INTO rag_summary_embeddings
                (document_id, embedding_model, embedding_dim, embedding_hash, embedding_status, error_message, embedded_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                embedding_dim = VALUES(embedding_dim),
                embedding_hash = VALUES(embedding_hash),
                embedding_status = VALUES(embedding_status),
                error_message = VALUES(error_message),
                embedded_at = NOW(),
                updated_at = NOW()
        """

        params: List[Tuple[int, str, int, str, str, Optional[str]]] = []
        for index, summary in enumerate(summaries):
            document_id = int(summary.get("document_id") or 0)
            if document_id <= 0:
                continue

            if embeddings and index < len(embeddings):
                vector = embeddings[index]
                vector_hash = hashlib.sha256(
                    ",".join(f"{float(value):.6f}" for value in vector).encode("utf-8")
                ).hexdigest()
            else:
                vector_hash = hashlib.sha256(
                    str(summary.get("summary_text") or "").encode("utf-8")
                ).hexdigest()

            params.append(
                (
                    document_id,
                    model_name,
                    vector_dim,
                    vector_hash,
                    safe_status,
                    safe_error,
                )
            )

        if not params:
            return

        try:
            for batch_start in range(0, len(params), _RAG_EMBEDDING_UPSERT_BATCH_SIZE):
                batch = params[batch_start : batch_start + _RAG_EMBEDDING_UPSERT_BATCH_SIZE]
                for attempt in range(1, _RAG_EMBEDDING_UPSERT_MAX_RETRIES + 1):
                    try:
                        with database.get_db_connection() as conn:
                            with database.get_cursor(conn) as cursor:
                                cursor.executemany(query, batch)
                        break
                    except Exception as exc:
                        mysql_errno = getattr(exc, "errno", None)
                        is_retryable = mysql_errno in _MYSQL_RETRYABLE_ERRNOS
                        if not is_retryable or attempt >= _RAG_EMBEDDING_UPSERT_MAX_RETRIES:
                            raise

                        delay = _RAG_EMBEDDING_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                        logger.warning(
                            "Повтор сохранения rag_summary_embeddings после временной ошибки БД: errno=%s attempt=%s/%s batch_size=%s sleep=%.2fs",
                            mysql_errno,
                            attempt,
                            _RAG_EMBEDDING_UPSERT_MAX_RETRIES,
                            len(batch),
                            delay,
                        )
                        time.sleep(delay)
        except Exception as exc:
            logger.warning("Не удалось сохранить rag_summary_embeddings: %s", exc)

    def _set_vector_document_status(self, document_id: int, status: str) -> int:
        """Синхронизировать статус документа в векторном индексе."""
        if not self._is_vector_search_enabled():
            return 0

        vector_index = self._get_vector_index()
        if vector_index is None:
            return 0
        chunks_status_result = vector_index.mark_document_status(document_id=document_id, status=status)
        if ai_settings.is_rag_summary_vector_enabled():
            vector_index.mark_summary_status(document_id=document_id, status=status)
        return chunks_status_result

    def _delete_vector_document(self, document_id: int) -> int:
        """Удалить векторные точки документа при hard-delete."""
        if not self._is_vector_search_enabled():
            return 0

        vector_index = self._get_vector_index()
        if vector_index is None:
            return 0
        deleted = vector_index.delete_document_points(document_id=document_id)
        if ai_settings.is_rag_summary_vector_enabled():
            vector_index.delete_summary_points(document_id=document_id)
        return deleted

    def backfill_vector_index(
        self,
        batch_size: int = 100,
        source_type: Optional[str] = None,
        dry_run: bool = False,
        max_documents: Optional[int] = None,
        target: str = "both",
    ) -> Dict[str, int]:
        """Выполнить пакетное заполнение векторных индексов (chunks/summaries/both)."""
        stats = {
            "documents_total": 0,
            "documents_processed": 0,
            "chunks_indexed": 0,
            "summaries_indexed": 0,
            "errors": 0,
        }
        if not self._is_vector_search_enabled():
            return stats

        safe_batch_size = max(1, int(batch_size))
        normalized_target = str(target or "both").strip().lower()
        if normalized_target not in {"chunks", "summaries", "both"}:
            raise ValueError("Некорректный target для backfill: ожидается chunks|summaries|both")

        include_chunks = normalized_target in {"chunks", "both"}
        include_summaries = normalized_target in {"summaries", "both"}
        if include_summaries and not ai_settings.is_rag_summary_vector_enabled():
            include_summaries = False

        grouped_chunks = self._load_backfill_chunks(source_type=source_type) if include_chunks else {}
        grouped_summaries = self._load_backfill_summaries(source_type=source_type) if include_summaries else {}

        document_ids = sorted(set(grouped_chunks.keys()) | set(grouped_summaries.keys()))
        if max_documents is not None and int(max_documents) > 0:
            document_ids = document_ids[: int(max_documents)]

        stats["documents_total"] = len(document_ids)

        for document_id in document_ids:
            chunks = grouped_chunks.get(document_id, [])
            summary_rows = grouped_summaries.get(document_id, [])
            if not chunks and not summary_rows:
                continue

            try:
                if dry_run:
                    stats["chunks_indexed"] += len(chunks)
                    stats["summaries_indexed"] += len(summary_rows)
                else:
                    if include_chunks and chunks:
                        for start in range(0, len(chunks), safe_batch_size):
                            batch = chunks[start : start + safe_batch_size]
                            stats["chunks_indexed"] += self._upsert_vectors_for_chunks(batch)
                    if include_summaries and summary_rows:
                        for start in range(0, len(summary_rows), safe_batch_size):
                            batch = summary_rows[start : start + safe_batch_size]
                            stats["summaries_indexed"] += self._upsert_vectors_for_summaries(batch)
                stats["documents_processed"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.warning("Ошибка backfill vector index для document_id=%s: %s", document_id, exc)

        return stats

    @staticmethod
    def _load_backfill_chunks(source_type: Optional[str]) -> Dict[int, List[Dict[str, object]]]:
        """Загрузить активные чанки документов для chunk backfill."""
        query = """
            SELECT d.id, d.filename, d.source_type, c.chunk_index, c.chunk_text
            FROM rag_documents d
            JOIN rag_chunks c ON c.document_id = d.id
            WHERE d.status = 'active'
        """
        params: List[object] = []
        if source_type:
            query += " AND d.source_type = %s"
            params.append(source_type)
        query += " ORDER BY d.id ASC, c.chunk_index ASC"

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall() or []

        grouped: Dict[int, List[Dict[str, object]]] = {}
        for row in rows:
            document_id = int(row.get("id") or 0)
            if document_id <= 0:
                continue
            grouped.setdefault(document_id, []).append(
                {
                    "document_id": document_id,
                    "chunk_index": int(row.get("chunk_index") or 0),
                    "filename": str(row.get("filename") or "document"),
                    "chunk_text": str(row.get("chunk_text") or ""),
                    "status": "active",
                }
            )
        return grouped

    @staticmethod
    def _load_backfill_summaries(source_type: Optional[str]) -> Dict[int, List[Dict[str, object]]]:
        """Загрузить активные summary документов для summary backfill."""
        query = """
            SELECT d.id, d.filename, d.source_type, s.summary_text
            FROM rag_documents d
            JOIN rag_document_summaries s ON s.document_id = d.id
            WHERE d.status = 'active'
        """
        params: List[object] = []
        if source_type:
            query += " AND d.source_type = %s"
            params.append(source_type)
        query += " ORDER BY d.id ASC"

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall() or []

        grouped: Dict[int, List[Dict[str, object]]] = {}
        for row in rows:
            document_id = int(row.get("id") or 0)
            summary_text = str(row.get("summary_text") or "").strip()
            if document_id <= 0 or not summary_text:
                continue

            grouped.setdefault(document_id, []).append(
                {
                    "document_id": document_id,
                    "filename": str(row.get("filename") or "document"),
                    "summary_text": summary_text,
                    "status": "active",
                }
            )

        return grouped

    def _tokenize(self, text: str) -> List[str]:
        """Токенизировать текст для lexical retrieval c опциональной нормализацией RU."""
        raw_tokens = _TOKEN_RE.findall((text or "").lower())
        tokens = [
            token
            for token in raw_tokens
            if len(token) >= 3
            or token in _RAG_FIXED_QUERY_TERMS
            or bool(_SHORT_ALNUM_TOKEN_RE.fullmatch(token))
            or (token.isdigit() and len(token) >= 2)
        ]
        if not tokens:
            return []

        if not ai_settings.is_rag_ru_normalization_enabled():
            return tokens

        return [self._normalize_token(token) for token in tokens if token]

    @staticmethod
    def _strip_query_patterns(question: str) -> Tuple[str, bool]:
        """Извлечь предметную часть из типового вопросительного шаблона.

        Если вопрос начинается с конструкции вроде «что такое X»,
        «как работает Y», возвращается предметная часть (X / Y) и флаг
        ``True``.  Если шаблон не распознан или предметная часть пуста,
        возвращается исходный текст и ``False``.
        """
        if not ai_settings.is_rag_query_pattern_strip_enabled():
            return question, False

        normalized_question = (question or "").strip()
        if not normalized_question:
            return question, False

        for pattern in _QUERY_STRIP_PATTERNS:
            match = pattern.match(normalized_question)
            if match:
                subject = (match.group(1) or "").strip().rstrip("?!.")
                if _HASHTAG_WORD_RE.search(subject):
                    return subject, True
                # Проверяем, что предметная часть содержит хотя бы 1 токен ≥3 символов
                if subject and _TOKEN_RE.search(subject):
                    return subject, True

        return question, False

    @staticmethod
    def _filter_stopwords(tokens: List[str]) -> List[str]:
        """Отфильтровать стоп-слова из списка токенов.

        Если после фильтрации список пуст, возвращается исходный
        список без изменений (safety guard).
        """
        if not ai_settings.is_rag_stopwords_enabled():
            return tokens

        if not tokens:
            return tokens

        filtered = [token for token in tokens if token not in _RU_STOPWORDS]
        # Safety guard: если все токены — стоп-слова, возвращаем оригинал
        if not filtered:
            return tokens

        return filtered

    def _augment_tokens_with_hyde(self, tokens: List[str], hyde_text: str) -> List[str]:
        """Дополнить список query-токенов уникальными токенами из HyDE-текста.

        Токенизирует HyDE-текст, удаляет стоп-слова и добавляет только те
        токены, которых ещё нет в исходном списке.  Порядок: оригинальные
        токены идут первыми, затем HyDE-токены (для стабильного BM25 TF).

        Args:
            tokens: Исходные query-токены (после preprocessing).
            hyde_text: Гипотетический документ, сгенерированный LLM.

        Returns:
            Дополненный список токенов.
        """
        if not hyde_text or not hyde_text.strip():
            return tokens

        hyde_tokens = self._tokenize(hyde_text)
        if not hyde_tokens:
            return tokens

        # Убрать стоп-слова из HyDE-токенов
        hyde_tokens = [t for t in hyde_tokens if t not in _RU_STOPWORDS]
        if not hyde_tokens:
            return tokens

        existing_set = set(tokens)
        new_tokens = [t for t in dict.fromkeys(hyde_tokens) if t not in existing_set]
        if not new_tokens:
            return tokens

        return tokens + new_tokens

    @staticmethod
    def _dampen_common_query_tokens(
        query_tokens: List[str],
        corpus_tokens: List[List[str]],
        return_diagnostics: bool = False,
    ) -> List[str] | Tuple[List[str], Dict[str, object]]:
        """Подавить query-токены с высокой document frequency в corpus.

        Токены, встречающиеся более чем в ``AI_RAG_PREFILTER_IDF_DAMPEN_RATIO``
        доле документов, дублируются с пониженным весом (через сокращение числа
        повторений), чтобы BM25 IDF не завышал их вклад в однородном корпусе.

        Вместо изменения весов (BM25Okapi не поддерживает пользовательские
        веса терминов), метод возвращает модифицированный список query-токенов,
        в котором часто встречающиеся токены заменены на одну «dampened» копию,
        а редкие — повторяются для усиления влияния.

        Если ``return_diagnostics=True``, дополнительно возвращает словарь
        с диагностикой применения dampening (для runtime-логирования).
        """
        def _result(
            tokens: List[str],
            *,
            reason: str,
            doc_count: int,
            threshold: float,
            dampen_ratio: float,
            dampen_factor: float,
            common_tokens: Optional[set[str]] = None,
            rare_tokens: Optional[List[str]] = None,
            boost_factor: int = 1,
        ) -> List[str] | Tuple[List[str], Dict[str, object]]:
            if not return_diagnostics:
                return tokens

            before_counts = Counter(query_tokens)
            after_counts = Counter(tokens)
            changed_counts: Dict[str, Dict[str, int]] = {}
            for token in sorted(set(before_counts) | set(after_counts)):
                before = int(before_counts.get(token, 0))
                after = int(after_counts.get(token, 0))
                if before != after:
                    changed_counts[token] = {"before": before, "after": after}

            diagnostics: Dict[str, object] = {
                "applied": bool(reason == "applied"),
                "reason": reason,
                "doc_count": int(doc_count),
                "threshold_docs": float(threshold),
                "dampen_ratio": float(dampen_ratio),
                "dampen_factor": float(dampen_factor),
                "boost_factor": int(boost_factor),
                "before_count": len(query_tokens),
                "after_count": len(tokens),
                "before_tokens": list(query_tokens),
                "after_tokens": list(tokens),
                "common_tokens": sorted(common_tokens or set()),
                "rare_tokens": sorted(set(rare_tokens or [])),
                "changed_token_counts": changed_counts,
            }
            return tokens, diagnostics

        dampen_ratio = max(0.0, min(1.0, float(ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_RATIO)))
        dampen_factor = max(0.0, min(1.0, float(ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_FACTOR)))

        if not query_tokens or not corpus_tokens:
            return _result(
                list(query_tokens),
                reason="empty_input",
                doc_count=len(corpus_tokens),
                threshold=0.0,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
            )

        if dampen_ratio >= 1.0:
            return _result(
                list(query_tokens),
                reason="ratio_disabled",
                doc_count=len(corpus_tokens),
                threshold=0.0,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
            )

        doc_count = len(corpus_tokens)
        if doc_count == 0:
            return _result(
                list(query_tokens),
                reason="empty_corpus",
                doc_count=doc_count,
                threshold=0.0,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
            )

        # Подсчёт document frequency каждого уникального query-токена
        unique_query_tokens = set(query_tokens)
        doc_freq: Dict[str, int] = {}
        for token in unique_query_tokens:
            count = sum(1 for doc_tokens in corpus_tokens if token in doc_tokens)
            doc_freq[token] = count

        # Классификация токенов: common (DF > ratio) vs rare
        threshold = dampen_ratio * doc_count
        common_tokens = {token for token, df in doc_freq.items() if df > threshold}

        if not common_tokens:
            return _result(
                list(query_tokens),
                reason="no_common_tokens",
                doc_count=doc_count,
                threshold=threshold,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
                common_tokens=common_tokens,
            )

        # Все токены являются common — не подавляем (возвращаем как есть)
        rare_tokens = [t for t in query_tokens if t not in common_tokens]
        if not rare_tokens:
            return _result(
                list(query_tokens),
                reason="all_tokens_common",
                doc_count=doc_count,
                threshold=threshold,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
                common_tokens=common_tokens,
                rare_tokens=rare_tokens,
            )

        # Строим модифицированный список: rare-токены усиливаются повторением,
        # common-токены включаются один раз с пониженным коэффициентом.
        # BM25 считает TF по количеству вхождений токена в query, поэтому
        # повторение — способ увеличения веса.
        boost_factor = max(1, int(round(1.0 / max(dampen_factor, 0.01))))
        dampened_query: List[str] = []
        seen_common: set[str] = set()
        for token in query_tokens:
            if token in common_tokens:
                if token not in seen_common:
                    dampened_query.append(token)
                    seen_common.add(token)
            else:
                # Редкий (информативный) токен: усиливаем повторением
                for _ in range(boost_factor):
                    dampened_query.append(token)

        return _result(
            dampened_query,
            reason="applied",
            doc_count=doc_count,
            threshold=threshold,
            dampen_ratio=dampen_ratio,
            dampen_factor=dampen_factor,
            common_tokens=common_tokens,
            rare_tokens=rare_tokens,
            boost_factor=boost_factor,
        )

    @staticmethod
    def _trim_tokens_for_log(tokens: List[str], limit: int = 20) -> List[str]:
        """Ограничить размер списка токенов для компактного runtime-лога."""
        if len(tokens) <= limit:
            return list(tokens)
        return list(tokens[:limit]) + [f"...(+{len(tokens) - limit})"]

    def _log_idf_dampening_effect(
        self,
        *,
        stage: str,
        question: str,
        diagnostics: Dict[str, object],
    ) -> None:
        """Записать в лог, как IDF-dampening повлиял на query-токены."""
        question_preview = _SPACES_RE.sub(" ", str(question or "").strip())
        if len(question_preview) > 160:
            question_preview = f"{question_preview[:159]}…"

        before_tokens = [str(token) for token in diagnostics.get("before_tokens", [])]
        after_tokens = [str(token) for token in diagnostics.get("after_tokens", [])]
        common_tokens = [str(token) for token in diagnostics.get("common_tokens", [])]
        rare_tokens = [str(token) for token in diagnostics.get("rare_tokens", [])]
        changed_token_counts = diagnostics.get("changed_token_counts", {})
        if not isinstance(changed_token_counts, dict):
            changed_token_counts = {}

        payload = {
            "question": question_preview,
            "applied": bool(diagnostics.get("applied", False)),
            "reason": str(diagnostics.get("reason", "unknown")),
            "doc_count": int(diagnostics.get("doc_count", 0) or 0),
            "threshold_docs": round(float(diagnostics.get("threshold_docs", 0.0) or 0.0), 3),
            "dampen_ratio": round(float(diagnostics.get("dampen_ratio", 0.0) or 0.0), 3),
            "dampen_factor": round(float(diagnostics.get("dampen_factor", 0.0) or 0.0), 3),
            "boost_factor": int(diagnostics.get("boost_factor", 1) or 1),
            "before_count": int(diagnostics.get("before_count", len(before_tokens)) or 0),
            "after_count": int(diagnostics.get("after_count", len(after_tokens)) or 0),
            "before_tokens": self._trim_tokens_for_log(before_tokens),
            "after_tokens": self._trim_tokens_for_log(after_tokens),
            "common_tokens": self._trim_tokens_for_log(common_tokens, limit=10),
            "rare_tokens": self._trim_tokens_for_log(rare_tokens, limit=10),
            "changed_token_counts": changed_token_counts,
        }

        logger.info("RAG IDF dampening [%s]: %s", stage, json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def _normalize_token(self, token: str) -> str:
        """Нормализовать токен с кэшем (лемматизация/стемминг для русского)."""
        safe_token = (token or "").strip().lower()
        if not safe_token:
            return ""

        if safe_token in _RAG_FIXED_QUERY_TERMS:
            self._normalized_token_cache[safe_token] = safe_token
            return safe_token

        cached = self._normalized_token_cache.get(safe_token)
        if cached is not None:
            return cached

        if not _CYRILLIC_TOKEN_RE.search(safe_token):
            self._normalized_token_cache[safe_token] = safe_token
            return safe_token

        mode = ai_settings.get_rag_ru_normalization_mode()
        normalized = safe_token
        if mode in {"lemma_then_stem", "lemma_only"}:
            normalized = self._lemmatize_ru_token(normalized)
        if mode in {"lemma_then_stem", "stem_only"}:
            normalized = self._stem_ru_token(normalized)

        normalized = normalized or safe_token
        self._normalized_token_cache[safe_token] = normalized
        return normalized

    def _lemmatize_ru_token(self, token: str) -> str:
        """Лемматизировать русский токен через pymorphy3 с graceful fallback."""
        analyzer = self._get_ru_morph_analyzer()
        if analyzer is None:
            return token

        try:
            parsed = analyzer.parse(token)
            if parsed:
                normal_form = str(getattr(parsed[0], "normal_form", "") or "").strip().lower()
                if normal_form:
                    return normal_form
        except Exception:
            return token

        return token

    def _stem_ru_token(self, token: str) -> str:
        """Применить стемминг русского токена через snowballstemmer."""
        stemmer = self._get_ru_stemmer()
        if stemmer is None:
            return token

        try:
            stemmed = stemmer.stemWord(token)
            return str(stemmed or token).strip().lower()
        except Exception:
            return token

    def _get_ru_morph_analyzer(self) -> Optional[object]:
        """Ленивая инициализация pymorphy3 MorphAnalyzer."""
        if self._ru_morph_analyzer is not None:
            return self._ru_morph_analyzer

        try:
            import pymorphy3

            self._ru_morph_analyzer = pymorphy3.MorphAnalyzer()
            return self._ru_morph_analyzer
        except Exception as exc:
            if not self._normalization_dependency_warning_logged:
                logger.warning("RU-нормализация: pymorphy3 недоступен, fallback без лемматизации: %s", exc)
                self._normalization_dependency_warning_logged = True
            return None

    def _get_ru_stemmer(self) -> Optional[object]:
        """Ленивая инициализация snowballstemmer для русского."""
        if self._ru_stemmer is not None:
            return self._ru_stemmer

        try:
            import snowballstemmer

            self._ru_stemmer = snowballstemmer.stemmer("russian")
            return self._ru_stemmer
        except Exception as exc:
            if not self._normalization_dependency_warning_logged:
                logger.warning("RU-нормализация: snowballstemmer недоступен, fallback без стемминга: %s", exc)
                self._normalization_dependency_warning_logged = True
            return None

    @staticmethod
    def _score_corpus_bm25(corpus_tokens: List[List[str]], query_tokens: List[str]) -> List[float]:
        """Вычислить BM25-score для корпуса документов по токенам запроса."""
        if not corpus_tokens or not query_tokens:
            return [0.0 for _ in corpus_tokens]

        safe_corpus = [tokens if tokens else [""] for tokens in corpus_tokens]

        if BM25Okapi is not None:
            try:
                bm25 = BM25Okapi(
                    safe_corpus,
                    k1=max(0.01, float(ai_settings.AI_RAG_BM25_K1)),
                    b=max(0.0, min(1.0, float(ai_settings.AI_RAG_BM25_B))),
                )
                return [max(0.0, float(score)) for score in bm25.get_scores(query_tokens)]
            except Exception:
                pass

        k1 = max(0.01, float(ai_settings.AI_RAG_BM25_K1))
        b = max(0.0, min(1.0, float(ai_settings.AI_RAG_BM25_B)))
        doc_count = len(safe_corpus)
        avg_doc_len = sum(len(doc_tokens) for doc_tokens in safe_corpus) / max(doc_count, 1)

        doc_freq: Dict[str, int] = {}
        term_freq_by_doc: List[Counter[str]] = []
        for doc_tokens in safe_corpus:
            tf = Counter(doc_tokens)
            term_freq_by_doc.append(tf)
            for token in tf.keys():
                doc_freq[token] = doc_freq.get(token, 0) + 1

        query_tf = Counter(query_tokens)
        scores: List[float] = [0.0 for _ in safe_corpus]

        for token, qf in query_tf.items():
            df = doc_freq.get(token, 0)
            if df <= 0:
                continue

            idf = math.log(1.0 + ((doc_count - df + 0.5) / (df + 0.5)))
            for idx, tf in enumerate(term_freq_by_doc):
                freq = tf.get(token, 0)
                if freq <= 0:
                    continue
                doc_len = len(safe_corpus[idx])
                denominator = freq + (k1 * (1.0 - b + (b * doc_len / max(avg_doc_len, 1e-9))))
                if denominator <= 0:
                    continue
                scores[idx] += idf * ((freq * (k1 + 1.0)) / denominator) * qf

        return [max(0.0, float(score)) for score in scores]

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


def preload_rag_runtime_dependencies() -> Dict[str, bool]:
    """Прогреть lazy-зависимости RAG на старте процесса бота."""
    started_at = time.perf_counter()
    logger.info("RAG preload: start")

    preload_result: Dict[str, bool] = {
        "vector_provider_ready": False,
        "vector_index_ready": False,
        "ru_morph_ready": False,
        "ru_stemmer_ready": False,
        "spellcheck_vocab_ready": False,
    }

    vector_enabled = False
    ru_normalization_enabled = bool(ai_settings.is_rag_ru_normalization_enabled())
    ru_normalization_mode = ai_settings.get_rag_ru_normalization_mode()
    spellcheck_enabled = bool(ai_settings.is_rag_spellcheck_enabled())
    status = "ok"

    try:
        rag_service = get_rag_service()

        vector_enabled = bool(rag_service._is_vector_search_enabled())
        if vector_enabled:
            preload_result["vector_provider_ready"] = rag_service._get_embedding_provider() is not None
            preload_result["vector_index_ready"] = rag_service._get_vector_index() is not None

        if ru_normalization_enabled and ru_normalization_mode in {"lemma_then_stem", "lemma_only"}:
            preload_result["ru_morph_ready"] = rag_service._get_ru_morph_analyzer() is not None

        if ru_normalization_enabled and ru_normalization_mode in {"lemma_then_stem", "stem_only"}:
            preload_result["ru_stemmer_ready"] = rag_service._get_ru_stemmer() is not None

        if spellcheck_enabled:
            preload_result["spellcheck_vocab_ready"] = rag_service._build_spellcheck_vocabulary()
    except Exception:
        status = "failed"
        logger.exception("RAG preload: failed")
    finally:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "RAG preload: done status=%s duration_ms=%s vector_enabled=%s vector_provider_ready=%s vector_index_ready=%s "
            "ru_normalization_enabled=%s ru_normalization_mode=%s ru_morph_ready=%s ru_stemmer_ready=%s "
            "spellcheck_enabled=%s spellcheck_vocab_ready=%s",
            status,
            duration_ms,
            vector_enabled,
            preload_result["vector_provider_ready"],
            preload_result["vector_index_ready"],
            ru_normalization_enabled,
            ru_normalization_mode,
            preload_result["ru_morph_ready"],
            preload_result["ru_stemmer_ready"],
            spellcheck_enabled,
            preload_result["spellcheck_vocab_ready"],
        )

    return preload_result


def reset_rag_service() -> None:
    """Сбросить singleton-экземпляр RAG-сервиса (для тестов)."""
    global _rag_service_instance
    _rag_service_instance = None
