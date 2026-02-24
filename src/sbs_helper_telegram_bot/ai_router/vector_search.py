"""vector_search.py — локальный векторный индекс и эмбеддинги для RAG."""

from __future__ import annotations

import hashlib
from contextlib import nullcontext
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings

logger = logging.getLogger(__name__)


@dataclass
class VectorChunkCandidate:
    """Кандидат, найденный векторным поиском."""

    score: float
    source: str
    chunk_text: str
    document_id: int
    chunk_index: int


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
            half_method()
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

            amp_autocast = getattr(getattr(torch, "amp", None), "autocast", None)
            if callable(amp_autocast):
                return amp_autocast("cuda", dtype=torch.float16)

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
    """Локальный векторный индекс на базе Qdrant (local mode)."""

    def __init__(self) -> None:
        self._client = None
        self._collection_name = ai_settings.AI_RAG_VECTOR_COLLECTION
        self._embedding_size: Optional[int] = None
        self._client_init_failed = False

    def is_ready(self) -> bool:
        """Проверить доступность клиента и коллекции."""
        client = self._get_client()
        if client is None:
            return False
        return True

    def ensure_collection(self, embedding_size: int) -> bool:
        """Создать коллекцию индекса при первом запуске."""
        if embedding_size <= 0:
            return False

        client = self._get_client()
        if client is None:
            return False

        distance = self._parse_distance()

        try:
            from qdrant_client import models

            collection_exists = client.collection_exists(self._collection_name)
            if not collection_exists:
                client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=models.VectorParams(
                        size=embedding_size,
                        distance=distance,
                    ),
                )
                logger.info(
                    "Создана коллекция локального векторного индекса: name=%s size=%s",
                    self._collection_name,
                    embedding_size,
                )

            self._embedding_size = embedding_size
            return True
        except Exception as exc:
            logger.warning("Не удалось создать/проверить коллекцию Qdrant: %s", exc)
            return False

    def upsert_chunks(
        self,
        chunks: List[Dict[str, object]],
        embeddings: List[List[float]],
    ) -> int:
        """Записать чанки и их эмбеддинги в индекс."""
        if not chunks or not embeddings or len(chunks) != len(embeddings):
            return 0

        if not self.ensure_collection(len(embeddings[0])):
            return 0

        client = self._get_client()
        if client is None:
            return 0

        try:
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
        except Exception as exc:
            logger.warning("Не удалось выполнить upsert чанков в Qdrant: %s", exc)
            return 0

    def search(
        self,
        query_vector: List[float],
        limit: int,
        allowed_document_ids: Optional[List[int]] = None,
    ) -> List[VectorChunkCandidate]:
        """Выполнить векторный поиск релевантных чанков."""
        if not query_vector:
            return []

        client = self._get_client()
        if client is None:
            return []

        safe_limit = max(1, min(limit, 100))
        prefetch_limit = max(safe_limit, int(ai_settings.AI_RAG_VECTOR_PREFETCH_K))
        query_filter = self._build_search_filter(allowed_document_ids)

        try:
            points = client.search(
                collection_name=self._collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=prefetch_limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            logger.warning("Не удалось выполнить поиск в Qdrant: %s", exc)
            return []

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

    def mark_document_status(self, document_id: int, status: str) -> int:
        """Обновить статус документа в payload всех его векторных точек."""
        if document_id <= 0:
            return 0

        client = self._get_client()
        if client is None:
            return 0

        try:
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
        except Exception as exc:
            logger.warning("Не удалось обновить статус векторных точек документа %s: %s", document_id, exc)
            return 0

    def delete_document_points(self, document_id: int) -> int:
        """Удалить все векторные точки документа."""
        if document_id <= 0:
            return 0

        client = self._get_client()
        if client is None:
            return 0

        try:
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
        except Exception as exc:
            logger.warning("Не удалось удалить точки документа %s из Qdrant: %s", document_id, exc)
            return 0

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
        """Инициализировать и вернуть Qdrant-клиент."""
        if self._client is not None:
            return self._client

        if self._client_init_failed:
            return None

        if not ai_settings.AI_RAG_VECTOR_LOCAL_MODE:
            logger.warning("Только local mode поддерживается в текущем профиле настройки")
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
