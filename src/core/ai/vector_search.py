"""vector_search.py — локальный векторный индекс и эмбеддинги для RAG."""

from __future__ import annotations

import hashlib
import time
from contextlib import nullcontext
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from config import ai_settings

logger = logging.getLogger(__name__)


@dataclass
class VectorChunkCandidate:
    """Кандидат, найденный векторным поиском."""

    score: float
    source: str
    chunk_text: str
    document_id: int
    chunk_index: int


@dataclass
class VectorSummaryCandidate:
    """Кандидат документа, найденный в summary-векторном prefilter."""

    score: float
    source: str
    summary_text: str
    document_id: int


class LocalEmbeddingProvider:
    """Локальный провайдер эмбеддингов на базе sentence-transformers."""

    def __init__(self) -> None:
        self._model = None
        self._model_name = ai_settings.AI_RAG_VECTOR_EMBEDDING_MODEL
        self._device = "cpu"
        self._fp16_enabled = bool(ai_settings.AI_RAG_VECTOR_EMBEDDING_FP16)

    def is_ready(self) -> bool:
        """Проверить, что модель эмбеддингов доступна для инференса."""
        return self._ensure_model_loaded()

    def encode_texts(self, texts: List[str]) -> List[List[float]]:
        """Преобразовать список текстов в dense-вектора."""
        if not texts:
            return []

        if not self._ensure_model_loaded():
            return []

        max_chars = max(200, int(ai_settings.AI_RAG_VECTOR_EMBEDDING_MAX_CHARS))
        normalized_texts = [self._normalize_text(text, max_chars=max_chars) for text in texts]

        with self._build_encode_precision_context():
            vectors = self._model.encode(
                normalized_texts,
                batch_size=max(1, int(ai_settings.AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE)),
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        return vectors.tolist()

    def encode(self, text: str) -> List[float]:
        """Преобразовать один текст в dense-вектор для обратной совместимости."""
        vectors = self.encode_texts([text])
        if not vectors:
            return []
        return vectors[0]

    @staticmethod
    def _normalize_text(text: str, max_chars: int) -> str:
        """Нормализовать текст перед вычислением эмбеддинга."""
        normalized = " ".join((text or "").strip().split())
        return normalized[:max_chars]

    def _ensure_model_loaded(self) -> bool:
        """Ленивая загрузка локальной embedding-модели."""
        if self._model is not None:
            return True

        try:
            self._device = self._resolve_device()
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name, device=self._device)
            self._try_enable_fp16()
            logger.info(
                "Локальная embedding-модель загружена: model=%s device=%s fp16=%s",
                self._model_name,
                self._device,
                self._fp16_enabled,
            )
            return True
        except Exception as exc:
            logger.warning("Не удалось загрузить embedding-модель %s: %s", self._model_name, exc)
            return False

    def _try_enable_fp16(self) -> None:
        """Включить FP16 для embedding-модели при запуске на CUDA."""
        if not self._fp16_enabled:
            return

        if self._device != "cuda":
            logger.info(
                "AI_RAG_VECTOR_EMBEDDING_FP16=1 проигнорирован: device=%s",
                self._device,
            )
            self._fp16_enabled = False
            return

        half_method = getattr(self._model, "half", None)
        if not callable(half_method):
            logger.warning(
                "AI_RAG_VECTOR_EMBEDDING_FP16=1 не применён: модель %s не поддерживает half()",
                self._model_name,
            )
            self._fp16_enabled = False
            return

        try:
            half_callable = half_method
            half_callable()
        except Exception as exc:
            logger.warning(
                "Не удалось включить FP16 для embedding-модели %s: %s. Используется FP32",
                self._model_name,
                exc,
            )
            self._fp16_enabled = False

    def _build_encode_precision_context(self):
        """Вернуть контекст precision для encode (autocast на CUDA при FP16)."""
        if not self._fp16_enabled or self._device != "cuda":
            return nullcontext()

        try:
            import torch

            return torch.cuda.amp.autocast(dtype=torch.float16)
        except Exception as exc:
            logger.warning(
                "Не удалось включить autocast FP16 для embedding encode: %s. Используется FP32",
                exc,
            )
            self._fp16_enabled = False
            return nullcontext()

    @staticmethod
    def _resolve_device() -> str:
        """Определить целевое устройство для вычисления эмбеддингов."""
        configured = str(ai_settings.AI_RAG_VECTOR_DEVICE or "auto").strip().lower()
        if configured not in {"auto", "cuda", "cpu"}:
            logger.warning(
                "Неизвестное значение AI_RAG_VECTOR_DEVICE=%s, используется auto",
                configured,
            )
            configured = "auto"

        if configured == "cpu":
            return "cpu"

        cuda_available = False
        try:
            import torch

            cuda_available = bool(torch.cuda.is_available())
        except Exception as exc:
            logger.info("PyTorch CUDA недоступен, используется CPU: %s", exc)

        if configured == "cuda":
            if cuda_available:
                return "cuda"
            logger.warning("Запрошен AI_RAG_VECTOR_DEVICE=cuda, но CUDA недоступен, используется CPU")
            return "cpu"

        if cuda_available:
            return "cuda"
        return "cpu"


class LocalVectorIndex:
    """Векторный индекс на базе Qdrant с remote-first и local fallback."""

    def __init__(
        self,
        *,
        chunk_collection_name: Optional[str] = None,
        summary_collection_name: Optional[str] = None,
    ) -> None:
        self._client = None
        self._remote_client = None
        self._collection_name = str(chunk_collection_name or ai_settings.AI_RAG_VECTOR_COLLECTION)
        self._summary_collection_name = str(
            summary_collection_name or ai_settings.AI_RAG_SUMMARY_VECTOR_COLLECTION
        )
        self._embedding_size: Optional[int] = None
        self._client_init_failed = False
        self._remote_failures = 0
        self._remote_cooldown_until = 0.0
        self._remote_state = "unknown"
        logger.info(
            "Эффективная конфигурация remote Qdrant: remote_configured=%s remote_url=%s "
            "remote_api_key_set=%s local_fallback_enabled=%s",
            bool(str(ai_settings.AI_RAG_VECTOR_REMOTE_URL or "").strip()),
            self._safe_remote_url_for_logs(),
            bool(str(ai_settings.AI_RAG_VECTOR_REMOTE_API_KEY or "").strip()),
            bool(ai_settings.AI_RAG_VECTOR_LOCAL_MODE),
        )

    def is_ready(self) -> bool:
        """Проверить доступность клиента и коллекции."""
        client = self._get_client()
        if client is None:
            return False
        return True

    def ensure_collection(self, embedding_size: int, collection_name: Optional[str] = None) -> bool:
        """Создать коллекцию индекса при первом запуске."""
        if embedding_size <= 0:
            return False

        target_collection = str(collection_name or self._collection_name)

        distance = self._parse_distance()

        def _action(client, backend_name: str) -> bool:
            from qdrant_client import models

            collection_exists = client.collection_exists(target_collection)
            if not collection_exists:
                client.create_collection(
                    collection_name=target_collection,
                    vectors_config=models.VectorParams(
                        size=embedding_size,
                        distance=distance,
                    ),
                )
                logger.info(
                    "Создана коллекция векторного индекса: backend=%s name=%s size=%s",
                    backend_name,
                    target_collection,
                    embedding_size,
                )

            self._embedding_size = embedding_size
            return True

        return self._execute_with_failover(
            operation_name="ensure_collection",
            remote_action=_action,
            local_action=_action,
            default_value=False,
        )

    def ensure_summary_collection(self, embedding_size: int) -> bool:
        """Создать коллекцию summary-эмбеддингов при первом запуске."""
        return self.ensure_collection(
            embedding_size=embedding_size,
            collection_name=self._summary_collection_name,
        )

    def upsert_chunks(
        self,
        chunks: List[Dict[str, object]],
        embeddings: List[List[float]],
    ) -> int:
        """Записать чанки и их эмбеддинги в индекс."""
        if not chunks or not embeddings or len(chunks) != len(embeddings):
            return 0

        if not self.ensure_collection(len(embeddings[0]), collection_name=self._collection_name):
            return 0

        def _action(client, _backend_name: str) -> int:
            from qdrant_client import models

            points: List[models.PointStruct] = []
            for chunk, vector in zip(chunks, embeddings):
                point_id = self._build_point_id(
                    document_id=int(chunk.get("document_id") or 0),
                    chunk_index=int(chunk.get("chunk_index") or 0),
                )
                payload = {
                    "document_id": int(chunk.get("document_id") or 0),
                    "chunk_index": int(chunk.get("chunk_index") or 0),
                    "filename": str(chunk.get("filename") or "document"),
                    "chunk_text": str(chunk.get("chunk_text") or ""),
                    "status": str(chunk.get("status") or "active"),
                }
                points.append(models.PointStruct(id=point_id, vector=vector, payload=payload))

            client.upsert(collection_name=self._collection_name, points=points, wait=True)
            return len(points)

        return self._execute_with_failover(
            operation_name="upsert_chunks",
            remote_action=_action,
            local_action=_action,
            default_value=0,
        )

    def upsert_summaries(
        self,
        summaries: List[Dict[str, object]],
        embeddings: List[List[float]],
    ) -> int:
        """Записать summary-документы и их эмбеддинги в отдельную коллекцию."""
        if not summaries or not embeddings or len(summaries) != len(embeddings):
            return 0

        if not self.ensure_summary_collection(len(embeddings[0])):
            return 0

        def _action(client, _backend_name: str) -> int:
            from qdrant_client import models

            points: List[models.PointStruct] = []
            for summary_row, vector in zip(summaries, embeddings):
                document_id = int(summary_row.get("document_id") or 0)
                if document_id <= 0:
                    continue

                point_id = self._build_summary_point_id(document_id=document_id)
                payload = {
                    "document_id": document_id,
                    "filename": str(summary_row.get("filename") or "document"),
                    "summary_text": str(summary_row.get("summary_text") or ""),
                    "status": str(summary_row.get("status") or "active"),
                }
                points.append(models.PointStruct(id=point_id, vector=vector, payload=payload))

            if not points:
                return 0

            client.upsert(collection_name=self._summary_collection_name, points=points, wait=True)
            return len(points)

        return self._execute_with_failover(
            operation_name="upsert_summaries",
            remote_action=_action,
            local_action=_action,
            default_value=0,
        )

    def search(
        self,
        query_vector: List[float],
        limit: int,
        allowed_document_ids: Optional[List[int]] = None,
    ) -> List[VectorChunkCandidate]:
        """Выполнить векторный поиск релевантных чанков."""
        if not query_vector:
            return []

        safe_limit = max(1, min(limit, 100))
        prefetch_limit = max(safe_limit, int(ai_settings.AI_RAG_VECTOR_PREFETCH_K))
        query_filter = self._build_search_filter(allowed_document_ids)

        def _action(client, _backend_name: str) -> List[VectorChunkCandidate]:
            response = client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=prefetch_limit,
                with_payload=True,
                with_vectors=False,
            )
            points = response.points

            candidates: List[VectorChunkCandidate] = []
            for point in points or []:
                payload = getattr(point, "payload", {}) or {}
                raw_score = float(getattr(point, "score", 0.0) or 0.0)
                score = max(0.0, min(raw_score, 1.0))
                if score <= 0:
                    continue

                document_id = int(payload.get("document_id") or 0)
                chunk_index = int(payload.get("chunk_index") or 0)
                filename = str(payload.get("filename") or "document")
                chunk_text = str(payload.get("chunk_text") or "").strip()
                if not document_id or not chunk_text:
                    continue

                candidates.append(
                    VectorChunkCandidate(
                        score=score,
                        source=filename,
                        chunk_text=chunk_text,
                        document_id=document_id,
                        chunk_index=chunk_index,
                    )
                )

            candidates.sort(key=lambda item: item.score, reverse=True)
            return candidates[:safe_limit]

        return self._execute_with_failover(
            operation_name="search",
            remote_action=_action,
            local_action=_action,
            default_value=[],
        )

    def search_summaries(
        self,
        query_vector: List[float],
        limit: int,
        allowed_document_ids: Optional[List[int]] = None,
    ) -> List[VectorSummaryCandidate]:
        """Выполнить векторный поиск релевантных summary-документов."""
        if not query_vector:
            return []

        safe_limit = max(1, min(limit, 200))
        prefetch_limit = max(safe_limit, int(ai_settings.AI_RAG_VECTOR_PREFETCH_K))
        query_filter = self._build_search_filter(allowed_document_ids)

        def _action(client, _backend_name: str) -> List[VectorSummaryCandidate]:
            response = client.query_points(
                collection_name=self._summary_collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=prefetch_limit,
                with_payload=True,
                with_vectors=False,
            )
            points = response.points

            candidates: List[VectorSummaryCandidate] = []
            for point in points or []:
                payload = getattr(point, "payload", {}) or {}
                raw_score = float(getattr(point, "score", 0.0) or 0.0)
                score = max(0.0, min(raw_score, 1.0))
                if score <= 0:
                    continue

                document_id = int(payload.get("document_id") or 0)
                filename = str(payload.get("filename") or "document")
                summary_text = str(payload.get("summary_text") or "").strip()
                if not document_id or not summary_text:
                    continue

                candidates.append(
                    VectorSummaryCandidate(
                        score=score,
                        source=filename,
                        summary_text=summary_text,
                        document_id=document_id,
                    )
                )

            candidates.sort(key=lambda item: item.score, reverse=True)
            return candidates[:safe_limit]

        return self._execute_with_failover(
            operation_name="search_summaries",
            remote_action=_action,
            local_action=_action,
            default_value=[],
        )

    def mark_document_status(self, document_id: int, status: str) -> int:
        """Обновить статус документа в payload всех его векторных точек."""
        if document_id <= 0:
            return 0


        def _action(client, _backend_name: str) -> int:
            from qdrant_client import models

            client.set_payload(
                collection_name=self._collection_name,
                payload={"status": str(status or "active")},
                points=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
            return 1

        return self._execute_with_failover(
            operation_name="mark_document_status",
            remote_action=_action,
            local_action=_action,
            default_value=0,
        )

    def mark_summary_status(self, document_id: int, status: str) -> int:
        """Обновить статус summary-документа в payload векторной summary-коллекции."""
        if document_id <= 0:
            return 0

        def _action(client, _backend_name: str) -> int:
            from qdrant_client import models

            client.set_payload(
                collection_name=self._summary_collection_name,
                payload={"status": str(status or "active")},
                points=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
            return 1

        return self._execute_with_failover(
            operation_name="mark_summary_status",
            remote_action=_action,
            local_action=_action,
            default_value=0,
        )

    def delete_document_points(self, document_id: int) -> int:
        """Удалить все векторные точки документа."""
        if document_id <= 0:
            return 0


        def _action(client, _backend_name: str) -> int:
            from qdrant_client import models

            client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
            return 1

        return self._execute_with_failover(
            operation_name="delete_document_points",
            remote_action=_action,
            local_action=_action,
            default_value=0,
        )

    def delete_summary_points(self, document_id: int) -> int:
        """Удалить summary-точки документа из summary-коллекции."""
        if document_id <= 0:
            return 0

        def _action(client, _backend_name: str) -> int:
            from qdrant_client import models

            client.delete(
                collection_name=self._summary_collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
            return 1

        return self._execute_with_failover(
            operation_name="delete_summary_points",
            remote_action=_action,
            local_action=_action,
            default_value=0,
        )

    def _build_search_filter(self, allowed_document_ids: Optional[List[int]]):
        """Собрать фильтр по активному статусу и списку document_id."""
        try:
            from qdrant_client import models
        except Exception:
            return None

        must_conditions = [
            models.FieldCondition(
                key="status",
                match=models.MatchValue(value="active"),
            )
        ]

        if allowed_document_ids:
            normalized_ids = [int(doc_id) for doc_id in allowed_document_ids if int(doc_id) > 0]
            if normalized_ids:
                must_conditions.append(
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchAny(any=normalized_ids),
                    )
                )

        return models.Filter(must=must_conditions)

    def _get_client(self):
        """Инициализировать и вернуть активный Qdrant-клиент."""
        backend_name, client = self._get_active_backend_client()
        if backend_name and client is not None:
            logger.debug("Используется Qdrant backend=%s", backend_name)
        return client

    def _execute_with_failover(
        self,
        operation_name: str,
        remote_action,
        local_action,
        default_value,
    ):
        """Выполнить операцию в remote-first режиме с fallback на local backend."""
        remote_client = self._get_remote_client()
        if remote_client is not None:
            try:
                result = remote_action(remote_client, "remote")
                self._reset_remote_failures()
                return result
            except Exception as exc:
                self._register_remote_failure(operation_name=operation_name, exc=exc)

        local_client = self._get_local_client()
        if local_client is not None:
            try:
                return local_action(local_client, "local")
            except Exception as exc:
                logger.warning("Операция %s в local Qdrant завершилась ошибкой: %s", operation_name, exc)

        return default_value

    def _get_active_backend_client(self) -> tuple[Optional[str], Optional[object]]:
        """Вернуть активный клиент и имя backend с приоритетом remote."""
        remote_client = self._get_remote_client()
        if remote_client is not None:
            return "remote", remote_client

        local_client = self._get_local_client()
        if local_client is not None:
            return "local", local_client

        return None, None

    def _get_remote_client(self):
        """Инициализировать и вернуть удалённый Qdrant-клиент при доступной конфигурации."""
        if not self._is_remote_enabled():
            self._set_remote_state("disabled")
            return None

        if self._is_remote_in_cooldown():
            self._set_remote_state("cooldown")
            return None

        if self._remote_client is not None:
            return self._remote_client

        try:
            from qdrant_client import QdrantClient

            timeout = max(1.0, float(ai_settings.AI_RAG_VECTOR_REMOTE_TIMEOUT_SECONDS))
            remote_url = str(ai_settings.AI_RAG_VECTOR_REMOTE_URL or "").strip()
            remote_api_key = str(ai_settings.AI_RAG_VECTOR_REMOTE_API_KEY or "").strip() or None

            self._remote_client = QdrantClient(
                url=remote_url,
                api_key=remote_api_key,
                timeout=timeout,
            )
            self._remote_client.get_collections()
            self._set_remote_state("up")
            return self._remote_client
        except Exception as exc:
            self._remote_client = None
            self._register_remote_failure(operation_name="connect", exc=exc)
            return None

    def _get_local_client(self):
        """Инициализировать и вернуть локальный Qdrant-клиент."""
        if self._client is not None:
            return self._client

        if self._client_init_failed:
            return None

        if not ai_settings.AI_RAG_VECTOR_LOCAL_MODE:
            logger.warning("Локальный fallback отключён: AI_RAG_VECTOR_LOCAL_MODE=0")
            return None

        try:
            from qdrant_client import QdrantClient

            db_path = Path(ai_settings.AI_RAG_VECTOR_DB_PATH).expanduser().resolve()
            db_path.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(db_path))
            return self._client
        except Exception as exc:
            if self._is_storage_locked_error(exc):
                self._client_init_failed = True
                logger.warning(
                    "Не удалось инициализировать Qdrant local mode: %s. "
                    "Векторная индексация отключена для текущего процесса. "
                    "Для параллельной работы используйте Qdrant server или отдельный AI_RAG_VECTOR_DB_PATH.",
                    exc,
                )
                return None
            logger.warning("Не удалось инициализировать Qdrant local mode: %s", exc)
            return None

    def _is_remote_enabled(self) -> bool:
        """Проверить, что remote backend сконфигурирован."""
        return bool(str(ai_settings.AI_RAG_VECTOR_REMOTE_URL or "").strip())

    def _is_remote_in_cooldown(self) -> bool:
        """Проверить, что remote backend находится в режиме cooldown."""
        if self._remote_cooldown_until <= 0:
            return False
        return time.time() < self._remote_cooldown_until

    def _register_remote_failure(self, operation_name: str, exc: Exception) -> None:
        """Учесть ошибку remote backend и активировать failover при достижении порога."""
        self._remote_failures += 1
        self._set_remote_state("down")
        threshold = max(1, int(ai_settings.AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD))
        logger.warning(
            "Ошибка remote Qdrant при операции %s (%s/%s): %s",
            operation_name,
            self._remote_failures,
            threshold,
            exc,
        )

        if self._remote_failures < threshold:
            return

        cooldown_seconds = max(1, int(ai_settings.AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS))
        self._remote_cooldown_until = time.time() + float(cooldown_seconds)
        self._remote_client = None
        self._set_remote_state("cooldown")
        logger.warning(
            "Remote Qdrant временно отключён на %s сек после %s ошибок подряд. Активирован local fallback.",
            cooldown_seconds,
            self._remote_failures,
        )

    def _reset_remote_failures(self) -> None:
        """Сбросить счётчик ошибок remote backend после успешной операции."""
        self._remote_failures = 0
        self._remote_cooldown_until = 0.0
        self._set_remote_state("up")

    def _set_remote_state(self, new_state: str) -> None:
        """Зафиксировать и залогировать смену состояния удалённого Qdrant backend."""
        normalized = str(new_state or "unknown").strip().lower() or "unknown"
        if normalized == self._remote_state:
            return

        previous_state = self._remote_state
        self._remote_state = normalized

        if normalized == "up":
            logger.info(
                "Состояние remote Qdrant: UP (prev=%s, url=%s)",
                previous_state,
                self._safe_remote_url_for_logs(),
            )
            return

        if normalized == "cooldown":
            logger.warning(
                "Состояние remote Qdrant: COOLDOWN (prev=%s, cooldown_until_ts=%.3f)",
                previous_state,
                self._remote_cooldown_until,
            )
            return

        if normalized == "down":
            logger.warning(
                "Состояние remote Qdrant: DOWN (prev=%s)",
                previous_state,
            )
            return

        if normalized == "disabled":
            logger.info(
                "Состояние remote Qdrant: DISABLED (AI_RAG_VECTOR_REMOTE_URL не задан)",
            )
            return

        logger.info("Состояние remote Qdrant: %s (prev=%s)", normalized.upper(), previous_state)

    @staticmethod
    def _safe_remote_url_for_logs() -> str:
        """Вернуть безопасное значение URL удалённого Qdrant для логов."""
        return str(ai_settings.AI_RAG_VECTOR_REMOTE_URL or "").strip() or "<empty>"

    @staticmethod
    def _is_storage_locked_error(exc: Exception) -> bool:
        """Определить ошибку блокировки локального хранилища Qdrant."""
        message = str(exc or "").strip().lower()
        if not message:
            return False

        return (
            "storage folder" in message
            and "already accessed" in message
            and "qdrant" in message
        )

    def _parse_distance(self):
        """Преобразовать строковое имя метрики в enum Qdrant."""
        try:
            from qdrant_client import models
        except Exception as exc:
            raise RuntimeError("Qdrant models недоступны") from exc

        normalized = str(ai_settings.AI_RAG_VECTOR_DISTANCE or "cosine").strip().lower()
        if normalized == "dot":
            return models.Distance.DOT
        if normalized == "euclid":
            return models.Distance.EUCLID
        if normalized == "manhattan":
            return models.Distance.MANHATTAN
        return models.Distance.COSINE

    @staticmethod
    def _build_point_id(document_id: int, chunk_index: int) -> int:
        """Сгенерировать стабильный числовой ID точки по document_id и chunk_index."""
        raw = f"{document_id}:{chunk_index}".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return int(digest, 16)

    @staticmethod
    def _build_summary_point_id(document_id: int) -> int:
        """Сгенерировать стабильный числовой ID summary-точки по document_id."""
        raw = f"summary:{document_id}".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return int(digest, 16)
